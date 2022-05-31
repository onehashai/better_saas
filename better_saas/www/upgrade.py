from __future__ import unicode_literals
import frappe
import json
from datetime import datetime
from frappe import _
from frappe.exceptions import DoesNotExistError, ValidationError
from frappe.integrations.doctype.stripe_settings.stripe_settings import get_gateway_controller
from frappe.integrations.utils import get_payment_gateway_controller
from frappe.utils import format_date, flt
from frappe.utils.data import (ceil, global_date_format, getdate, flt, today,cint)
from frappe.sessions import get_geo_ip_country
from better_saas.better_saas.doctype.saas_user.saas_user import apply_new_limits, disable_enable_site
from erpnext.accounts.doctype.subscription.subscription import  get_subscription_updates
from erpnext.erpnext_integrations.stripe_integration import stripe_cancel_subscription,create_stripe_refund,retrieve_stripe_invoice
from erpnext.crm.doctype.lead.lead import make_customer

no_cache = 1
import stripe
# stripe.api_key = "sk_test_51Hf3MFCwmuPVDwVyVlhlRK2GXQPLS3tWpKSZbfCKg0FQmwjOnFTadwz5xTtA8330XzC4TC1SxLHrQwhqEnnFyRG700VxEhABqA"

def get_context(context):
    try:
        context.no_cache = 1
        args = frappe.request.args
        frappe.local.jenv.filters["timeformat"] = datetime.fromtimestamp
        site_name = args["site"] if "site" in args else ""
        context.site = get_current_limits(site_name)
        active_plan = frappe.get_doc("Subscription Plan",context.site.base_plan,ignore_permissions=True)
        context.active_plan = active_plan
        context.active_plan_name = context.site.base_plan
        # get_gateway_object_by_plan(context.active_plan_name)
        context.currency = active_plan.currency
        context.country = frappe.get_all("Country",pluck="name")
        context.tax_rate = get_tax_rate(active_plan.sales_taxes_and_charges_template)
        context.current_subscription,context.cart = get_current_plan(site_name,context.active_plan_name)
        context.balance=0 #get_balance(context.current_subscription.get("subscription_id"),context.site.get("customer"))
        subscription_plans = []
        saas_user = frappe.get_doc("Saas User",{"linked_saas_site":site_name},ignore_permissions=True)
        context.billing_email = saas_user.email
        context.customer_name = saas_user.company_name
        for plan in context.current_subscription.plans:
            subscription_plans.append(plan.plan)
        context.subscription_plans = subscription_plans if len(subscription_plans)>0 else {}
        context.add_ons = get_all_addons(currency=active_plan.currency)
        context.plans = get_all_plans(currency=active_plan.currency,current_plan=context.active_plan_name)
        context.address = get_address_by_site(site_name)
        context.invoices = get_stripe_subscription_invoice(context.current_subscription.get("subscription_id",None),get_payment_gateway_by_plan(context.active_plan_name))
        context.geo_country = get_geo_ip_country(
            frappe.local.request_ip) if frappe.local.request_ip else None
    except Exception as e:
        frappe.log_error(frappe.get_traceback(),"Error Traceback")
        frappe.log_error(e)
    pass

def get_all_plans(currency=None,product="OneCRM",current_plan=None):
    filters = {"show_on_website":1,"is_addon":0}
    filters["product"]=product
    if currency:
        filters["currency"] = currency

    plans = frappe.get_all("Subscription Plan",filters=filters,fields="*")
    plans_obj ={}
    for plan in plans:
        plans_obj[plan.name]=plan
    if current_plan and current_plan not in plans_obj:
        plans_obj[current_plan] = frappe.get_doc("Subscription Plan",current_plan,ignore_permissions=True).as_dict()
    return plans_obj    

@frappe.whitelist(allow_guest=True)
def get_current_plan(site_name,active_plan_name):
    args = {"reference_site":site_name,"status":["!=","Cancelled"]}
    if frappe.db.exists("Subscription",args):
        doc =  frappe.get_doc("Subscription",{"reference_site":site_name,"status":["!=","Cancelled"]},ignore_permissions=True)
    else:
        doc = frappe.new_doc("Subscription")
        doc.append("plans",{"plan":active_plan_name,"qty":1})

    cart={"base_plan":{},"add_ons":{}}
    for plan in doc.plans:
        if plan.plan==active_plan_name:
            cart["base_plan"]["plan"]=plan.plan
            cart["base_plan"]["qty"]=plan.qty
        else:
            cart["add_ons"][plan.plan]=plan.qty

    if not "plan" in cart["base_plan"]:
        cart["base_plan"]["plan"] = active_plan_name 
    return doc,cart
    pass

