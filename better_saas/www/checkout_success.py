# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt
from __future__ import unicode_literals
from better_saas.better_saas.doctype.saas_user.saas_user import apply_promocode
from erpnext.crm.doctype.lead.lead import make_customer
import frappe
from frappe import _, throw
from frappe.utils import cint, fmt_money
from frappe.utils import today
import json
from frappe.integrations.doctype.stripe_settings.stripe_settings import get_gateway_controller
from erpnext.erpnext_integrations.stripe_integration import create_stripe_subscription, create_stripe_charge
from frappe.utils.data import flt
from werkzeug.exceptions import ExpectationFailed

no_cache = 1

expected_keys = ('amount', 'title', 'description',
	'payer_name', 'payer_email', 'order_id', 'currency','reference_docname','reference_doctype')

def get_context(context):
    context.no_cache = 1
    import stripe
    try:
        ltd_checkout = frappe.get_doc("LTD Checkout Settings")
        ltd_checkout.gateway_controller = frappe.db.get_value("Payment Gateway", ltd_checkout.payment_gateway, "gateway_controller")
        stripe_controller = frappe.get_doc("Stripe Settings",ltd_checkout.gateway_controller)
        stripe.api_key = stripe_controller.get_password(fieldname="secret_key", raise_exception=False)
        session = stripe.checkout.Session.retrieve(frappe.request.args.get('session_id'))
        customer = stripe.Customer.retrieve(session.customer)
        site_name = session.get("metadata").get("site_name")
        context.session = session
        context.customer = customer
        context.site_name = site_name
        payment_entry = frappe.get_value("Payment Entry",{"reference_no":session.get("payment_intent"),"docstatus":1},"name")
        context.payment_entry = payment_entry
        if(payment_entry):
            frappe.throw("Invalid Request",ExpectationFailed)
            return
        promocode  = retrive_code(ltd_checkout.code_prefix)
        context.promocode = promocode.coupon_code
        data={
            "payment_gateway":ltd_checkout.payment_gateway,
            "company":ltd_checkout.company,
            "items":[{
                "item_code":ltd_checkout.item_code,
                "qty":1,
                "rate":ltd_checkout.rate,
                "cost_center":ltd_checkout.cost_center
            }],
            "currency":ltd_checkout.currency,
            "payment_id":session.get("payment_intent"),
            "payer_email":customer.get("email"),
            "payer_name":customer.get("name"),
            "phone_number":customer.get("phone"),
            "promocode":promocode.coupon_code,
            "address":customer.get("address",{}),
            "source":"Website"
        }
        cur_user = frappe.session.user
        frappe.set_user("Administrator")
        invoice =create_invoice(data)
        pe = create_payment_entry(invoice,data)
        
        # Link Customer to the Promocode
        promocode.customer = invoice.customer
        promocode.save(ignore_permissions = True)

        send_email(ltd_checkout, invoice, pe, promocode,data)
        frappe.db.commit()
        if site_name:
            context.apply_promocode_result = apply_promocode(promocode.coupon_code,site_name)
            context.primary_action = "https://{}/app/usage-info".format(site_name)
            context.primary_action_label = "Continue"
        else:
            name = data.get("payer_name").split(" ",1)
            redirect_params = {
                "master_site_domain":frappe.conf.get("master_site_domain"), 
                "first_name":name[0],
                "last_name":name[1] if len(name)>1 else "",
                "email":data.get("payer_email"),
                "phone_number":data.get("phone_number"),
                "promocode":data.get("promocode"),
                "source": data.get("source"),
                "campaign":data.get("campaign")
            }
            context.primary_action = "https://{master_site_domain}/signup?first_name={first_name}&last_name={last_name}&email={email}&phone_number={phone_number}&promocode={promocode}&utm_source={source}&utm_campaign={campaign}".format(**redirect_params)
            context.primary_action_label = "Redeem Code"
        frappe.set_user(cur_user)

    except Exception as e:
        frappe.redirect_to_message(_('Error'),
        		_(frappe.get_traceback()),indicator_color='red',http_status_code=417)
        frappe.local.flags.redirect_location = frappe.local.response.location
        raise frappe.Redirect

