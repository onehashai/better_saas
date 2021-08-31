from __future__ import unicode_literals
from codecs import ignore_errors
from re import sub
from erpnext.accounts.doctype.payment_entry.payment_entry import PaymentEntry
from erpnext.controllers.accounts_controller import get_tax_rate
import frappe
import json
import datetime
from frappe.geo.doctype import currency
from frappe.utils import data
from six import string_types
from frappe import _
from frappe.utils import format_date, flt
from frappe.utils.data import (ceil, global_date_format, nowdate, getdate, add_days, add_to_date,
                               add_months, date_diff, flt, get_date_str, get_first_day, get_last_day)
from frappe.sessions import get_geo_ip_country
from frappe.geo.country_info import get_country_timezone_info
from frappe.integrations.utils import get_payment_gateway_controller
from better_saas.better_saas.doctype.saas_user.saas_user import SaasUser, apply_new_limits, disable_enable_site
from erpnext.accounts.doctype.subscription.subscription import Subscription, get_subscription_updates
from erpnext.erpnext_integrations.stripe_integration import stripe_update_subscription, stripe_cancel_subscription,create_stripe_refund,retrieve_stripe_invoice
from frappe.integrations.doctype.stripe_settings.stripe_settings import get_gateway_controller
from erpnext.crm.doctype.lead.lead import make_customer
from erpnext.accounts.doctype.payment_request.payment_request import make_payment_entry

no_cache = 1

def get_context(context):
    context.no_cache = 1
    args = frappe.request.args
    context.site = args["site"] if "site" in args else ""
    context.geo_country = get_geo_ip_country(
        frappe.local.request_ip) if frappe.local.request_ip else None
    pass


@frappe.whitelist(allow_guest=True)
def get_country():
    geo_country = get_geo_ip_country(
        frappe.local.request_ip) if frappe.local.request_ip else None
    return geo_country

@frappe.whitelist(allow_guest=True)
def get_country_list():
    countries = frappe.get_list("Country",ignore_permissions=True)
    country_list=[]
    for country in countries:
        country_list.append(country.name)
    return country_list

@frappe.whitelist(allow_guest=True)
def get_site_details(site_name, email, onehash_partner):
    site = frappe.get_doc("Saas Site", site_name,ignore_permissions=True)
    saas_user= frappe.db.get_values("Saas User",filters={"linked_saas_site":site_name},fieldname=["email","company_name","currency"],as_dict=True)[0]
    
    site.expiry = global_date_format(site.expiry)
    plan = get_base_plan_details(site.base_plan)
    addons = get_addon_plans(plan.currency)
    formatted_expiry = global_date_format(site.expiry)
    # Discounted Amount
    discounted_users = get_discounted_users(site_name)
    discount_amount = flt(plan.cost)*flt(discounted_users)
    discount_display_amount = frappe.format_value(-1 * flt(plan.cost)*flt(discounted_users), {"fieldtype": "Currency", "currency": plan.currency})
    # Subscription Amount
    subscription_amount = flt(plan.cost)*flt(site.limit_for_users)
    subscription_value = frappe.format_value(flt(plan.cost)*flt(site.limit_for_users) - flt(discount_amount), {"fieldtype": "Float"})
    subscription_display_amount = frappe.format_value(flt(
        plan.cost)*flt(site.limit_for_users), {"fieldtype": "Currency", "currency": plan.currency})
    return {
        "site": site,
        "plan": plan,
        "formatted_expiry": formatted_expiry,
        "non_discounted_subscription_amount": subscription_amount,
        "subscription_amount": subscription_amount,
        "subscription_value": subscription_value,
        "addons": addons,
        "subscription_display_amount": subscription_display_amount,
        "discount_amount": discount_amount,
        "discount_value": discounted_users,
        "discount_display_amount": discount_display_amount,
        "billing_company_name": saas_user.company_name,
        "billing_email":saas_user.email
    }


def get_discounted_users(site_name):
    return frappe.get_doc("Saas Site", site_name, ignore_permissions=True).discounted_users


def get_addon_plans(currency):
    addons = frappe.get_all("Saas AddOn", filters={"disabled": 0, "currency": currency, "is_a_subscription": 1}, fields=[
                            "addon_name", "name", "monthly_amount", "yearly_amount", "addon_type", "addon_value", "currency"])
    result_addon = {}
    for addon in addons:
        result_addon[addon.addon_type] = addon
    return result_addon


@frappe.whitelist(allow_guest=True)
def get_cart_details(site_name, email, onehash_partner, cart):
    site_details = get_site_details(site_name, email, onehash_partner)
    # base_plan_details = get_base_plan_details(cart.plan)
    return get_cart_value(site_details, cart)


def get_base_plan_details(plan_name):
    return frappe.get_doc("Subscription Plan", plan_name)


def get_cart_value(site_details, cart):
    cart = json.loads(cart)
    site_data = site_details
    cart_details = {}
    cart_details["cart"] = []

    if("Users" in cart):
        pass
    else:
        cart["Users"] = site_data["site"].limit_for_users - site_data["site"].discounted_users

    # cart_details["cart"] = [{
    #     "upgrade_type": "Subscription",
    #     "value": 1,
    #     "amount": site_data["subscription_value"],
    #     "amount_to_display": site_data["subscription_value"]
    # }]
    # cart_amount = flt(site_data["subscription_value"])
    cart_amount = 0
    addons = site_data["addons"]
    plan = site_data["plan"]
    for key, addon in addons.items():
        if (key in cart and cart[key] != 0):
            item_amount = flt(cart[key]*addon["monthly_amount"]/flt(addon["addon_value"]))
    
            ## Check for negetive amount
            if cart_amount + item_amount <= 0:
                cart[key] = 0
                frappe.throw("Total amount must be positive")

            cart_amount = cart_amount + item_amount
           
            cart_item = {
                "upgrade_type": key,
                "value": cart[key],
                "amount": item_amount,
                "amount_to_display": frappe.format_value(item_amount, {"fieldtype": "Currency", "currency": plan.currency})
            }
            cart_details["cart"].append(cart_item)
    
    ## Get Tax Amount
    tax_amount = 0
    if plan.sales_taxes_and_charges_template:
        from erpnext.controllers.accounts_controller import get_taxes_and_charges
        taxes = get_taxes_and_charges("Sales Taxes and Charges Template", plan.sales_taxes_and_charges_template)
        for tax in taxes:
            tax_amount = tax_amount + flt(tax.rate) * flt(cart_amount)/100


    cart_details["total"] = cart_amount
    cart_details["total_tax"] = tax_amount
    cart_details["subscribed_users"] = site_data["site"].limit_for_users
    cart_details["discounted_users"] = site_data["site"].discounted_users
    cart_details["total_to_display"] = frappe.format_value(cart_amount, {"fieldtype": "Currency", "currency": plan.currency})
    cart_details["payment_gateway"] = frappe.get_value("Payment Gateway Account", plan.payment_gateway, "payment_gateway")
    return {"cart_details": cart_details, "addons": addons, "plan": plan, "site_data": site_data}