def get_current_limits(site_name):
    return frappe.get_doc("Saas Site",site_name, ignore_permissions=True)

def get_all_addons(currency=None,product="OneCRM"):
    filters = {"show_on_website":1,"is_addon":1}
    filters["product"]=product
    if currency:
        filters["currency"] = currency
    plans = frappe.get_all("Subscription Plan",filters=filters,fields="*")
    plans_obj ={}
    for plan in plans:
        plans_obj[plan.name]=plan
        
    return plans_obj    

def get_balance(stripe_subscription_id,customer):
    if customer==None:
        return 0
    if stripe_subscription_id==None:
        return 0
    stripe_subscription  = stripe.Subscription.retrieve(stripe_subscription_id)
    frappe.log_error(stripe_subscription)
    stripe_customer = stripe.Customer.retrieve(stripe_subscription.get("customer"))
    balance = -1*stripe_customer.get("balance")/100
    frappe.log_error(balance,stripe_subscription.get("customer"))
    return balance


#     response = stripe.Customer.create_balance_transaction(
#   "cus_LfTNvmoW4cpGFN",
#   amount=500,
#   currency="inr",
# )
#     return response.get("ending_balance")
    # pass

@frappe.whitelist(allow_guest=True)
def add_balance(amount,currency,site_name):
    frappe.log_error(amount,"Amount")
    amount = cint(flt(amount)*100)
    item = [{"price_data":{
    "currency":currency,
        "unit_amount": amount,
        "product_data":{
        "name":"Add balance"
        }
    },
    'quantity':1}]
    frappe.log_error(item,"Item")
    saas_user  = frappe.get_doc("Saas User",{"linked_saas_site":site_name},ignore_permissions=True)
    address= get_address_by_site(site_name,primary=True)[0]
    checkout_session = stripe.checkout.Session.create(
    customer_email = saas_user.email,
    success_url= frappe.utils.get_url("https://{0}/upgrade?site={1}&email={2}&full_name={3}&country={4}".format(frappe.conf.get("master_site_domain","app.onehash.ai"),site_name,saas_user.email,saas_user.first_name,saas_user.country)+"?subscription_status=success" or "https://app.onehash.ai/"),
    cancel_url= frappe.utils.get_url("https://{0}/app/usage-info".format(site_name)+"?subscription_status=cancel" or "https://app.onehash.ai/"),
    mode="payment",             
    payment_method_types=["card"],
    line_items=item,
    metadata = {"site_name":site_name}
    )
    return checkout_session
    pass

def get_address(customer,primary=False):
    filters={"link_name": customer}
    if primary:
        filters["is_primary_address"]=1
    order_by = "is_primary_address DESC"
    return frappe.get_all("Address", filters=filters,fields="*",order_by=order_by)
    pass

def get_address_by_site(site_name,primary=False):
    customer = get_customer_by_site(site_name)
    if not customer:
        customer = get_lead_by_site(site_name)
    if not customer:
        registered_email = frappe.get_value("Saas User",{"linked_saas_site":site_name},"email")
        customer = frappe.get_value("Lead",{"email_id":registered_email},"name")
    return get_address(customer,primary)

def get_customer_by_site(site_name):
    return frappe.db.get_value("Saas Site",site_name,"customer")
     
def get_lead_by_site(site_name):
    return frappe.db.get_value("Lead",{"linked_saas_site":site_name},"name")

@frappe.whitelist(allow_guest=True)
def get_cart_value(cart, site_name,email,onehash_partner,currency):
    cart  = json.loads(cart)
    plans = get_all_plans()
    add_ons = get_all_addons()
    cart_object = []
    if(len(cart["base_plan"])>0):
        cart_object.append(cart["base_plan"])
    for plan,qty in cart["add_ons"].items():
        cart_object.append({"plan":plan,"qty":qty})
    tax_rate = get_tax_rate(plans[cart["base_plan"]["plan"]].sales_taxes_and_charges_template)
    return frappe.render_template("templates/includes/upgrade/cart.html", {"cart":cart_object,"plans":plans,"add_ons":add_ons,"currency":currency,"tax_rate":tax_rate})
    pass