def send_email(ltd_settings,invoice, payment_entry, coupon_code, data):
    if not ltd_settings.email_template:
        return
    attachments = []
    attachments.append({"print_format_attachment":1, "doctype":"Sales Invoice",
			"name":invoice.name, "print_format":ltd_settings.invoice_print_format or "Standard", "html":None})
    
    invoice = invoice.as_dict()
    ltd_settings = ltd_settings.as_dict()
    payment_entry = payment_entry.as_dict()
    coupon_code = coupon_code.as_dict()
    combined_data = {**coupon_code,**ltd_settings,**payment_entry,**invoice}
    email_template = frappe.get_doc("Email Template",ltd_settings["email_template"])
    message = frappe.render_template(email_template.response_html if email_template.use_html else email_template.response, combined_data)
    frappe.sendmail(data["payer_email"], subject=email_template.subject, message=message,attachments=attachments,with_container=True,now=True)
        


def get_api_key(doc, gateway_controller):
	publishable_key = frappe.db.get_value("Stripe Settings", gateway_controller, "publishable_key")
	if cint(frappe.form_dict.get("use_sandbox")):
		publishable_key = frappe.conf.sandbox_publishable_key

	return publishable_key

def retrive_code(series="OH-"):
    coupon_code = frappe.get_list("Coupon Code",filters=[["coupon_code","like",series+"%"],["status","=","Available"],["linked_saas_site","is","not set"]],limit_page_length=1,ignore_permissions=True)
    if(len(coupon_code)==0):
        frappe.throw("Deal Could not be Activated, Please Contact Support.",ExpectationFailed)
    else:
        doc = frappe.get_doc("Coupon Code",coupon_code[0].name,ignore_permissions=True)
        doc.status="Sold"
        doc.save(ignore_permissions=True)
        return doc


def get_header_image(doc, gateway_controller):
	header_image = frappe.db.get_value("Stripe Settings", gateway_controller, "header_img")
	return header_image

@frappe.whitelist(allow_guest=True)
def buy_ltd(referrer="https://onehash.ai/pricing"):
    ltd_checkout = frappe.get_doc("LTD Checkout Settings")
    ltd_checkout.cancel_url = ltd_checkout.cancel_url if ltd_checkout.cancel_url else referrer
    ltd_checkout.gateway_controller = frappe.db.get_value("Payment Gateway", ltd_checkout.payment_gateway, "gateway_controller")
    ltd_checkout.quantity = 1
    checkout_session = create_checkout_session_stripe(ltd_checkout)
    return {"redirect_to":checkout_session.url}

def create_checkout_session_stripe(data):
    import stripe
    stripe_controller = frappe.get_doc("Stripe Settings",data.gateway_controller)
    stripe.api_key = stripe_controller.get_password(fieldname="secret_key", raise_exception=False)
    checkout_session = stripe.checkout.Session.create(
      success_url="{}".format(data.success_url or "https://staging.onehash.ai/signup")+"?session_id={CHECKOUT_SESSION_ID}",
      cancel_url=data.cancel_url,
      payment_method_types=["card"],
      billing_address_collection='required' if data.address_at_checkout else 'auto',
      line_items=[
        {
          'price_data': {
            'currency': data.currency,
            'product_data': {
              'name': data.item_name,
              'description': data.item_description
            },
            'unit_amount': cint(flt(data.rate)*100),
          },
          'quantity': data.quantity
        }
      ],
      mode="payment"
    )
    return checkout_session


