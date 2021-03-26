from __future__ import unicode_literals
import frappe,json
from frappe.utils import format_date,flt
from frappe.utils.data import global_date_format
from frappe.sessions import get_geo_ip_country
from frappe.geo.country_info import get_country_timezone_info
from frappe.integrations.utils import get_payment_gateway_controller

def get_context(context):
    args = frappe.request.args
    context.site = args["site"] if "site" in args else ""
    context.geo_country = get_geo_ip_country(frappe.local.request_ip) if frappe.local.request_ip else None
    pass

@frappe.whitelist(allow_guest=True)
def get_country():
    geo_country = get_geo_ip_country(frappe.local.request_ip) if frappe.local.request_ip else None
    return geo_country

@frappe.whitelist(allow_guest=True)
def get_site_details(site_name,email,onehash_partner):
    site  = frappe.get_doc("Saas Site",site_name)
    site.expiry = global_date_format(site.expiry)
    plan = get_base_plan_details(site.base_plan)
    addons = get_addon_plans()
    formatted_expiry = global_date_format(site.expiry)
    subscription_amount = flt(plan.cost)*flt(site.limit_for_users)
    subscription_value = frappe.format_value(flt(plan.cost)*flt(site.limit_for_users), {"fieldtype":"Float"})
    subscription_display_amount = frappe.format_value(flt(plan.cost)*flt(site.limit_for_users), {"fieldtype":"Currency","currency":plan.currency})
    return {"site":site,"plan":plan,"formatted_expiry":formatted_expiry,"subscription_amount":subscription_amount,"subscription_value":subscription_value,"addons":addons,"subscription_display_amount":subscription_display_amount}

def get_addon_plans():
    addons = frappe.get_all("Saas AddOn",filters={"disabled":0},fields=["addon_name","name","monthly_amount","yearly_amount","addon_type","addon_value","currency"])
    result_addon = {}
    for addon in addons:
        result_addon[addon.addon_type] = addon
    return result_addon

@frappe.whitelist(allow_guest=True)
def get_cart_details(site_name,email,onehash_partner,cart):
    site_details = get_site_details(site_name,email,onehash_partner)
    # base_plan_details = get_base_plan_details(cart.plan)
    return get_cart_value(site_details,cart)

def get_base_plan_details(plan_name):
    return frappe.get_doc("Subscription Plan",plan_name)

def get_cart_value(site_details,cart):
    cart = json.loads(cart)
    site_data = site_details
    cart_details = {}
    cart_details["cart"]=[{
                "upgrade_type":"Subscription",
                "value":1,
                "amount":site_data["subscription_amount"],
                "amount_to_display": site_data["subscription_display_amount"]
            }]
    cart_amount = site_data["subscription_amount"]
    addons = site_data["addons"]
    plan = site_data["plan"]
    for key,addon in addons.items():
        if (key in cart and cart[key]!=0):
            item_amount = flt(cart[key]*addon["monthly_amount"]/flt(addon["addon_value"]))
            cart_amount = cart_amount + item_amount
            cart_item = {
                "upgrade_type":key,
                "value":cart[key],
                "amount": item_amount,
                "amount_to_display":frappe.format_value(item_amount,{"fieldtype":"Currency","currency":addon["currency"]})
            }
            cart_details["cart"].append(cart_item)
    
    cart_details["total"] = cart_amount
    cart_details["total_to_display"] = frappe.format_value(cart_amount,{"fieldtype":"Currency","currency":plan.currency})
    cart_details["payment_gateway"] = plan.payment_gateway
    return {"cart_details":cart_details,"addons":addons}
    
@frappe.whitelist(allow_guest=True)
def pay(site_name,email,onehash_partner,cart):
    cart = get_cart_details(site_name,email,onehash_partner,cart)
    gateway_controller = cart["cart_details"]["payment_gateway"] if "payment_gateway" in cart["cart_details"] else "Razorpay"
    controller = get_payment_gateway_controller(gateway_controller)
    payment_details = {
        "amount": cart["cart_details"]["total"],
        "title": "OneHash",
        "description": "Subscription Payment",
        "reference_doctype": "Saas Site",
        "reference_docname": site_name,
        "payer_email": email,
        "payer_name": frappe.utils.get_fullname(frappe.session.user),
        "order_id": site_name+"_"+frappe.utils.now(),
        "currency": "INR",
        "redirect_to": frappe.utils.get_url("https://app.onehash.ai/signup" or "")
    }

    # Redirect the user to this url
    return  {"redirect_to":controller.get_payment_url(**payment_details)}

def setup_subscription():
    controller = get_payment_gateway_controller("Razorpay")
    settings = controller.get_settings({})

    plan_id = "plan_GoSRXxQRs4COQl"
    if not plan_id:
        frappe.throw(_("Please setup Razorpay Plan ID"))

    subscription_details = {
        "plan_id": plan_id,
        "billing_frequency": 12,
        "customer_notify": 1
    }

    args = {
        'subscription_details': subscription_details
    }

    subscription = controller.setup_subscription(settings, **args)
    
    payment_details = {
        "title": "OneHash Payment",
        "description": "OneHash Plan Renew/Upgrade ",
        "reference_doctype": "Saas Site",
        "reference_docname": "india.onehash.ai",
        "payer_email": "engg.ny@gmail.com",
        "payer_name": frappe.utils.get_fullname(frappe.session.user),
        "subscription_id": subscription["subscription_id"],
        "currency": "INR",
        "amount":"",
        "order_id":"",
        "redirect_to": ""
    }

    # Redirect the user to this url
    return  {"redirect_to":controller.get_payment_url(**payment_details)}
    #return controller.get_payment_url(**subscription_details)
    #return subscription