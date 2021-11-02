from __future__ import unicode_literals
import frappe
import json
import datetime
from six import string_types
from frappe import _
from frappe.utils import format_date, flt
from frappe.utils.data import (cint, global_date_format, getdate, nowdate, add_days, add_to_date, add_months, date_diff, flt, get_date_str, get_first_day, get_last_day)
from frappe.sessions import get_geo_ip_country
from frappe.geo.country_info import get_country_timezone_info
from frappe.integrations.utils import get_payment_gateway_controller
from better_saas.better_saas.doctype.saas_user.saas_user import apply_new_limits
from erpnext.accounts.doctype.subscription.subscription import get_subscription_updates
from erpnext.erpnext_integrations.stripe_integration import stripe_update_subscription
from frappe.integrations.doctype.stripe_settings.stripe_settings import get_gateway_controller
from erpnext.crm.doctype.lead.lead import make_customer
from journeys.addon_limits import update_limits


def get_context(context):
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
def get_addon():
    return frappe.get_all("Saas AddOn", filters={"disabled": 0, "is_a_subscription": 0}, fields=['*'])
    

@frappe.whitelist(allow_guest=True)
def buy(site_name=None,cart=[],currency="USD",**kwargs):
    saas_settings = frappe.get_doc("Saas Settings")
    tax_rates = [saas_settings.default_tax_rate_id_stripe] if currency=="INR" and saas_settings.default_tax_rate_id_stripe else []
    payment_gateway = saas_settings.default_payment_gateway_india if currency=="INR" else saas_settings.default_payment_gateway_international
    data = {}
    data["cancel_url"] = kwargs["cancel_url"] if "cancel_url" in kwargs else "https://onehash.ai"
    data["gateway_controller"] = frappe.db.get_value("Payment Gateway", payment_gateway, "gateway_controller")
    data["line_items"]=[]
    for item in json.loads(cart):
        data["line_items"].append({
          'price_data': {
            'currency': item["currency"],
            'product_data': {
              'name': item["name"],
              'description': item["name"]
            },
            'unit_amount': cint(flt(item["rate"])*100),
          },
          'quantity': item["qty"],
          'tax_rates': tax_rates
        })
    data["site_name"] = None
    data["metadata"]={}
    if(site_name):
        data["site_name"] = site_name
        data["metadata"]["site_name"]=site_name
    data["address_at_checkout"] = "auto"
    data["success_url"] = "https://{}/checkout_success".format(frappe.conf.get("master_site_domain"))+"?session_id={CHECKOUT_SESSION_ID}&type=add-on&currency="+currency
    checkout_session = create_checkout_session_stripe(frappe._dict(data))
    return {"redirect_to":checkout_session.url}

def create_checkout_session_stripe(data):
    import stripe
    stripe_controller = frappe.get_doc("Stripe Settings",data.gateway_controller)
    stripe.api_key = stripe_controller.get_password(fieldname="secret_key", raise_exception=False)
    checkout_session = stripe.checkout.Session.create(
      success_url=data["success_url"],
      cancel_url=data["cancel_url"],
      payment_method_types=["card"],
      billing_address_collection='required' if data["address_at_checkout"] else 'auto',
      line_items=data["line_items"],
      mode="payment",
      metadata = data["metadata"],
      payment_intent_data = {"metadata":data["metadata"]}
      
    )
    return checkout_session

@frappe.whitelist(allow_guest=True)
def get_site_details(site_name, email, onehash_partner):
    site = frappe.get_doc("Saas Site", site_name)
    plan = get_base_plan_details(site.base_plan)
    addons = get_addon_plans(plan.currency)
    return {"site": site, "plan": plan, "addons": addons}

def get_addon_plans(currency):
    addons = frappe.get_all("Saas AddOn", filters={"disabled": 0, "currency": currency, "is_a_subscription": 0}, fields=[
                            "addon_name", "name", "per_credit_price", "addon_type", "addon_value", "currency"])
    result_addon = {}
    for addon in addons:
        result_addon[addon.addon_type] = addon
    return result_addon

def get_base_plan_details(plan_name):
    return frappe.get_doc("Subscription Plan", plan_name)