@frappe.whitelist(allow_guest=True)
def create_billing_address(site_name, values):
    try:
        saas_user = frappe.get_list('Saas User', filters={'linked_saas_site': site_name}, ignore_permissions=True)[0].name
        saas_user = frappe.get_doc('Saas User', saas_user, ignore_permissions=True)
        saas_user_email = saas_user.email

        customer = frappe.get_list("Customer", filters={'email_id': saas_user_email}, ignore_permissions=True)
        if len(customer)>0:
            customer_name = customer[0].name

        lead = frappe.get_list('Lead', filters={'email_id': saas_user_email}, ignore_permissions=True)

        if not len(lead)>0:
            lead = frappe.new_doc('Lead')
            lead.email_id = saas_user.email
            lead.lead_name = "{} {}".format(saas_user.first_name, saas_user.last_name)
            lead.insert(ignore_permissions=True)
        else: 
            lead = frappe.get_doc("Lead",lead[0].name, ignore_permissions=True)
            
        values = frappe._dict(json.loads(values))
        doc = frappe.new_doc("Address")
        doc.address_title = customer_name if len(customer)>0 else lead.lead_name
        doc.address_type = values.address_type
        doc.email_id = values.email_id
        doc.phone = values.phone
        doc.address_line1 = values.address_line1
        doc.address_line2 = values.address_line2
        doc.city = values.city
        doc.state = values.state
        doc.pincode = values.pincode
        doc.country = values.country
        doc.gst_state = values.gst_state
        doc.gstin = values.gstin
        doc.is_primary_address = 1
        doc.insert(ignore_permissions=True)

        if len(customer)>0:
            row = doc.append("links",{})
            row.link_doctype = "Customer"
            row.link_name = customer_name
            row.link_title = customer_name
        if lead:
            row = doc.append("links",{})
            row.link_doctype = "Lead"
            row.link_name = lead.name
            row.link_title = lead.name
        doc.save(ignore_permissions=True)
        return 'success'
    except:
        frappe.log_error(frappe.get_traceback(), "Billing Address Create Error")
        return 'failed'


@frappe.whitelist(allow_guest=True)
def get_address(address):
    return frappe.get_doc("Address", address, ignore_permissions=True)

@frappe.whitelist(allow_guest=True)
def update_billing_address(values):
    try:
        values = frappe._dict(json.loads(values))
        address_name = values.address_name

        doc = frappe.get_doc("Address", address_name, ignore_permissions=True)
        doc.address_type = values.address_type
        doc.email_id = values.email_id
        doc.phone = values.phone
        doc.address_line1 = values.address_line1
        doc.address_line2 = values.address_line2
        doc.city = values.city
        doc.state = values.state
        doc.pincode = values.pincode
        doc.country = values.country
        doc.is_primary_address = 1
        doc.gst_state = values.gst_state
        doc.gstin = values.gstin
        doc.save(ignore_permissions=True)
        return 'success'
    except:
        frappe.log_error(frappe.get_traceback(), "Billing Address Update Error")
        return 'failed'


@frappe.whitelist(allow_guest=True)
def get_billing_address(site_name):
    try:
        from frappe.contacts.doctype.address.address import get_address_display

        saas_user = frappe.get_list('Saas User', filters={'linked_saas_site': site_name}, ignore_permissions=True)[0].name
        saas_user_email = frappe.get_doc('Saas User', saas_user).email

        customer = frappe.get_list("Customer", filters={'email_id': saas_user_email}, ignore_permissions=True)

        lead = frappe.get_list('Lead', filters={'email_id': saas_user_email}, ignore_permissions=True)
    
        if len(customer)>0:
            primary_address = frappe.get_list("Address", filters={"link_name": customer[0].name, 'is_primary_address': 1}, ignore_permissions=True)[0].name
        elif len(lead)>0:
            primary_address = frappe.get_list("Address", filters={"link_name": lead[0].name, 'is_primary_address': 1}, ignore_permissions=True)[0].name
        return {"address_object":primary_address,"address_display":get_address_display(primary_address)}
    except Exception as e:
        frappe.log_error(e,"Billing Address")
        return {'message': "Unable to fetch billing address", 'status_code': '404' }


@frappe.whitelist(allow_guest=True)
def cancel(site_name):
    site = frappe.get_doc("Saas Site", site_name, ignore_permissions=True)
    if not site.subscription:
        frappe.throw("No active subscription found for this site")

    plan = get_base_plan_details(site.base_plan)
    plan_id = plan.payment_plan_id

    gateway_controller = frappe.get_value(
        "Payment Gateway Account", plan.payment_gateway, "payment_gateway")
    controller = get_payment_gateway_controller(gateway_controller)

    subscription = frappe.get_doc(
        "Subscription", site.subscription, ignore_permissions=True)
    subscription_id = subscription.subscription_id

    if 'Stripe' in controller.name:
        try:
            for plan in subscription.plans:
                if plan.plan == site.base_plan:
                    subscription_item_id = plan.subscription_item_id

            subscription_details = frappe._dict({
                "site_name": site_name,
                "reference_doctype": "Saas Site",
                "reference_docname": site_name,
                "subscription_id": subscription_id,
                "subscription_item_id": subscription_item_id,
                "plan_id": plan_id,
            })

            gateway_controller = get_gateway_controller(subscription_details["reference_doctype"], subscription_details["reference_docname"])
            stripe_cancel_subscription(gateway_controller, subscription_details)

            # Redirect the user to this url
            redirect_url = "https://{0}/app/usage-info".format(site_name)
            return get_redirect_message(_('Subscription Cancelled'),_("Your Subscription will get cancelled after end of current billing cycle."),primary_label="Continue",primary_action=redirect_url)
        except:
            frappe.log_error(frappe.get_traceback(),"Stripe Subscription Cancellation Error")
            return
    else:
        try:
            controller.cancel_subscription(subscription_id)
            redirect_url = "https://{0}/app/usage-info".format(site_name)
            return get_redirect_message(_('Subscription Cancelled'),_("Your Subscription will get cancelled after end of current billing cycle."),primary_label="Continue",primary_action=redirect_url)
        except:
            frappe.log_error(frappe.get_traceback(),"Razorpay Subscription Cancellation Error")
            return 