def get_cart(cart, site_name,currency):
    cart  = json.loads(cart)
    plans = get_all_plans()
    add_ons = get_all_addons()
    cart_object = []
    if(len(cart["base_plan"])>0):
        cart_object.append(cart["base_plan"])
    for plan,qty in cart["add_ons"].items():
        cart_object.append({"plan":plan,"qty":qty})
    tax_rate = get_tax_rate(plans[cart["base_plan"]["plan"]].sales_taxes_and_charges_template)
    return cart_object

def get_tax_rate(tax_template):
    tax_rate=0
    from erpnext.controllers.accounts_controller import get_taxes_and_charges
    taxes = get_taxes_and_charges("Sales Taxes and Charges Template", tax_template)
    if not taxes:
        return 0
    for tax in taxes:
        tax_rate = tax_rate + flt(tax.rate)
    return tax_rate
        
@frappe.whitelist(allow_guest=True)
def pay(cart, site_name,email,onehash_partner,currency):
    cart  = json.loads(cart)
    site = get_current_limits(site_name)
    current_subscription,old_cart = get_current_plan(site_name,site.base_plan)
    plans = get_all_plans(current_plan=site.base_plan)
    add_ons = get_all_addons()
    
    # new subscription
    if not current_subscription.subscription_id:
        response = create_subscription(plans,add_ons,cart,site)
        if(response.url):
            return {"redirect_to":response.url, "message":"redirecting to the gateway"}
        else:
            return {"redirect_to":"","message":"Something went wrong, Please try after sometime."}
        pass
    else:
        response,redirect_url= update_subscription(plans,add_ons,cart,site,current_subscription)
        return {"redirect_to":redirect_url,"message":"Subscription Updated Successfully." if redirect_url=="" else "Please complete the payment."}
        pass

def get_payment_gateway_by_plan(plan_name):
    payment_gateway = frappe.db.get_value("Subscription Plan",plan_name,"payment_gateway")
    return frappe.get_value("Payment Gateway Account",payment_gateway,"payment_gateway")

def get_gateway_object_by_plan(plan):
    payment_gateway= frappe.get_value("Subscription Plan",plan,"payment_gateway")
    frappe.log_error(payment_gateway,"Payment Gateway")
    gateway = frappe.get_value("Payment Gateway Account", payment_gateway, "payment_gateway")
    return get_gateway_object(gateway)
    pass


def get_stripe_items(plans,add_ons,cart,subscription_id=None):
    cart_object = []
    gateway = frappe.get_value("Payment Gateway Account", plans[cart["base_plan"]["plan"]].payment_gateway, "payment_gateway")
    stripe_subscription_items = {}
    if subscription_id:
        stripe = get_gateway_object(gateway)
        stripe_subscription = stripe.Subscription.retrieve(subscription_id)
        stripe_items = stripe_subscription.get("items").get("data")
        for item in stripe_items:
            stripe_subscription_items[item.get("price").get("id")]=item
    
    if(len(cart["base_plan"])>0):
        price_id = plans[cart["base_plan"]["plan"]].product_price_id
        item_object = {"price":price_id,"quantity":cart["base_plan"]["qty"],"tax_rates":[plans[cart["base_plan"]["plan"]].pg_tax_id] if plans[cart["base_plan"]["plan"]].pg_tax_id else [] }
        if price_id in stripe_subscription_items:
            item_object["id"]=stripe_subscription_items[price_id].get("id")
            del stripe_subscription_items[price_id]
        cart_object.append(item_object)
        
    for plan,qty in cart["add_ons"].items():
        price_id = add_ons[plan].product_price_id
        item_object = {"price":price_id,"quantity":qty,"tax_rates":[add_ons[plan].pg_tax_id] if add_ons[plan].pg_tax_id else []}
        if price_id in stripe_subscription_items:
            item_object["id"]=stripe_subscription_items[price_id].get("id")
            del stripe_subscription_items[price_id]
        cart_object.append(item_object)

    for price_id,item in stripe_subscription_items.items():
        item_object = {"id":item.get("id"),"price":price_id,"quantity":item.get("quantity"),"tax_rates":item.get("tax_rates"),"deleted":True}
        cart_object.append(item_object)
    return cart_object,gateway
    pass