def create_invoice(data):
    """
    Creates a `Invoice`, submits it and returns it
    """
    from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import get_accounting_dimensions
    from erpnext import get_default_company

    customer = get_customer(data)
    doctype = 'Sales Invoice'
    invoice = frappe.new_doc(doctype)
    invoice.currency= data["currency"]
    # For backward compatibility
    # Earlier subscription didn't had any company field
    company =  data.get("company") or get_default_company() or "OneHash, Inc."
    cost_center =  data.get("cost_center")
    invoice.company = company
    invoice.cost_center = cost_center
    invoice.set_posting_time = 1
    invoice.posting_date = today()
    invoice.customer = customer
    invoice.customer_name  = data.get("payer_name")
    
    
    # Subscription is better suited for service items. I won't update `update_stock`
    # for that reason
    items_list = data.get("items")
    for item in items_list:
        invoice.append('items', item)
    invoice.set_missing_values()
    # invoice.flags.ignore_mandatory = True
    invoice.flags.ignore_permissions = True
    invoice.save()
    invoice.submit()
    return invoice

def create_payment_entry(invoice,data):
    payment_gateway = data.get("payment_gateway")
    payment_account = frappe.get_value("Payment Gateway Account", {"payment_gateway":payment_gateway}, "payment_account")
    cur_user = frappe.session.user
    frappe.set_user("Administrator")
            
    from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
    frappe.flags.ignore_account_permission = True
    bank_amount = invoice.grand_total
    pe = get_payment_entry(dt="Sales Invoice", dn=invoice.name, bank_amount=bank_amount)
    frappe.flags.ignore_account_permission=False
    pe.paid_to = payment_account
    pe.payment_type = "Receive"
    pe.received_amount = pe.paid_amount/pe.target_exchange_rate
    pe.reference_no = data.get("payment_id")
    pe.reference_date =  today()
    pe.save(ignore_permissions=True)
    
    if(abs(pe.difference_amount)<1):
        pe.paid_amount = pe.paid_amount - pe.difference_amount
        pe.save(ignore_permissions=True)
    frappe.flags.ignore_permissions=True
    pe.submit()
    frappe.set_user(cur_user)
    return pe

def get_customer(data):
    email = data["payer_email"]
    customer = frappe.get_list('Customer', filters={'email_id': email}, ignore_permissions=True)
    if customer:
        customer_name = customer[0].name
        address = {}
        country = frappe.get_value("Country", {"code": data["address"]["country"].lower()})
        address["address_line1"] = data.get("address",{}).get("line1")
        address["address_line2"] = data.get("address",{}).get("line2")
        address["city"] = data.get("address",{}).get("city")
        address["state"] = data.get("address",{}).get("state")
        address["pincode"] = data.get("address",{}).get("postal_code")  
        address["mobile_no"] = data.get("phone_number")
        address["country"] = country
        address["doctype"] = "Customer"
        address["name"] = customer_name
        frappe.log_error(address,"Address")
        from erpnext.selling.doctype.customer.customer import make_address
        make_address(address)
    else:
        lead = frappe.get_list('Lead', filters={'email_id': email}, ignore_permissions=True)
        if not len(lead)>0:
            lead = frappe.new_doc('Lead')
            lead.email_id = email
            lead.lead_name = data.get("payer_name")
            lead.source = "Website"
            lead.address_line1 = data.get("address",{}).get("line1")
            lead.address_line2 = data.get("address",{}).get("line2")
            lead.city = data.get("address",{}).get("city")
            lead.state = data.get("address",{}).get("state")
            lead.pincode = data.get("address",{}).get("postal_code")
            
            lead.mobile_no = data.get("phone_number")
            lead.country = frappe.db.get_value("Country",{"code":data.get("address",{}).get("country")})
            lead.insert(ignore_permissions=True)
        else: 
            lead = frappe.get_doc("Lead",lead[0].name, ignore_permissions=True)
        
        try:
            cur_user = frappe.session.user
            if(lead.contact_date and lead.contact_date.strftime("%Y-%m-%d %H:%M:%S.%f") < frappe.utils.now()):
                lead.contact_date = ""
                lead.save(ignore_permissions=True)


            frappe.set_user("Administrator")
            customer = make_customer(lead.name)
            #customer.default_currency = currency
            customer.insert(ignore_permissions=True)
            customer_name = customer.name
            frappe.set_user(cur_user)
        except:
            frappe.log_error(frappe.get_traceback(), 'Make Customer Error')
    return customer_name


    