@frappe.whitelist(allow_guest=True)
def pay(site_name, email, onehash_partner, cart):
    cart = get_cart_details(site_name, email, onehash_partner, cart)
    gateway_controller = cart["cart_details"]["payment_gateway"] if "payment_gateway" in cart["cart_details"] else "Razorpay"
    controller = get_payment_gateway_controller(gateway_controller)

    try:
        site = frappe.get_doc('Saas Site', site_name, ignore_permissions=True)
        subscription = site.subscription
    except Exception as e:
        log = frappe.log_error(frappe.get_traceback(),"Subscription Fetching Error")

    if cart["cart_details"]["total"] <= 0:
        if not subscription:
            if not 'Stripe' in controller.name:
                frappe.throw(_("Can not process Zero Amount"))

    # For Stripe
    if 'Stripe' in controller.name:
        try:
            plan_id = cart["plan"].payment_plan_id if cart["plan"] else None

            if not plan_id:
                frappe.throw(_("Please setup Plan ID"))

            if not subscription:
                payment_details = {
                    "amount": cart["cart_details"]["total"],
                    "title": "OneHash",
                    "description": "Subscription Fee",
                    "reference_doctype": "Saas Site",
                    "reference_docname": site_name,
                    "payer_email": cart["site_data"]["billing_email"],
                    "payer_name": cart["site_data"]["billing_company_name"],
                    "order_id": "",
                    "plan_id": plan_id,
                    "quantity": cart["cart_details"]["subscribed_users"] - cart["cart_details"]["discounted_users"],
                    "currency": "USD",
                    "redirect_to": frappe.utils.get_url("https://{0}/app/usage-info".format(site_name) or "https://app.onehash.ai/")
                }

                for cart_item in cart["cart_details"]["cart"]:
                    if cart_item["upgrade_type"] == "Users":
                        payment_details["quantity"] = cart_item["value"]

                # Redirect the user to this url
                return {"redirect_to": controller.get_payment_url(**payment_details)}
            else:
                # Stripe Subscription Update
                subscription = frappe.get_doc(
                    'Subscription', subscription, ignore_permissions=True)
                subscription_id = subscription.subscription_id
                for plan in subscription.plans:
                    if plan.plan == site.base_plan:
                        subscription_item_id = plan.subscription_item_id

                subscription_details = frappe._dict({
                    "site_name": site_name,
                    "reference_doctype": "Saas Site",
                    "reference_docname": site_name,
                    "subscription_id": subscription_id,
                    "subscription_item_id": subscription_item_id,
                    "plan_id": plan_id,
                    "quantity": cart["cart_details"]["subscribed_users"] - cart["cart_details"]["discounted_users"],
                })

                for cart_item in cart["cart_details"]["cart"]:
                    if cart_item["upgrade_type"] == "Users":
                        subscription_details["quantity"] = cart_item["value"]

                gateway_controller = get_gateway_controller(
                    subscription_details["reference_doctype"], subscription_details["reference_docname"])
                stripe_update_subscription(
                    gateway_controller, subscription_details)

                # Redirect the user to this url
                redirect_url = "https://{0}/app/usage-info".format(site_name)
                return get_redirect_message(_('Subscription Updated'),_('Your Subscription has been successfully updated.'),primary_label="Continue",primary_action=redirect_url)
        except:
            frappe.log_error(frappe.get_traceback())
            return

    # For Razorpay
    else:
        try:
            settings = controller.get_settings({})
            plan_id = cart["plan"].payment_plan_id if cart["plan"] else None
            if not plan_id:
                frappe.throw(_("Please setup Razorpay Plan ID"))

            subscription_details = {
                "plan_id": plan_id,
                "billing_frequency": 1200,
                "customer_notify": 1,
                "quantity": cart["cart_details"]["subscribed_users"] - cart["cart_details"]["discounted_users"]
            }
            addons = []

            for cart_item in cart["cart_details"]["cart"]:
                if cart_item["upgrade_type"] == "Users":
                    subscription_details["quantity"] = cart_item["value"]
                #    addons.append({"item": {"name": cart_item["upgrade_type"], "amount": cart_item["amount"], "currency": "INR"}, "quantity": 1})

            args = {
                "subscription_details": subscription_details,
                # "addons": addons
            }

            if not subscription:

                subscription = controller.setup_subscription(settings, **args)
                payment_details = {
                    "amount": cart["cart_details"]["total"],
                    "title": "OneHash",
                    "description": "Subscription Fee",
                    "reference_doctype": "Saas Site",
                    "reference_docname": site_name,
                    "payer_email": email,
                    "payer_name": frappe.utils.get_fullname(frappe.session.user),
                    "order_id": "",
                    "subscription_id": subscription["subscription_id"],
                    "currency": "INR",
                    "redirect_to": frappe.utils.get_url("https://{0}/app/usage-info".format(site_name) or "https://app.onehash.ai/")
                }

                # Redirect the user to this url
                return {"redirect_to": controller.get_payment_url(**payment_details) + get_razorpay_args(site_name, cart)}

            else:
                subscription_id = frappe.get_doc(
                    'Subscription', subscription, ignore_permissions=True).subscription_id
                controller.update_subscription(settings, subscription_id, **args)

                # Redirect the user to this url
                redirect_url = "https://{0}/app/usage-info".format(site_name)
                return get_redirect_message(_('Subscription Updated'),_('Your Subscription has been successfully updated.'),primary_label="Continue",primary_action=redirect_url)
        except:
            frappe.log_error(frappe.get_traceback(),_("Error while making payment"))
            return

def get_redirect_message(title=_("Subscription Updated"),message=_("Your Subscription has been successfully updated."),primary_label=_("Continue"),primary_action="/",indicator_color="green"):
    redirect_html = '''<script>
	frappe.ready(function() {
			setTimeout(function(){
				window.location.href = "'''+primary_action+'''";
			}, 4000);
		
	})
</script>'''
    return {"redirect_to": frappe.redirect_to_message(_(title), _(message+redirect_html),context={"primary_action":primary_action,"primary_label":primary_label,"title":title})}


@frappe.whitelist(allow_guest=True)
def verify_system_user(site_name, email):
    try:
        site = frappe.get_doc("Saas Site", site_name, ignore_permissions= True)
        for user in site.user_details:
            if user.emai_id == email and user.active == 1 and user.user_type == "System User":
                return True
        return False
    except:
        frappe.log_error('Authorization Failed, Please contact <a href="mailto:support@onehash.ai">support@onehash.ai</a> or your site Administrator.')
        return False