def create_subscription(plans,add_ons,cart,site,current_subscription=None):
    items,gateway = get_stripe_items(plans,add_ons,cart)
    stripe = get_gateway_object(gateway)
    site_name = site.name
    saas_user  = frappe.get_doc("Saas User",{"linked_saas_site":site_name},ignore_permissions=True)
    address= get_address_by_site(site_name,primary=True)[0]
    checkout_session = stripe.checkout.Session.create(
    customer={
                        "name":saas_user.company_name,
                        "email":saas_user.email,
                        "metadata":{"site_name":site_name},
                        "address":{
                            "city":address.get("city"),
                            # "country":address.get("country"),
                            "line1":address.get("address_line1"),
                            "line2":address.get("address_line2"),
                            "postal_code":address.get("postal_code"),
                            "state":address.get("state")
                        }
                    },
      success_url= frappe.utils.get_url("https://{0}/app/usage-info".format(site_name)+"?subscription_status=success" or "https://app.onehash.ai/"),
      cancel_url= frappe.utils.get_url("https://{0}/app/usage-info".format(site_name)+"?subscription_status=cancel" or "https://app.onehash.ai/"),
      mode="subscription",             
      payment_method_types=["card"],
      billing_address_collection='required',
      line_items=items,
      metadata = {"site_name":site.name},
      subscription_data = {"metadata":{"site_name":site.name}}
    )
    return checkout_session
    pass

def get_gateway_object(gateway):
    import stripe
    gateway_controller = frappe.db.get_value("Payment Gateway",gateway, "gateway_controller")
    stripe_controller = frappe.get_doc("Stripe Settings",gateway_controller,ignore_permissions=True)
    stripe.api_key = stripe_controller.get_password(fieldname="secret_key", raise_exception=False)
    frappe.log_error(stripe.api_key,"API Key")
    return stripe    
    pass

def update_subscription(plans,add_ons,cart,site,current_subscription):
    current_subscription_items = {}
    for plan in current_subscription.plans:
        current_subscription_items[plan.plan]=plan
    items,gateway = get_stripe_items(plans,add_ons,cart,current_subscription.subscription_id)
    stripe = get_gateway_object(gateway)
    redirect_url = ""
    response = stripe.Subscription.modify(current_subscription.subscription_id,items=items,payment_behavior="allow_incomplete",proration_behavior="always_invoice",payment_settings={"payment_method_options":{"card":{"mandate_options":{"amount":10000,"amount_type":"maximum"}}}})
    if response.get("status")!="active":
        invoice = stripe.Invoice.retrieve(response.get("latest_invoice"))
        pi = stripe.PaymentIntent.confirm(invoice.get("payment_intent"),return_url="https://staging.onehash.ai/upgrade?site="+site.name+"&email=None&full_name=Administrator")
        next_action = pi.get("next_action")
        if next_action.get("type")=="redirect_to_url":
            redirect_url = next_action.get("redirect_to_url").get("url")
        elif next_action.get("type")=="use_stripe_sdk":
            redirect_url = next_action.get("use_stripe_sdk").get("stripe_js")
        else:
            redirect_url = invoice.get("hosted_invoice_url")
    return response,redirect_url
    pass

@frappe.whitelist(allow_guest=True)
def stripe_webhook():
    data = frappe._dict(json.loads(frappe.request.get_data()))
    if data.get("type") in ['customer.subscription.created', 'customer.subscription.updated']:
        try:
            stripe_subscription = frappe._dict(data.get("data", {}).get("object", {}))
            stripe_subscription_items = stripe_subscription.get("items",{}).get("data",[])
            if stripe_subscription.get("status")!="active":
                return {"success":True,"response":"Request rejected due to invalid status"+stripe_subscription.get("status")}
                pass
            metadata = stripe_subscription.get("metadata",{})
            product = metadata.get("website","OneHash")
            if product=="OneChat":
                return {"success":True,"response":"OneChat Request"}
            site_name = stripe_subscription.get("metadata",{}).get("site_name",None)
            if not site_name:
                frappe.throw(_("Site Name is required"),ValidationError)
            
            stripe_subscription.current_period_start = datetime.fromtimestamp(stripe_subscription.current_period_start).strftime("%Y-%m-%d")
            stripe_subscription.current_period_end = datetime.fromtimestamp(stripe_subscription.current_period_end).strftime("%Y-%m-%d")
            
            saas_site = get_current_limits(site_name)
            if not saas_site.customer:
                saas_site.customer = get_customer_from_site(saas_site.site_name)
            
            base_plan,subscription_items = get_base_plan_and_subscription_items(saas_site,stripe_subscription_items)
            saas_site.base_plan=base_plan
            saas_site = update_site_limits(saas_site,subscription_items)
            saas_site.expiry = stripe_subscription.current_period_end
            if data.type not in ['customer.subscription.deleted']:
                subscription = update_site_subscription(saas_site,subscription_items,stripe_subscription)
                if "status" in subscription:
                    return subscription
                saas_site.subscription = subscription
            else:
                subscription = frappe.get_doc("Subscription", saas_site.subscription, ignore_permissions=True)
                subscription.cancel_at_period_end = True
                subscription.save(ignore_permissions=True)
                saas_site.expiry = today()
                subscription.cancel_subscription()

            saas_site.save(ignore_permissions=True)
            apply_new_limits(saas_site.limit_for_users,saas_site.limit_for_emails,saas_site.limit_for_space,saas_site.limit_for_email_group,saas_site.expiry,site_name)
            pass
        except Exception as e:
            log = frappe.log_error(frappe.get_traceback(), "Exception Occured while handling stripe callback")
            return {"status": "Failed", "reason": e}
        return {"status": "Success"} 
    pass

