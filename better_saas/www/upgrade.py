from __future__ import unicode_literals
import frappe
import json
import datetime
from six import string_types
from frappe import _
from frappe.utils import format_date, flt
from frappe.utils.data import global_date_format
from frappe.sessions import get_geo_ip_country
from frappe.geo.country_info import get_country_timezone_info
from frappe.integrations.utils import get_payment_gateway_controller


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
def get_site_details(site_name, email, onehash_partner):
    site = frappe.get_doc("Saas Site", site_name)
    site.expiry = global_date_format(site.expiry)
    plan = get_base_plan_details(site.base_plan)
    addons = get_addon_plans()
    formatted_expiry = global_date_format(site.expiry)
    subscription_amount = flt(plan.cost)*flt(site.limit_for_users)
    subscription_value = frappe.format_value(
        flt(plan.cost)*flt(site.limit_for_users), {"fieldtype": "Float"})
    subscription_display_amount = frappe.format_value(flt(
        plan.cost)*flt(site.limit_for_users), {"fieldtype": "Currency", "currency": plan.currency})
    return {"site": site, "plan": plan, "formatted_expiry": formatted_expiry, "subscription_amount": subscription_amount, "subscription_value": subscription_value, "addons": addons, "subscription_display_amount": subscription_display_amount}