def verify_signature(data):
    return True
    # if frappe.flags.in_test:
    # 	return True
    # signature = frappe.request.headers.get("X-Razorpay-Signature")

    # settings = frappe.get_doc("Membership Settings")
    # key = settings.get_webhook_secret()

    # controller = frappe.get_doc("Razorpay Settings")

    # controller.verify_signature(data, signature, key)

@frappe.whitelist(allow_guest=True)
def razorpay_process_refund(*args, **kwargs):
    request_data = frappe.request.get_data()
    data = frappe._dict(json.loads(request_data))
    frappe.log_error(request_data,data.event+" Webhook Data")
    try:
        verify_signature(data)
    except Exception as e:
        log = frappe.log_error(frappe.get_traceback(), "Webhook Verification Error")
        notify_failure(log)
        return {"status": "Failed", "reason": e}
    if data.event == "refund.created":
        try:
            frappe.set_user("Administrator")
            refund = frappe._dict(data.payload.get("refund", {}).get("entity", {}))
            payment_id = refund.get("payment_id",None)
            refund_amount = refund.get("amount",0)/100
            reference_invoice_no = get_invoice_by_payment_id(payment_id)
            create_credit_note(reference_invoice_no,refund_amount)
            subscription = get_subscription_by_invoice(reference_invoice_no)
            create_refund_payment_entry(subscription,refund.get("id"),reference_invoice=reference_invoice_no,amount = refund_amount)
        except Exception as e:
            log = frappe.log_error(frappe.get_traceback(), "Refund Processing Error")
            notify_failure(log)
            return {"status": "Failed", "reason": e}
    
    return {"status": "Success"}

def get_invoice_by_payment_id(payment_id):
    payment_entry = frappe.get_list("Payment Entry",filters={"reference_no":payment_id},ignore_permissions=True)
    if(len(payment_entry)>0):
        payment_entry_doc = frappe.get_doc("Payment Entry",payment_entry[0].name,ignore_permissions=True)
        reference_invoice = payment_entry_doc.references[0].reference_name
        return reference_invoice
    #return payment_entry.references[0].reference_name
    pass

def create_credit_note(reference_invoice_no,refund_amount):
    from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return
    credit_note_doc = make_sales_return(reference_invoice_no)
    credit_note_doc = extract_tax_from_grand_total(credit_note_doc,refund_amount)
    credit_note_doc.insert(ignore_permissions=True)
    credit_note_doc.submit()
    return credit_note_doc

def extract_tax_from_grand_total(doc,amount):
    tax_rate = 0
    if hasattr(doc, 'taxes'):
        for tax_row in doc.taxes:
            tax_rate += flt(tax_row.rate,3)
    
    base_value = flt(flt(amount)/(1+(tax_rate/100)),2)
    prev_invoice_item_rate = doc.items[0].rate
    prev_invoice_quantity = doc.items[0].qty
    expected_qty = doc.items[0].qty
    multiplier = -1 if expected_qty<0 else 1
    if(doc.items[0].qty!=0):
        revised_rate = flt((base_value/abs(doc.items[0].qty)),3)
    else:
        revised_rate = doc.items[0].rate
    
    if(revised_rate>prev_invoice_item_rate):
        expected_qty = ceil(base_value/prev_invoice_item_rate)*multiplier
        revised_rate = flt((base_value/abs(expected_qty)),3)
    doc.items[0].qty = expected_qty
    doc.items[0].rate = revised_rate

    if(abs(prev_invoice_quantity)<abs(expected_qty) and multiplier==-1):
        doc.items[0].qty = 0

    if(doc.items[0].qty==0):
        doc.items[0].rate=base_value
    
    return doc

@frappe.whitelist(allow_guest=True)
def trigger_razorpay_subscription(*args, **kwargs):

    data = frappe._dict(json.loads(frappe.request.get_data()))
    #data = frappe._dict(json.loads('{"entity":"event","account_id":"acc_GAUOQ9HMzBdaBS","event":"subscription.charged","contains":["subscription","payment"],"payload":{"subscription":{"entity":{"id":"sub_HbVQONzIiATjwQ","entity":"subscription","plan_id":"plan_H2VwfZwFhbePTR","customer_id":"cust_Gu07v3Pxs7Qlix","status":"active","current_start":1626854207,"current_end":1629484200,"ended_at":null,"quantity":7,"notes":[],"charge_at":1629484200,"start_at":1626854207,"end_at":4779887400,"auth_attempts":0,"total_count":1200,"paid_count":1,"customer_notify":true,"created_at":1626854124,"expire_by":null,"short_url":null,"has_scheduled_changes":false,"change_scheduled_at":null,"source":"api","payment_method":"card","offer_id":null,"remaining_count":1199}},"payment":{"entity":{"id":"pay_HbVRqJmbjOX63J","entity":"payment","amount":289100,"currency":"INR","status":"captured","order_id":"order_HbVQPPTiOSWFLw","invoice_id":"inv_HbVQPNWEyHZoKm","international":true,"method":"card","amount_refunded":0,"amount_transferred":0,"refund_status":null,"captured":"1","description":"Subscription Fee","card_id":"card_HbVRqU226tK9lk","card":{"id":"card_HbVRqU226tK9lk","entity":"card","name":"OneHash Technologies Limited","last4":"5100","network":"MC","type":"credit","issuer":null,"international":true,"emi":false,"expiry_month":12,"expiry_year":2034,"sub_type":"consumer","number":"**** **** **** 5100","color":"#25BAC3"},"bank":null,"wallet":null,"vpa":null,"email":"engg.ny14@gmail.com","contact":"+919109911161","customer_id":"cust_Gu07v3Pxs7Qlix","token_id":null,"notes":{"site_name":"indiatest14.onehash.ai","token":"97cc31f171"},"fee":13305,"tax":2030,"error_code":null,"error_description":null,"acquirer_data":{"auth_code":"773718"},"created_at":1626854207}}},"created_at":1626854277}'))
    #frappe.log_error(frappe.request.get_data(),data.event+" Webhook Data")
    #return {"status": "Success"}
    try:
        verify_signature(data)
    except Exception as e:
        log = frappe.log_error(frappe.get_traceback(), "Webhook Verification Error")
        notify_failure(log)
        return {"status": "Failed", "reason": e}

    ## Send Email to Customer
    #send_email_to_customer(data)
    # Subscription Charged or Updated
    if data.event == "subscription.charged" or data.event == "subscription.updated":
        try:
            update_razorpay_subscription(data)
        except Exception as e:
            log = frappe.log_error(frappe.get_traceback(), "Subscription Charged/Update Error")
            notify_failure(log)
            return {"status": "Failed", "reason": e}
    # Subscription Cancelled
    elif data.event == "subscription.cancelled":
        try:
            cancel_subscription_razorpay(data)
        except Exception as e:
            log = frappe.log_error(
                frappe.get_traceback(), "Subscription Cancel Error")
            notify_failure(log)
            return {"status": "Failed", "reason": e}
    
    return {"status": "Success"}