def update_site_subscription(saas_site,subscription_items,stripe_subscription):
    try:
        subscription_name = saas_site.subscription
        if not subscription_name:
            subscription = frappe.new_doc('Subscription')
        else:
            subscription = frappe.get_doc("Subscription",subscription_name)

        subscription.subscription_id = stripe_subscription.get("id")
        subscription.reference_site = saas_site.name
        subscription.party_type = 'Customer'
        subscription.party = saas_site.customer
        subscription.current_invoice_start = stripe_subscription.get("current_plan_start")
        subscription.current_invoice_end = stripe_subscription.get("current_plan_end")
        subscription.cancel_at_period_end = False
        subscription.generate_invoice_at_period_start = True

        base_plan = saas_site.base_plan
        subscription.sales_tax_template,subscription.company = frappe.db.get_value("Subscription Plan", base_plan, ["sales_taxes_and_charges_template","default_company"])

        updated_items=[]
        # map items
        current_subscription_items = subscription.get("plans",[])
        for item in current_subscription_items:
            if item.get("subscription_item_id") in subscription_items:
                item.qty = subscription_items[item.get("subscription_item_id")].get("qty")
                updated_items.append(item)
                del subscription_items[item.get("subscription_item_id")]
        subscription.plans = updated_items
        for key,item in subscription_items.items():
            row = {"plan":item.get("plan"),"qty":item.get("qty"),"subscription_item_id":item.get("subscription_item_id")}
            subscription.append("plans",row)
            pass

        subscription.save(ignore_permissions=True)
        return subscription.name
    except Exception as e:
        log = frappe.log_error(frappe.get_traceback(),"Subscription Create Error")
        return {"status": "Failed", "reason": e}
    pass

def update_site_limits(saas_site,subscription_items):

    for key,si in subscription_items.items():
        if si.get("is_unlimited"):
            setattr(saas_site, si["data_key"], 0)
        else:
            if si["data_key"]=="limit_for_users":
                saas_site.limit_for_users = si["qty"]+saas_site.discounted_users
            else:
                setattr(saas_site, si["data_key"], si["qty"]*si["limit_multiplier"])

    return saas_site
    pass

def get_base_plan_and_subscription_items(saas_site,subscription_items):
    plans = get_all_plans(current_plan=saas_site.get("base_plan"))
    add_ons = get_all_addons()
    plans_by_subscription_price_id={}
    base_plan = saas_site.get("base_plan")
    for plan,plan_item in plans.items():
        plans_by_subscription_price_id[plan_item["product_price_id"]]=plan_item
    
    for plan,plan_item in add_ons.items():
        plans_by_subscription_price_id[plan_item["product_price_id"]]=plan_item

    psubscription_items={}
    for item in subscription_items:
        selected_plan = plans_by_subscription_price_id[item.get("plan").get("id")]
        if not selected_plan.get("is_addon"):
            base_plan= selected_plan.get("name")
        psubscription_items[item.get("id")]={'plan':selected_plan.name, 'qty': item.get("quantity"), 'subscription_item_id': item.get("id"),"data_key":selected_plan.get("data_key"),"is_unlimited":selected_plan.get("is_unlimited"),"limit_multiplier":selected_plan.get("limit_multiplier",1)}
    return base_plan,psubscription_items
    pass

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