def get_addon_plans():
    addons = frappe.get_all("Saas AddOn", filters={"disabled": 0}, fields=[
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
    cart_details["cart"] = [{
        "upgrade_type": "Subscription",
        "value": 1,
        "amount": site_data["subscription_amount"],
        "amount_to_display": site_data["subscription_display_amount"]
    }]
    cart_amount = site_data["subscription_amount"]
    addons = site_data["addons"]
    plan = site_data["plan"]
    for key, addon in addons.items():
        if (key in cart and cart[key] != 0):
            item_amount = flt(cart[key]*addon["monthly_amount"]/flt(addon["addon_value"]))
            cart_amount = cart_amount + item_amount
            cart_item = {
                "upgrade_type": key,
                "value": cart[key],
                "amount": item_amount,
                "amount_to_display": frappe.format_value(item_amount, {"fieldtype": "Currency", "currency": addon["currency"]})
            }
            cart_details["cart"].append(cart_item)

    cart_details["total"] = cart_amount
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
    settings = controller.get_settings({})
    plan_id = cart["plan"].payment_plan_id if cart["plan"] else None
    if not plan_id:
        frappe.throw(_("Please setup Razorpay Plan ID"))

    subscription_details = {
        "plan_id": plan_id,
        "billing_frequency": 12,
        "customer_notify": 1,
        "quantity": cart["cart_details"]["subscribed_users"]
    }
    addons = []

    for cart_item in cart["cart_details"]["cart"]:
        if cart_item["upgrade_type"] != "Subscription":
            addons.append({"item": {"name": cart_item["upgrade_type"], "amount": cart_item["amount"], "currency": "INR"}, "quantity": 1})

    args = {
        "subscription_details": subscription_details,
        "addons": addons
    }

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
        "redirect_to": frappe.utils.get_url("https://app.onehash.ai/signup" or "")
    }

    # Redirect the user to this url
    return {"redirect_to": controller.get_payment_url(**payment_details) + get_razorpay_args(site_name,cart)}



def verify_signature(data):
    return True
    # if frappe.flags.in_test:
    # 	return True
    # signature = frappe.request.headers.get("X-Razorpay-Signature")

    # settings = frappe.get_doc("Membership Settings")
    # key = settings.get_webhook_secret()

    # controller = frappe.get_doc("Razorpay Settings")

    # controller.verify_signature(data, signature, key)


'''
    Successful Payment or renewal

    1. Parse Subscription Data
    2. Extract Site name from this reponse
    3. For that site increase the User/Email/ other Add-On Limit
    4. Update Site Expiry if payment is successful by 1 month

    Failed Subscription or renewal:
    1. If Subscrption failed i.e. could not renew and subscription status changed to Halt or Inactive.
    -> Mark that site inactive.

    Taxation:
        Currently Tax added into the plan pricing.

    Downgrading:
    1. Downgrade user limit or desired addons in subscription

    Cancellation:
    1. When User Canecels subscription handle those scenarios.

    India --> To be completed by Razorpay only.
    International--> To be implemented by stripe subscription


    Misc points:
    - User on upgrade page
        - renew with current users & add-ons
            - case 1: site renewal(25 april) before expiry date(30 april) -> expiry date + 1 month
            - case 2: site expired -> site renewal date + 1 month
        - no. of users incresed
            - on date of upgradation -> cancel current subscription & expiry date = current date + 1 month [Read about Razorpay subscription.update]
                # To be discussed Further
        - no. of users reduced: Limits subjected to base plan
            - Downgrading not allowed at mid-month: If done -> downgrading will fall back on next month [TO study over Razorpay subscription]
        - only Add-on added: [One Time Payment Payment Plan] [Order id will take place]
            - Saas Site Add-on: update add-on limit; ex current add-on plan + 
        - Add-on with Subscription: Both cases will be followed

    Subscription Module:  Razorpay + OneHash
    
'''


@frappe.whitelist(allow_guest=True)
def trigger_razorpay_subscription(*args, **kwargs):
    try: 
        data = frappe._dict(json.loads(frappe.request.get_data()))
        with open("/home/frappe/frappe-bench//apps/better_saas/better_saas/www/data.json", 'w') as f:
            json.dump(data, f)
    except:
        # Example Data
        data = frappe._dict({"entity": "event", "account_id": "acc_GAUOQ9HMzBdaBS", "event": "subscription.charged", "contains": ["subscription", "payment"], "payload": {"subscription": {"entity": {"id": "sub_H02WRMjN6DNU13", "entity": "subscription", "plan_id": "plan_GoSRXxQRs4COQl", "customer_id": "cust_GwQCvotqb6weM4", "status": "active", "current_start": 1618673773, "current_end": 1621189800, "ended_at": "null", "quantity": 10, "notes": [], "charge_at": 1621189800, "start_at": 1618673773, "end_at": 1647455400, "auth_attempts": 0, "total_count": 12, "paid_count": 1, "customer_notify": "true", "created_at": 1618673757, "expire_by": "null", "short_url": "null", "has_scheduled_changes": "false", "change_scheduled_at": "null", "source": "api", "payment_method": "card", "offer_id": "null", "remaining_count": 11}}, "payment": {"entity": {"id": "pay_H02WiP8NlXJS0o", "entity": "payment", "amount": 475000, "currency": "INR", "status": "captured", "order_id": "order_H02WRwQv9RPa10", "invoice_id": "inv_H02WRtXPJBeWOm", "international": "true", "method": "card", "amount_refunded": 0, "amount_transferred": 0, "refund_status": "null", "captured": "1", "description": "Subscription Fee", "card_id": "card_H02Wia04euT2Fr", "card": {"id": "card_H02Wia04euT2Fr", "entity": "card", "name": "Guest", "last4": "5558", "network": "MC", "type": "credit", "issuer": "KARB", "international": "true", "emi": "false", "expiry_month": 3, "expiry_year": 2030, "sub_type": "consumer", "number": "**** **** **** 5558", "color": "#25BAC3"}, "bank": "null", "wallet": "null", "vpa": "null", "email": "kuber@onehash.ai", "contact": "+918317067738", "customer_id": "cust_GwQCvotqb6weM4", "token_id": "null", "notes": {"emails": "5000","space": "10", "users": "2", "site": "india.onehash.ai", "token": "1dd3005b87"}, "fee": 21859, "tax": 3334, "error_code": "null", "error_description": "null", "acquirer_data": {"auth_code": "633206"}, "created_at": 1618673773}}}, "created_at": 1618674082})
        
    try:
        verify_signature(data)
    except Exception as e:
        log = frappe.log_error(e, "Webhook Verification Error")
        notify_failure(log)
        return {"status": "Failed", "reason": e}

    if not data.event == "subscription.charged":
        return  # TODO: for Other Cases

    try:
        update_razorpay_subscription(data)
    except Exception as e:
        log = frappe.log_error(e, "Subscription Error")
        notify_failure(log)
        return {"status": "Failed", "reason": e}
    return {"status": "Success"}


def update_razorpay_subscription(data):
    subscription_data = get_razorpay_subscription_data(data)

    # Subscription Renewed
    if data.payload.get("subscription", {}):
        renewal_date = subscription_data.renewal_date
        
        doc = frappe.get_doc("Saas Site", subscription_data.site)
        expiry_date = str(doc.expiry)
        
        # Case 1: renewal before expiry
        if(renewal_date < expiry_date):
            expiry_date = datetime.datetime.strptime(expiry_date, '%Y-%m-%d') + datetime.timedelta(days=30)
            expiry_date = expiry_date.strftime("%Y-%m-%d")

            doc.db_set('limit_for_users', subscription_data.limit_users, commit=True)
            doc.db_set('expiry', expiry_date, commit=True)
        # Case 2: renewal after expiry
        else:
            doc.db_set('limit_for_users', subscription_data.limit_users, commit=True)
            doc.db_set('expiry', subscription_data.expiry_date, commit=True)
    # Case 3: Add-on is added/removed
    if subscription_data.emails:
        doc.db_set('limit_for_emails', doc.limit_for_emails + int(subscription_data.emails), commit=True)
    if subscription_data.space:
        doc.db_set('limit_for_space', doc.limit_for_space + int(subscription_data.space), commit=True)
        # Saas Site Add-on to code: Finrich & Profile Enrich
            # user email add-ons
    #Case 4: Change in Users
    if subscription_data.users:
        # User Added
        if int(subscription_data.users) > 0:
            # TODO: To be added by renewal date
            doc.db_set('limit_for_users', doc.limit_for_users + int(subscription_data.users), commit=True) 
            pass
        # User Reduced
        elif int(subscription_data.users) < 0:
            # TODO: To be reduced by next month if triggered after mid-month
            pass

# Downgrade will take effect after grace period [using Background Jobs] on Downgrading date

def get_razorpay_subscription_data(data):

    subscription = frappe._dict(data.payload.get("subscription", {}).get("entity", {}))
    payment = frappe._dict(data.payload.get("payment", {}).get("entity", {}))
    notes = frappe._dict(data.payload.get("payment", {}).get("entity", {}).get("notes", {}))

    if subscription:
        subscription_data = frappe._dict({
            'limit_users': subscription.quantity,
            "renewal_date": datetime.datetime.fromtimestamp(subscription.current_start).strftime("%Y-%m-%d"),
            "expiry_date": datetime.datetime.fromtimestamp(subscription.current_end).strftime("%Y-%m-%d"),
        })
    else: subscription_data={}

    for key in notes:
        subscription_data[key] = notes[key]
    return subscription_data


def get_razorpay_args(site_name, cart):
    args = '&site_name='+ site_name
    for cart_item in cart["cart_details"]["cart"]:
        if cart_item["upgrade_type"] != "Subscription":
            addon , qty = cart_item["upgrade_type"], str(cart_item["value"])
            args += '&' + addon + '=' + qty
    return args


def notify_failure(log):
    try:
        content = """
			Dear System Manager,
			Razorpay webhook for creating renewing membership subscription failed due to some reason.
			Please check the following error log linked below
			Error Log: {0}
			Regards, Administrator
		""".format(get_link_to_form("Error Log", log.name))

        sendmail_to_system_managers(
            "[Important] [OneHash] Razorpay membership webhook failed , please check.", content)
    except:
        pass