@frappe.whitelist(allow_guest=True)
def razorpay_mid_upgrade_handler(*args, **kwargs):
    data = frappe._dict(json.loads(frappe.request.get_data()))
    try:
        verify_signature(data)
    except Exception as e:
        frappe.log_error(frappe.request.get_data(),data.event+" Webhook Data")
        log = frappe.log_error(frappe.get_traceback(), "Webhook Verification Error")
        notify_failure(log)
        return {"status": "Failed", "reason": e}
    if data.event == "invoice.paid":
        try:
            payment = frappe._dict(data.payload.get("payment", {}).get("entity", {}))
            invoice = frappe._dict(data.payload.get("invoice", {}).get("entity", {}))
            notes = invoice.get("notes",{})
            invoice_type = notes.get("type",None) if "type" in notes else None
            subscription_id = invoice.get('subscription_id',None)
            paid_amount = payment.get("amount",0)/100
            payment_currency = payment.get("currency")
            if(invoice_type =="upgrade"):
                subscription = get_subscription_by_pg_subscription_id(subscription_id)
                if not subscription:
                    frappe.throw(_("Subscription is mandatory was generating invoice."))
                invoice  = create_upgrade_invoice(paid_amount,subscription,payment_currency)
                create_payment_entry(subscription.name,payment.get("id"),invoice.name)
                subscription.append('invoices', {
                    'document_type': "Sales Invoice",
                    'invoice': invoice.name
                })
                subscription.save(ignore_permissions=True)
        except Exception as e:
            log = frappe.log_error(frappe.get_traceback(), "Upgrade Invoice Error")
            notify_failure(log)
            return {"status": "Failed", "reason": e}
    
    return {"status": "Success"}

@frappe.whitelist(allow_guest=True)
def stripe_mid_upgrade_handler(*args, **kwargs):
    data = frappe._dict(json.loads(frappe.request.get_data()))
    
    if data.type in ['invoice.payment_succeeded']:
        try:
            invoice = data.get("data",{}).get("object",{})
            billing_reason = invoice.get("billing_reason",None)
            paid_amount = invoice.get("amount_paid",0)/100
            invoice_total = invoice.get("total",0)/100
            payment_currency = (invoice.get("currency")).upper()
            subscription_id = invoice.get("subscription")
            payment_id = invoice.get("charge")
            if(billing_reason =="subscription_update"):
                subscription = get_subscription_by_pg_subscription_id(subscription_id)
                if not subscription:
                    frappe.throw(_("Subscription is mandatory was generating invoice."))

                if paid_amount>0:
                    upgrade_invoice  = create_upgrade_invoice(paid_amount,subscription,payment_currency)
                    subscription.append('invoices', {
                    'document_type': "Sales Invoice",
                    'invoice': upgrade_invoice.name
                    })
                    subscription.save(ignore_permissions=True)
                    create_payment_entry(subscription.name,payment_id,upgrade_invoice.name)
                    
                elif invoice_total<0:
                    frappe.set_user("Administrator")
                    payment_id = invoice.get("id")
                    stripe_customer_id = invoice.get("customer")
                    reference_invoice_no = (subscription.invoices[-1]).get("invoice")
                    create_credit_note(reference_invoice_no,abs(invoice_total))
                    create_refund_payment_entry(subscription.name,payment_id,reference_invoice_no,abs(invoice_total))
                    charge_id = get_reference_charge_id(subscription,reference_invoice_no,abs(invoice_total))
                    create_refund_on_stripe(subscription,abs(invoice.get("total")),payment_currency,stripe_customer_id,charge_id)
        except Exception as e:
            log = frappe.log_error(frappe.get_traceback(), "Stripe Payment Update Failure")
            notify_failure(log)
            return {"status": "Failed", "reason": e}
        return {"status": "Success"}


def get_reference_charge_id(subscription,reference_invoice_no,refund_amount):
    '''
        Retrieve payment entry associated with the reference Invoice
    '''
    invoice = frappe.get_doc("Sales Invoice",reference_invoice_no)
    if(invoice.grand_total>refund_amount):
        #eligible invoice for refund
        payment_entry = frappe.get_list("Payment Entry",filters=[["Payment Entry Reference","reference_name","=",reference_invoice_no],["Payment Entry","payment_type","=","Receive"]],fields=["name","reference_no"])
        if(len(payment_entry)>0):
            reference_no = payment_entry[0].reference_no
            if(reference_no[:3]=="ch_"):
                return reference_no
            else:
                subscription_plan = subscription.get("plans")[0]
                plan = get_base_plan_details(subscription_plan.plan)
                plan_id = plan.payment_plan_id
                gateway_controller = frappe.get_value(
                    "Payment Gateway Account", plan.payment_gateway, "payment_gateway")
                controller = get_payment_gateway_controller(gateway_controller)
                subscription_id = subscription.subscription_id
                try:
                    subscription_item_id = subscription_plan.subscription_item_id
                    subscription_details = frappe._dict({
                        "site_name": subscription.reference_site,
                        "reference_doctype": "Saas Site",
                        "reference_docname": subscription.reference_site,
                        "subscription_id": subscription_id,
                        "invoice_id": reference_no,
                        "subscription_item_id": subscription_item_id,
                        "plan_id": plan_id
                    })
                    gateway_controller = get_gateway_controller(subscription_details["reference_doctype"], subscription_details["reference_docname"])
                    invoice =retrieve_stripe_invoice(gateway_controller, subscription_details)
                    return invoice.get("charge")
                except:
                    frappe.log_error(frappe.get_traceback(),"Stripe Reteirve charge id Error")
                    return
    else:
        # Add logic to retireve the payment entry for the customer
        pass        

def create_refund_on_stripe(subscription,refund_amt,payment_currency,stripe_customer_id,charge_id):
    subscription_plan = subscription.get("plans")[0]
    plan = get_base_plan_details(subscription_plan.plan)
    plan_id = plan.payment_plan_id
    gateway_controller = frappe.get_value(
        "Payment Gateway Account", plan.payment_gateway, "payment_gateway")
    controller = get_payment_gateway_controller(gateway_controller)
    subscription_id = subscription.subscription_id
    try:
        subscription_item_id = subscription_plan.subscription_item_id
        subscription_details = frappe._dict({
            "site_name": subscription.reference_site,
            "reference_doctype": "Saas Site",
            "reference_docname": subscription.reference_site,
            "subscription_id": subscription_id,
            "charge_id": charge_id,
            "subscription_item_id": subscription_item_id,
            "amount":refund_amt,
            "plan_id": plan_id,
            "currency":payment_currency,
            "customer":stripe_customer_id
        })
        gateway_controller = get_gateway_controller(subscription_details["reference_doctype"], subscription_details["reference_docname"])
        return create_stripe_refund(gateway_controller, subscription_details)
    except:
        frappe.log_error(frappe.get_traceback(),"Stripe Subscription Cancellation Error")
        return

