# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt
from __future__ import unicode_literals
from erpnext.crm.doctype.lead.lead import make_customer
import frappe
from frappe import _
from frappe.utils import cint, fmt_money
from frappe.utils import today
import json
from frappe.integrations.doctype.stripe_settings.stripe_settings import get_gateway_controller
from erpnext.erpnext_integrations.stripe_integration import create_stripe_subscription, create_stripe_charge
from frappe.utils.data import flt

no_cache = 1

expected_keys = ('amount', 'title', 'description',
	'payer_name', 'payer_email', 'order_id', 'currency','reference_docname','reference_doctype')

def get_context(context):
    context.no_cache = 1
    try:
        args = frappe.request.args.to_dict() or {}
        tid = frappe.request.cookies.get("_fprom_tid",None)
        if tid:
            args["fp_tid"]=tid
        site_name = args["site_name"] if "site_name" in args else None
        context.site_name = site_name
        context.ltd_link = buy_ltd(site_name=site_name,args=args)
    except Exception as e:
        frappe.redirect_to_message(_('Some information is missing'),
        		_(frappe.get_traceback()))
        frappe.local.flags.redirect_location = frappe.local.response.location
        raise frappe.Redirect
        


def get_api_key(doc, gateway_controller):
	publishable_key = frappe.db.get_value("Stripe Settings", gateway_controller, "publishable_key")
	if cint(frappe.form_dict.get("use_sandbox")):
		publishable_key = frappe.conf.sandbox_publishable_key

	return publishable_key

def get_header_image(doc, gateway_controller):
	header_image = frappe.db.get_value("Stripe Settings", gateway_controller, "header_img")
	return header_image

@frappe.whitelist(allow_guest=True)
def buy_ltd(referrer="https://onehash.ai/pricing",site_name=None,args={}):
    ltd_checkout = frappe.get_doc("LTD Checkout Settings")
    ltd_checkout.cancel_url = ltd_checkout.cancel_url if ltd_checkout.cancel_url else referrer
    ltd_checkout.gateway_controller = frappe.db.get_value("Payment Gateway", ltd_checkout.payment_gateway, "gateway_controller")
    ltd_checkout.quantity = 1
    ltd_checkout.metadata = {}
    ltd_checkout.site_name = None
    if(site_name):
        ltd_checkout.site_name = site_name
        ltd_checkout.metadata["site_name"]=site_name
    utm_string=""
    if(args):
        for key,value in args.items():
            ltd_checkout.metadata[key] = value
            utm_string = utm_string+"&"+key+"="+value
    
    ltd_checkout.success_url = "https://{}/checkout_success".format(frappe.conf.get("master_site_domain"))+"?session_id={CHECKOUT_SESSION_ID}"+utm_string
    checkout_session = create_checkout_session_stripe(ltd_checkout)
    return {"redirect_to":checkout_session.url}

def create_checkout_session_stripe(data):
    import stripe
    stripe_controller = frappe.get_doc("Stripe Settings",data.gateway_controller)
    stripe.api_key = stripe_controller.get_password(fieldname="secret_key", raise_exception=False)
    checkout_session = stripe.checkout.Session.create(
      success_url="{}".format(data.success_url or "https://staging.onehash.ai/signup?"),
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
      mode="payment",
      metadata = data.metadata,
        payment_intent_data = {"metadata":data.metadata}
      
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
    
    
    # Subscription is better suited for service items. I won't update `update_stock`
    # for that reason
    items_list = data.get("items")
    for item in items_list:
        invoice.append('items', item)

    invoice.flags.ignore_mandatory = True
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
    else:
        lead = frappe.get_list('Lead', filters={'email_id': email}, ignore_permissions=True)
        if not len(lead)>0:
            lead = frappe.new_doc('Lead')
            lead.email_id = email
            lead.lead_name = data.get("name")
            lead.source = "Website"
            lead.address_line1 = data.get("address_line1")
            lead.city = data.get("city")
            lead.state = data.get("state")
            lead.zipcode = data.get("zipcode")
            lead.address_line2 = data.get("address_line2")
            lead.mobile_no = data.get("phone")
            lead.country = data.get("country")
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


    