@frappe.whitelist(allow_guest=True)
def stripe_mid_upgrade_handler():
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
            if(billing_reason =="subscription_update" or billing_reason=="subscription_cycle"):
                
                subscription = frappe.get_doc("Subscription",{"subscription_id":subscription_id},ignore_permissions=True)
                if not subscription:
                    frappe.throw(_("Subscription is mandatory was generating invoice."))

                if paid_amount>0:
                    upgrade_invoice  = create_upgrade_invoice(invoice,subscription)
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
            return {"status": "Failed", "reason": e}
        return {"status": "Success"}

def create_credit_note(reference_invoice_no,refund_amount):
    from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return
    credit_note_doc = make_sales_return(reference_invoice_no)
    # credit_note_doc = extract_tax_from_grand_total(credit_note_doc,refund_amount)
    credit_note_doc.insert(ignore_permissions=True)
    credit_note_doc.submit()
    return credit_note_doc

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
                # controller = get_payment_gateway_controller(gateway_controller)
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



def create_upgrade_invoice(gateway_invoice,subscription):
    """
    Creates a `Invoice`, submits it and returns it
    """
    from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import get_accounting_dimensions
    from erpnext import get_default_company

    
    doctype = 'Sales Invoice'
    invoice = frappe.new_doc(doctype)
    invoice.currency= invoice.get("currency").upper()
    # For backward compatibility
    # Earlier subscription didn't had any company field
    company = subscription.get('company') or get_default_company()
    if not company:
        frappe.throw(_("Company is mandatory was generating invoice. Please set default company in Global Defaults"))

    invoice.company = company
    # invoice.set_posting_time = 1
    # invoice.posting_date = subscription.current_invoice_start if subscription.generate_invoice_at_period_start \
    #     else subscription.current_invoice_end

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

    plans = get_all_plans()
    add_ons = get_all_addons()
    invoice_item = gateway_invoice.get("lines",{}).get("data",[])
    si_items = {}
    for item in subscription.get("plans"):
        si_items[item.subscription_item_id] = item

    for item in invoice_item:
        plan_name = si_items[item.get("subscription_item")].plan
        plan_details = plans[plan_name] if plan_name in plans else add_ons[plan_name]
        rate = (item.get("amount")/item.get("quantity"))/100
        quantity = item.get("quantity")
        item_row={"item_code":plan_details.get("item"),"description":item.get("description"), "qty": quantity, "rate": rate, 'cost_center': plan_details.get("cost_center")}
        invoice.append("items",item_row)
        pass

    # for item in items_list:
    #     item['cost_center'] = subscription.cost_center
    #     invoice.append('items', item)

    # Taxes
    tax_template = subscription.sales_tax_template
    
    if tax_template:
        invoice.taxes_and_charges = tax_template
        invoice.set_taxes()

    # Subscription period
    invoice.from_date = subscription.current_invoice_start
    invoice.to_date = subscription.current_invoice_end
    # invoice = extract_tax_from_grand_total(invoice,paid_amount)
    invoice.flags.ignore_mandatory = True
    invoice.flags.ignore_permissions = True
    invoice.save()
    invoice.submit()
    return invoice

def create_payment_entry(subscription_name, payment_id,reference_invoice=None,amount=None):
    try:
        subscription = frappe.get_doc("Subscription", subscription_name, ignore_permissions=True)
        invoice = reference_invoice if reference_invoice else subscription.invoices[-1].invoice
        sales_invoice = frappe.get_doc("Sales Invoice", invoice, ignore_permissions=True)

        base_plan = frappe.get_value("Saas Site", subscription.reference_site, "base_plan")
        payment_gateway = frappe.db.get_value("Subscription Plan",base_plan,"payment_gateway")
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
    except Exception as e:
        frappe.log_error(frappe.get_traceback(),"Error in Payment Entry")


def create_refund_payment_entry(subscription_name, payment_id,reference_invoice=None,amount=None):
    subscription = frappe.get_doc("Subscription", subscription_name, ignore_permissions=True)
    invoice = reference_invoice if reference_invoice else subscription.invoices[0].invoice
    sales_invoice = frappe.get_doc("Sales Invoice", invoice, ignore_permissions=True)

    base_plan = frappe.get_value("Saas Site", subscription.reference_site, "base_plan")
    payment_gateway = frappe.db.get_value("Subscription Plan",base_plan,"payment_gateway")
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