def get_subscription_by_pg_subscription_id(pg_subscription_id):
    """ 
    Retrieves subscription object based on the payment gateway subscription id
    """
    subscription_list = frappe.get_list("Subscription",filters = {"subscription_id":pg_subscription_id},ignore_permissions=True)
    if(len(subscription_list)>0):
        return frappe.get_doc("Subscription",subscription_list[0].name)
    return None

def create_upgrade_invoice(paid_amount,subscription,invoice_currency):
    """
    Creates a `Invoice`, submits it and returns it
    """
    from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import get_accounting_dimensions
    from erpnext import get_default_company

    
    doctype = 'Sales Invoice'
    invoice = frappe.new_doc(doctype)
    invoice.currency= invoice_currency
    # For backward compatibility
    # Earlier subscription didn't had any company field
    company = subscription.get('company') or get_default_company()
    if not company:
        frappe.throw(_("Company is mandatory was generating invoice. Please set default company in Global Defaults"))

    invoice.company = company
    invoice.set_posting_time = 1
    invoice.posting_date = subscription.current_invoice_start if subscription.generate_invoice_at_period_start \
        else subscription.current_invoice_end

    invoice.cost_center = subscription.cost_center
    invoice.customer = subscription.party
    
    ## Add dimensions in invoice for subscription:
    accounting_dimensions = get_accounting_dimensions()

    for dimension in accounting_dimensions:
        if subscription.get(dimension):
            invoice.update({
                dimension: subscription.get(dimension)
            })

    # Subscription is better suited for service items. I won't update `update_stock`
    # for that reason
    items_list = subscription.get_items_from_plans(subscription.plans)
    for item in items_list:
        item['cost_center'] = subscription.cost_center
        invoice.append('items', item)

    # Taxes
    tax_template = subscription.sales_tax_template
    
    if tax_template:
        invoice.taxes_and_charges = tax_template
        invoice.set_taxes()

    # Subscription period
    invoice.from_date = subscription.current_invoice_start
    invoice.to_date = subscription.current_invoice_end
    invoice = extract_tax_from_grand_total(invoice,paid_amount)
    invoice.flags.ignore_mandatory = True
    invoice.flags.ignore_permissions = True
    invoice.save()
    invoice.submit()
    return invoice

def get_customer_from_site(site_name,currency=None):
    saas_user = frappe.get_list('Saas User', filters={'linked_saas_site': site_name}, ignore_permissions=True)[0].name
    saas_user = frappe.get_doc('Saas User', saas_user)
    saas_user_email = saas_user.email
    currency = saas_user.currency
    customer = frappe.get_list('Customer', filters={'email_id': saas_user_email}, ignore_permissions=True)
    if customer:
        customer_name = customer[0].name
    else:
        lead = frappe.get_list('Lead', filters={'email_id': saas_user_email}, ignore_permissions=True)
        if not len(lead)>0:
            lead = frappe.new_doc('Lead')
            lead.email_id = saas_user.email
            lead.lead_name = "{} {}".format(saas_user.first_name, saas_user.last_name)
            lead.insert(ignore_permissions=True)
        else: 
            lead = frappe.get_doc("Lead",lead[0].name, ignore_permissions=True)
        
        try:
            cur_user = frappe.session.user
            frappe.set_user("Administrator")

            customer = make_customer(lead.name)
            #customer.default_currency = currency
            customer.insert(ignore_permissions=True)
            customer_name = customer.name

            frappe.set_user(cur_user)
        except:
            frappe.log_error(frappe.get_traceback(), 'Make Customer Error')
    return customer_name


def cancel_subscription_razorpay(data):
    subscription = frappe._dict(data.payload.get("subscription", {}).get("entity", {}))
    
    subscription = frappe.get_list("Subscription", filters= {'subscription_id': subscription.id}, ignore_permissions=True)
    if not len(subscription)>0:
        frappe.throw("Subscription you are looking for does not exist.")
    subscription = frappe.get_doc("Subscription", subscription[0].name, ignore_permissions=True)
    saas_site = frappe.get_doc("Saas Site", subscription.reference_site, ignore_permissions=True)
    
    subscription.cancel_at_period_end = True
    subscription.save(ignore_permissions=True)

    saas_site.subscription = ''
    saas_site.save(ignore_permissions=True)

    subscription.cancel_subscription()
    disable_enable_site(saas_site.name, saas_site.site_status)


def update_razorpay_subscription(data):
    subscription_data = get_razorpay_subscription_data(data)
    site = frappe.get_doc("Saas Site", subscription_data.site_name, ignore_permissions=True)
    if not site.customer:
        site.customer = get_customer_from_site(site.site_name,"INR")
        site.save(ignore_permissions=True)

    ## Subscription Renewed
    renewal_date = subscription_data.renewal_date
    expiry_date = subscription_data.expiry_date
    quantity = subscription_data.quantity + site.discounted_users  # Discounted Users Added
    
    ## Saas Site Updated Limits
    site_data = frappe._dict({})
    site_data["limit_for_users"] = quantity
    site_data["expiry"] = expiry_date

    subscription_name = update_site_subscription(site.site_name, site.customer, site.base_plan, quantity, subscription_data.id, '', renewal_date, expiry_date)
    update_saas_site(site, site_data, subscription_name)
    if(data.event == "subscription.charged"):
        create_payment_entry(subscription_name, subscription_data.payment_id)