@frappe.whitelist(allow_guest=True)
def get_cart_details(site_name, email, onehash_partner, cart):
    site_details = get_site_details(site_name, email, onehash_partner)
    return get_cart_value(site_details, cart)


def get_cart_value(site_details, cart):
    cart = json.loads(cart)
    site_data = site_details
    cart_details = {}
    cart_details["cart"] = []
    cart_amount = 0
    addons = site_data["addons"]
    plan = site_data["plan"]

    for key, addon in addons.items():
        if (key in cart and cart[key] != 0):
            item_amount = flt(cart[key]*addon["per_credit_price"]/flt(addon["addon_value"]))
            cart_amount = cart_amount + item_amount
            cart_item = {
                "upgrade_type": key,
                "value": cart[key],
                "amount": item_amount,
                "amount_to_display": frappe.format_value(item_amount, {"fieldtype": "Currency", "currency": addon["currency"]})
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
    cart_details["total_to_display"] = frappe.format_value(
        cart_amount, {"fieldtype": "Currency", "currency": plan.currency})
    cart_details["payment_gateway"] = frappe.get_value(
        "Payment Gateway Account", plan.payment_gateway, "payment_gateway")
    return {"cart_details": cart_details, "addons": addons, "plan": plan, "site_data": site_data}
    

@frappe.whitelist(allow_guest=True)
def pay(site_name, email, onehash_partner, cart):
    cart = get_cart_details(site_name, email, onehash_partner, cart)
    gateway_controller = cart["cart_details"]["payment_gateway"] if "payment_gateway" in cart["cart_details"] else "Razorpay"
    controller = get_payment_gateway_controller(gateway_controller)
    
    if not email:
        email = frappe.get_value("Saas User", {"linked_saas_site": site_name}, "email")
    
    if cart["cart_details"]["total"] <= 0:
        frappe.throw(_("Can not process Zero Amount"))

    try:
        site = frappe.get_doc('Saas Site', site_name, ignore_permissions=True)
        subscription = site.subscription
    except Exception as e:
        log = frappe.log_error(frappe.get_traceback(), "Subscription Fetching Error")

    metadata = frappe._dict({})
    metadata["site"] = site_name

    for cart_item in cart["cart_details"]["cart"]:
        metadata[cart_item["upgrade_type"]] = cart_item["value"]

    # For Stripe
    if 'Stripe' in controller.name:
        payment_details = {
            "amount": cart["cart_details"]["total"] + cart["cart_details"]["total_tax"],
            "title": "OneHash",
            "description": "Addon Charges",
            "reference_doctype": "Saas Site",
            "reference_docname": site_name,
            "payer_email": email,
            "payer_name": frappe.utils.get_fullname(frappe.session.user),
            "order_id": '',
            "metadata": metadata,
            "currency": cart["plan"].currency,
            "redirect_to": frappe.utils.get_url("https://{}/".format(site_name) or "https://app.onehash.ai/")
        }
        
        # Redirect the user to this url
        return {"redirect_to": controller.get_payment_url(**payment_details)}

    # For Razorpay
    else:
        try:
            addons = []

            for cart_item in cart["cart_details"]["cart"]:
                addons.append({"item": {"name": cart_item["upgrade_type"], "amount": cart_item["amount"], "currency": "INR"}, "quantity": 1})

            args = {
                "addons": addons
            }

            notes = frappe._dict({})
            for addon in addons:
                key = addon["item"]["name"]
                value = addon["item"]["amount"]
                notes[key] = int(value)

            payment_details = {
                "amount": cart["cart_details"]["total"] + cart["cart_details"]["total_tax"],
                "title": "OneHash",
                "description": "Addon Charges",
                "reference_doctype": "Saas Site",
                "reference_docname": site_name,
                "payer_email": email,
                "payer_name": frappe.utils.get_fullname(frappe.session.user),
                "order_id": '',
                "currency": cart["plan"].currency,
                "redirect_to": frappe.utils.get_url("https://{}/".format(site_name) or "https://app.onehash.ai/")
            }

            # Redirect the user to this url
            return {"redirect_to": controller.get_payment_url(**payment_details)+ get_razorpay_args(site_name,cart)} 
        except:
            frappe.log_error(frappe.get_traceback())


def get_razorpay_args(site_name, cart):
    args = '&site_name='+ site_name
    for cart_item in cart["cart_details"]["cart"]:
        addon , qty = cart_item["upgrade_type"], str(cart_item["value"])
        args += f'&{addon}={qty}'
    return args

@frappe.whitelist(allow_guest=True)
def razorpay_addon_webhook_response(*args, **kwargs):
    data = frappe._dict(json.loads(frappe.request.get_data()))
    if(data.event) == "payment.captured":
        try:
            razorpay_update_addons_on_saas_site(data)
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Addon Update Error")
            return {"status": "Failed", "reason": e}
    return {"status":"Success"}

def razorpay_update_addons_on_saas_site(data):
    payment_id = frappe._dict(data.payload.get("payment", {}).get("entity", {})).id
    notes = frappe._dict(data.payload.get("payment", {}).get("entity", {}).get("notes", {}))
    if notes.site_name:
        site_name = notes.site_name
    site = frappe.get_doc("Saas Site", notes.site_name)
    currency = frappe.get_doc("Subscription Plan", site.base_plan).currency
    # Update Saas Site Credits
    update_addon_credits(site, notes, currency)
    create_invoice_and_payment_entry(site, notes, currency, payment_id)


@frappe.whitelist(allow_guest=True)
def stripe_addon_webhook_response(*args, **kwargs):
    data = frappe._dict(json.loads(frappe.request.get_data()))
    if(data.type) == "charge.succeeded":
        try:
            stripe_update_addons_on_saas_site(data)
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Addon Update Error")
            return {"status": "Failed", "reason": e}
    return {"status":"Success"}

def stripe_update_addons_on_saas_site(data):
    charge_id = frappe._dict(data.get("data", {}).get("object",{})).id
    metadata = frappe._dict(data.get("data", {}).get("object",{})).metadata
    site_name = metadata["site"]
    site = frappe.get_doc("Saas Site", site_name, ignore_permissions=True)
    currency = frappe.get_doc("Subscription Plan", site.base_plan).currency
    # Update Saas Site Credits
    update_addon_credits(site, metadata, currency)
    update_site_credits(site.name)
    create_invoice_and_payment_entry(site, metadata, currency, charge_id)

def update_addon_credits(site, addons, currency):
    for addon_type in addons:
        if addon_type == "Emails":
            site.limit_for_emails += int(addons[addon_type])
            site.save(ignore_permissions=True)
        elif addon_type == "Space":
            site.limit_for_space += int(addons[addon_type])
            site.save(ignore_permissions=True)
        elif not addon_type in ["site", "site_name", "token"]:
            update_addon_credits_child_table(site, addon_type, int(addons[addon_type]), currency)

@frappe.whitelist(allow_guest=True)
def update_site_credits(site_name):
    site = frappe.get_doc("Saas Site", site_name, ignore_permissions=True)

    ## Apply New Limits on Saas Site
    apply_new_limits(site.limit_for_users, site.limit_for_emails, site.limit_for_space, site.limit_for_email_group, site.expiry, site.site_name)
    # return update_addon_limits(site.addon_limits, site.site_name)

def update_addon_limits(addon_limits,site_name):
    limit_dict = frappe._dict({})
    for limit in addon_limits:
        limit_dict[limit.get("service_name")]=limit
    return update_limits(limit_dict,site_name=site_name)

def update_addon_credits_child_table(site, addon_type, credits, currency):
    addon_exists = False
    for addon in site.addon_limits:
        if addon.addon_type == addon_type:
            addon.available_credits += credits
            addon_exists =True
    
    if not addon_exists:
        saas_addon = frappe.get_list("Saas AddOn", filters={"currency":currency, "addon_type": addon_type}, ignore_permissions=True)[0].name
        addon = frappe.get_doc("Saas AddOn", saas_addon, ignore_permissions=True)
        # Adding New Row
        row = site.append("addon_limits",{})
        row.service_name = addon.addon_name
        row.addon_type = addon_type
        row.available_credits = credits
        row.uom = addon.uom
        row.rate = addon.per_credit_price
        row.currency = addon.currency
        row.minimum_quantity = addon.minimum_quantity
    site.save(ignore_permissions=True)


def create_invoice_and_payment_entry(site, addons, currency, payment_id):
    company_name = frappe.db.get_single_value('Global Defaults', 'default_company')
    company = frappe.get_doc("Company", company_name, ignore_permissions=True)

    si = frappe.new_doc("Sales Invoice")
    si.posting_date = nowdate()
    si.company = company_name
    si.cost_center = frappe.db.get_value('Company', si.company, 'cost_center')
    si.customer = site.customer
    si.debit_to = company.default_receivable_account
    si.currency= currency
    
    ## INR for Indian Customer, USD for rest
    si.price_list = frappe.get_list("Price List", filters={'enabled': 1, 'currency': currency, 'selling':1}, ignore_permissions=True)[0].name

    ## Add addons in Sales Invoice Items
    for addon_type in addons:
        if addon_type not in ["site", "site_name", "token"]:
            ## Fetching AddOn details from Saas AddOn List
            addon_name = frappe.get_list("Saas AddOn", filters={'disabled':0, 'addon_type':addon_type, 'currency':currency},ignore_permissions=True)[0].name
            addon = frappe.get_doc("Saas AddOn", addon_name, ignore_permissions=True)
            
            si.append("items", {
                "item_code": addon_type,
                "qty": addons[addon_type],
                "rate": flt(addon.per_credit_price)/flt(addon.addon_value),
            })
    
    ## Choosing Tax Template
    from erpnext.controllers.accounts_controller import get_taxes_and_charges
    si.taxes_and_charges = frappe.db.get_value("Subscription Plan", site.base_plan, "sales_taxes_and_charges_template")
    if si.taxes_and_charges:
        for row in get_taxes_and_charges("Sales Taxes and Charges Template", si.taxes_and_charges): 
            si.append("taxes",row)

    ## Insert & Save Invoice 
    frappe.set_user("Administrator")
    si.insert(ignore_permissions=True)
    si.submit()

    ## Creating Payment Entry
    create_payment_entry(site, si, payment_id)

    ## Send Invoice to Customer
    send_invoice_email(site, si, payment_id)

def create_payment_entry(site, sales_invoice, payment_id):
    payment_gateway = get_base_plan_details(site.base_plan).payment_gateway
    payment_account = frappe.get_value("Payment Gateway Account", payment_gateway, "payment_account")

    from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
    frappe.flags.ignore_account_permission = True
    pe = get_payment_entry(dt="Sales Invoice", dn=sales_invoice.name, bank_amount=sales_invoice.grand_total)
    frappe.flags.ignore_account_permission=False
    pe.paid_to = payment_account
    pe.reference_no = payment_id
    pe.reference_date = getdate()
    pe.save(ignore_permissions=True)
    pe.submit()

def send_invoice_email(site, si, payment_id):
    site_user = frappe.get_list("Saas User", filters={'linked_saas_site': site.name})[0].name
    site_user = frappe.get_doc("Saas User", site_user, ignore_permissions=True)
    STANDARD_USERS = ("Guest", "Administrator")

    subject="Payment Recieved at OneHash"
    template="payment_recieved_email"
    attachments = [frappe.attach_print("Sales Invoice", si.name, print_format='Standard')]
    
    args = {
        'name': site_user.first_name or site_user.last_name or "user",
        'user': site_user.email,
        'payment_id': payment_id,
        'invoice': si,
        'site': site_user.linked_saas_site,
        'site_url': "https://"+site_user.linked_saas_site,
        'help_url':"https://help.onehash.ai",
        'user_fullname': site_user.first_name+" "+site_user.last_name
        }

    sender = frappe.session.user not in STANDARD_USERS and get_formatted_email(frappe.session.user) or None
    frappe.sendmail(recipients=site_user.email, sender=sender, subject=subject, template=template, attachments= attachments, args=args, header=[subject, "green"],delayed=False)
    return 