def get_base_plan_details(plan_name):
    return frappe.get_doc("Subscription Plan", plan_name)

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

def get_redirect_message(title=_("Subscription Updated"),message=_("Your Subscription has been successfully updated."),primary_label=_("Continue"),primary_action="/",indicator_color="green"):
    redirect_html = '''<script>
	frappe.ready(function() {
			setTimeout(function(){
				window.location.href = "'''+primary_action+'''";
			}, 4000);
		
	})
</script>'''
    return {"redirect_to": frappe.redirect_to_message(_(title), _(message+redirect_html),context={"primary_action":primary_action,"primary_label":primary_label,"title":title})}

def get_stripe_subscription_invoice(stripe_subscription_id,gateway):
    if not stripe_subscription_id:
        return []
    stripe = get_gateway_object(gateway)
    return stripe.Invoice.list(subscription=stripe_subscription_id)
    pass


@frappe.whitelist(allow_guest=True)
def verify_system_user(site_name, email):
    if email in ["None","Administrator"]:
        return True

    try:
        site = frappe.get_doc("Saas Site", site_name, ignore_permissions= True)
        for user in site.user_details:
            if user.emai_id == email and user.active == 1 and user.user_type == "System User":
                return True
        return False
    except:
        frappe.log_error('Authorization Failed, Please contact <a href="mailto:support@onehash.ai">support@onehash.ai</a> or your site Administrator.')
        return False

def get_customer_or_lead_by_site(site_name,billing_email=None):
    customer = get_customer_by_site(site_name)
    if(customer):
        return customer,"Customer"
    customer = get_lead_by_site(site_name)
    if customer:
        return customer,"Lead"
    if billing_email:
        lead_name = frappe.get_value("Lead",{"email_id":billing_email},name)
        return lead_name,"Lead"
    return None,None    
    pass

@frappe.whitelist(allow_guest=True)
def add_address(site_name,**kwargs):
    dn,dt = get_customer_or_lead_by_site(site_name,kwargs.get("email_id"))
    doc = frappe.get_doc({
        "doctype":"Address",
        "address_line1":kwargs.get("address_line1"),
        "address_line2":kwargs.get("address_line2"),
        "city":kwargs.get("city"),
        "state":kwargs.get("state"),
        "country":kwargs.get("country"),
        "pincode":kwargs.get("pincode"),
        "email_id":kwargs.get("email_id"),
        "phone":kwargs.get("phone"),
        "gst_state":kwargs.get("gst_state") or "",
        "gstin":kwargs.get("gstin") or "",
        "is_primary_address":True
    })
    doc.append("links",{"link_doctype":dt,"link_name":dn})
    doc.save(ignore_permissions=True)
    address = get_address_by_site(kwargs.get("site_name"))
    return frappe.render_template("templates/includes/upgrade/address.html",{"address":address})
    pass

@frappe.whitelist(allow_guest=True)
def mark_address_primary(name,site_name):
    doc =frappe.get_doc("Address",name,ignore_permissions=True)
    doc.is_primary_address = True
    doc.save(ignore_permissions=True)
    address = get_address_by_site(site_name)
    return frappe.render_template("templates/includes/upgrade/address.html",{"address":address})
    pass

@frappe.whitelist(allow_guest=True)
def update_address(name,**kwargs):
    doc =frappe.get_doc("Address",name,ignore_permissions=True)
    doc.address_line1=kwargs.get("address_line1")
    doc.address_line2 = kwargs.get("address_line2")
    doc.city=kwargs.get("city")
    doc.state=kwargs.get("state")
    doc.country=kwargs.get("country")
    doc.pincode=kwargs.get("pincode")
    doc.email_id=kwargs.get("email_id")
    doc.phone=kwargs.get("phone")
    doc.gst_state=kwargs.get("gst_state") or ""
    doc.gstin=kwargs.get("gstin") or ""
    doc.save(ignore_permissions=True)
    # return doc
    address = get_address_by_site(kwargs.get("site_name"))
    return frappe.render_template("templates/includes/upgrade/address.html",{"address":address})
    pass

@frappe.whitelist(allow_guest=True)
def get_address_by_id(name):
    return frappe.get_doc("Address",name,ignore_permissions=True)