def update_site_subscription(site_name, customer, base_plan, qty, subscription_id, subscription_item_id, start_date, end_date):
    try:
        subscription_name = frappe.get_doc(
            'Saas Site', site_name, ignore_permissions=True).subscription
        if not subscription_name:
            subscription = frappe.new_doc('Subscription')
            subscription.subscription_id = subscription_id
            subscription.reference_site = site_name
            subscription.party_type = 'Customer'
            subscription.party = customer
            subscription.current_invoice_start = start_date
            subscription.current_invoice_end = end_date
            subscription.cancel_at_period_end = False
            subscription.generate_invoice_at_period_start = True
            subscription.append('plans', {'plan': base_plan, 'qty': qty, 'subscription_item_id': subscription_item_id})
            subscription.sales_tax_template = frappe.db.get_value("Subscription Plan", base_plan, "sales_taxes_and_charges_template")
            subscription.company = frappe.db.get_value("Subscription Plan", base_plan, "default_company")
            subscription.insert(ignore_permissions=True)
            frappe.db.commit()
        else:
            subscription = frappe.get_doc('Subscription', subscription_name, ignore_permissions=True)
            for subscription_plan in subscription.plans:
                if subscription_plan.plan == base_plan:
                    subscription_plan.qty = qty
            subscription.save(ignore_permissions=True)
            frappe.db.commit()

        frappe.set_user("Administrator")
        get_subscription_updates(subscription.name)

        return subscription.name

    except Exception as e:
        log = frappe.log_error(frappe.get_traceback(),"Subscription Create Error")
        notify_failure(log)
        return {"status": "Failed", "reason": e}

def get_subscription_by_invoice(reference_invoice_no):
    subscription = frappe.get_list("Subscription",filters=[["Subscription Invoice","invoice","=",reference_invoice_no]])
    if(len(subscription)>0):
        return subscription[0].name
    else:
        return None

def create_payment_entry(subscription_name, payment_id,reference_invoice=None,amount=None):
    subscription = frappe.get_doc("Subscription", subscription_name, ignore_permissions=True)
    invoice = reference_invoice if reference_invoice else subscription.invoices[-1].invoice
    sales_invoice = frappe.get_doc("Sales Invoice", invoice, ignore_permissions=True)

    base_plan = frappe.get_value("Saas Site", subscription.reference_site, "base_plan")
    payment_gateway = get_base_plan_details(base_plan).payment_gateway
    payment_account = frappe.get_value("Payment Gateway Account", payment_gateway, "payment_account")

    from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
    frappe.flags.ignore_account_permission = True
    bank_amount = flt(amount) if amount else sales_invoice.grand_total
    pe = get_payment_entry(dt="Sales Invoice", dn=sales_invoice.name, bank_amount=bank_amount)
    frappe.flags.ignore_account_permission=False
    pe.paid_to = payment_account
    pe.payment_type = "Receive"
    #pe.paid_amount = bank_amount
    pe.received_amount = pe.paid_amount/pe.target_exchange_rate
    pe.reference_no = payment_id
    pe.reference_date = getdate()
    pe.save(ignore_permissions=True)
    frappe.set_user("Administrator")
    if(abs(pe.difference_amount)<1):
        pe.paid_amount = pe.paid_amount - pe.difference_amount
        pe.save(ignore_permissions=True)
    frappe.flags.ignore_permissions=True
    pe.submit()


def create_refund_payment_entry(subscription_name, payment_id,reference_invoice=None,amount=None):
    subscription = frappe.get_doc("Subscription", subscription_name, ignore_permissions=True)
    invoice = reference_invoice if reference_invoice else subscription.invoices[0].invoice
    sales_invoice = frappe.get_doc("Sales Invoice", invoice, ignore_permissions=True)

    base_plan = frappe.get_value("Saas Site", subscription.reference_site, "base_plan")
    payment_gateway = get_base_plan_details(base_plan).payment_gateway
    payment_account = frappe.get_value("Payment Gateway Account", payment_gateway, "payment_account")

    from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry,get_negative_outstanding_invoices
    frappe.flags.ignore_account_permission = True
    bank_amount = flt(amount) if amount else sales_invoice.grand_total
    pe = get_payment_entry(dt="Sales Invoice", dn=sales_invoice.name, bank_amount=bank_amount)
    frappe.flags.ignore_account_permission=False
    pe.paid_from = payment_account
    pe.payment_type = "Pay"
    pe.paid_amount = bank_amount
    pe.received_amount = pe.paid_amount/pe.target_exchange_rate
    pe.reference_no = payment_id
    pe.reference_date = getdate()
    outstanding_amount_diff = sales_invoice.outstanding_amount+pe.paid_amount
    if(abs(outstanding_amount_diff)<1):
        pe.paid_amount = pe.paid_amount - outstanding_amount_diff
        pe.received_amount = pe.paid_amount/pe.target_exchange_rate

    # Negative Account Balance
    #get_negative_outstanding_invoices(pe.party_type,pe.paid_to,pe.company,pe.paid_to_account_currency,pe.paid_from_)
    frappe.flags.ignore_permissions=True
    pe.save(ignore_permissions=True)
    if(pe.difference_amount and abs(pe.difference_amount)<1):
        pe.paid_amount = pe.paid_amount - pe.difference_amount
        pe.save(ignore_permissions=True)
        # pe.save(ignore_permissions=True)
    pe.submit()


def update_saas_site(doc, data, subscription_name):
    doc.limit_for_users = data.limit_for_users
    doc.expiry = data.expiry
    doc.subscription = subscription_name
    doc.save(ignore_permissions=True)
    #frappe.db.commit()

    apply_new_limits(doc.limit_for_users, doc.limit_for_emails, doc.limit_for_space, doc.limit_for_email_group, doc.expiry, doc.site_name)


def get_razorpay_subscription_data(data):
    subscription = frappe._dict(data.payload.get("subscription", {}).get("entity", {}))
    payment = frappe._dict(data.payload.get("payment", {}).get("entity", {}))
    notes = frappe._dict(data.payload.get("payment", {}).get("entity", {}).get("notes", {}))

    subscription_data = frappe._dict({})
    subscription_data["addon"] = frappe._dict({})

    if subscription:
        subscription_data['id'] = subscription.id
        subscription_data["subscription_item_id"] = ''
        subscription_data['plan_id'] = subscription.plan_id
        subscription_data["quantity"] = subscription.quantity
        subscription_data["renewal_date"] = datetime.datetime.fromtimestamp(
            subscription.current_start).strftime("%Y-%m-%d")
        subscription_data["expiry_date"] = datetime.datetime.fromtimestamp(
            subscription.current_end).strftime("%Y-%m-%d")
    if payment:
        subscription_data['payment_id'] = payment.id
    if notes:
        for key in notes:
            if (key in ["finrich", "profile_enrich"]):
                subscription_data["addon"][key] = notes[key]
            else:
                subscription_data[key] = notes[key]
        # TODO change addon services list to dynamic list

    # For Upgrade & Monthly Payments
    if not notes.site_name:
        subscription_doc = frappe.get_list('Subscription', filters={
                                           'subscription_id': subscription.id}, ignore_permissions=True)[0].name
        site_name = frappe.get_list('Saas Site', filters=dict(subscription=subscription_doc))[0].name
        subscription_data["site_name"] = site_name

    return subscription_data


def get_razorpay_args(site_name, cart):
    args = '&site_name=' + site_name
    for cart_item in cart["cart_details"]["cart"]:
        if cart_item["upgrade_type"] not in ["Subscription", "Users"]:
            addon, qty = cart_item["upgrade_type"], str(cart_item["value"])
            args += '&{addon}={qty}'
    return args


def notify_failure(log):
    try:
        content = """
			Dear System Manager,
			Razorpay webhook for subscription failed due to some reason.
			Please check the following error log linked below
			Error Log: {0}
			Regards, Administrator
		""".format(get_link_to_form("Error Log", log.name))

        sendmail_to_system_managers(
            "[Important] [OneHash] Razorpay membership webhook failed , please check.", content)
    except:
        pass


@frappe.whitelist(allow_guest=True)
def trigger_stripe_subscription(*args, **kwargs):
    data = frappe._dict(json.loads(frappe.request.get_data()))

    # Subscription Charged/Updated/Canceled
    if data.type in ['customer.subscription.created', 'customer.subscription.updated', 'customer.subscription.deleted']:
        try:
            ## Send Email to Customer
            #send_email_to_customer(data)
            
            ## Update Subscription
            update_stripe_subscription(data)
        except Exception as e:
            log = frappe.log_error(frappe.get_traceback(), "Subscription Charge/Update/Cancel Error")
            notify_failure(log)
            return {"status": "Failed", "reason": e}
        return {"status": "Success"}


def update_stripe_subscription(data):
    subscription_data = get_stripe_subscription_data(data)

    site = frappe.get_doc(
        "Saas Site", subscription_data.site_name, ignore_permissions=True)

    if not site.customer:
        site.customer = get_customer_from_site(site.site_name,"USD")
        site.save(ignore_permissions=True)

    # Subscription Created/Updated
    if data.type in ['customer.subscription.created', 'customer.subscription.updated']:
        ## Subscription Renewed
        renewal_date = subscription_data.renewal_date
        expiry_date = subscription_data.expiry_date
        quantity = subscription_data.quantity + site.discounted_users  # Discounted Users Added
        payment_id = subscription_data.payment_id
        
        ## Saas Site Updated Limits
        site_data = frappe._dict({})
        site_data["limit_for_users"] = quantity
        site_data["expiry"] = expiry_date

        subscription_name = update_site_subscription(site.site_name, site.customer, site.base_plan, quantity, subscription_data.id, subscription_data.subscription_item_id, renewal_date, expiry_date)
        update_saas_site(site, site_data, subscription_name)
        if(data.type=="customer.subscription.created"):
            create_payment_entry(subscription_name, payment_id)
    
    ## Subscription Cancelled
    elif data.type == 'customer.subscription.deleted':
        subscription = frappe.get_doc("Subscription", site.subscription, ignore_permissions=True)
        
        subscription.cancel_at_period_end = True
        subscription.save(ignore_permissions=True)
        
        site.subscription = ''
        site.save(ignore_permissions=True)
        
        subscription.cancel_subscription()
        disable_enable_site(site.name, site.site_status)


def get_stripe_subscription_data(data):
    subscription = frappe._dict(data.get("data", {}).get("object", {}))
    subscription_item = frappe._dict(data.get("data", {}).get("object", {}).get("items", {}))["data"][0]

    subscription_data = frappe._dict({})

    if subscription:
        subscription_data['id'] = subscription.id
        subscription_data["subscription_item_id"] = subscription_item["id"]
        subscription_data['plan_id'] = subscription_item["plan"]["id"]
        subscription_data["quantity"] = subscription_item["quantity"]
        subscription_data["payment_id"] = subscription["latest_invoice"]
        subscription_data["site_name"] = subscription.metadata["site_name"]
        subscription_data["renewal_date"] = datetime.datetime.fromtimestamp(
            subscription.current_period_start).strftime("%Y-%m-%d")
        subscription_data["expiry_date"] = datetime.datetime.fromtimestamp(
            subscription.current_period_end).strftime("%Y-%m-%d")
    return subscription_data


def send_email_to_customer(data):
    try:
        if data.type:
            subscription_data = get_stripe_subscription_data(data)
            subscritpion_event = data.type
        elif data.event:
            subscription_data = get_razorpay_subscription_data(data)
            subscritpion_event = data.event

        site = frappe.get_list("Saas User", filters={'linked_saas_site': subscription_data.site_name})[0].name
        site_user = frappe.get_doc("Saas User", site, ignore_permissions=True)
        saas_site = frappe.get_doc("Saas Site", site_user.linked_saas_site, ignore_permissions=True)
        STANDARD_USERS = ("Guest", "Administrator")

        if subscritpion_event in ['customer.subscription.created', "subscription.charged"]:
            subject="Subscription Started with OneHash"
            template="subscription_created_email"
            
        elif subscritpion_event in ['customer.subscription.updated', 'subscription.updated']:
            subject="Subscription Updated with OneHash"
            template="subscription_updated_email"
            
        elif subscritpion_event in ['customer.subscription.deleted', 'subscription.cancelled']:
            subject="Subscription Cancelled with OneHash"
            template="subscription_cancelled_email"
            
        args = {
                    'name': site_user.first_name or site_user.last_name or "user",
                    'user': site_user.email,
                    'subscription_id': subscription_data.id,
                    'subscription_plan': saas_site.base_plan,
                    'previous_user_count': saas_site.limit_for_users + saas_site.discounted_users,
                    'user_count': subscription_data.quantity + saas_site.discounted_users,
                    'start_date': format_date(subscription_data.renewal_date, 'dd-MM-yyyy'),
                    'renewal_date': format_date(subscription_data.renewal_date, 'dd-MM-yyyy'),
                    'next_due_date': format_date(subscription_data.expiry_date, 'dd-MM-yyyy'),
                    'ending_date': format_date(subscription_data.expiry_date, 'dd-MM-yyyy'),
                    'cancellation_date': format_date(getdate(), 'dd-MM-yyyy'),
                    'site_expiry_date': format_date(saas_site.expiry, 'dd-MM-yyyy'),
                    'site': site_user.linked_saas_site,
                    'site_url': "https://"+site_user.linked_saas_site,
                    'help_url':"https://help.onehash.ai",
                    'user_fullname': site_user.first_name+" "+site_user.last_name
                }
        sender = frappe.session.user not in STANDARD_USERS and get_formatted_email(frappe.session.user) or None
        frappe.sendmail(recipients=site_user.email, sender=sender, subject=subject,template=template, args=args, header=[subject, "green"],delayed=False)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(),"Email Alert Error")
    return 