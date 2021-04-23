from __future__ import unicode_literals
import frappe
import json
import datetime
from six import string_types
from frappe import _
from frappe.utils import format_date, flt
from frappe.utils.data import (global_date_format, nowdate, add_days, add_to_date, add_months, date_diff, flt, get_date_str, get_first_day, get_last_day)
from frappe.sessions import get_geo_ip_country
from frappe.geo.country_info import get_country_timezone_info
from frappe.integrations.utils import get_payment_gateway_controller
from better_saas.better_saas.doctype.saas_user.saas_user import apply_new_limits
from better_saas.better_saas.doctype.saas_site.saas_site import update_addon_limits
from erpnext.accounts.doctype.subscription.subscription import get_subscription_updates


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


def get_subscription_data(site_name, controller, settings, **args):
    try:
        subscription = frappe.get_doc('Saas Site', site_name, ignore_permissions=True).subscription

        if not subscription:
            subscription = controller.setup_subscription(settings, **args)
        else:
            subscription_id = frappe.get_doc('Subscription', subscription).subscription_id
            subscription = controller.update_subscription(settings, subscription_id, **args)
    except Exception as e:
        log = frappe.log_error(frappe.get_traceback(), "Subscription Fetching Error")
    
    return subscription


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
        if cart_item["upgrade_type"] == "Users":
            subscription_details["quantity"] = subscription_details["quantity"] + cart_item["value"]
        #    addons.append({"item": {"name": cart_item["upgrade_type"], "amount": cart_item["amount"], "currency": "INR"}, "quantity": 1})

    args = {
        "subscription_details": subscription_details,
        # "addons": addons
    }

    subscription = get_subscription_data(site_name, controller, settings, **args)

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


    Call Apply Limits
    Invoice Generation is pending
'''


@frappe.whitelist(allow_guest=True)
def trigger_razorpay_subscription(*args, **kwargs):
    
    data = frappe._dict(json.loads(frappe.request.get_data()))
    with open("/home/frappe/frappe-bench//apps/better_saas/better_saas/www/data.json", 'w') as f:
        json.dump(data, f) # TODO: Remove After Testing also delete file

    try:
        verify_signature(data)
    except Exception as e:
        log = frappe.log_error(e, "Webhook Verification Error")
        notify_failure(log)
        return {"status": "Failed", "reason": e}

    # Subscription Charged
    if data.event == "subscription.charged":
        try:
            update_razorpay_subscription(data)
        except Exception as e:
            log = frappe.log_error(e, "Subscription Error")
            notify_failure(log)
            return {"status": "Failed", "reason": e}
        return {"status": "Success"}

    # SUbscription Updated
    if data.event == "subscription.updated":
        try:
            update_razorpay_subscription(data)
        except Exception as e:
            log = frappe.log_error(frappe.get_traceback(), "Subscription Error")
            notify_failure(log)
            return {"status": "Failed", "reason": e}
        return {"status": "Update Success"}


def update_razorpay_subscription(data):
    subscription_data = get_razorpay_subscription_data(data)

    site = frappe.get_doc("Saas Site", subscription_data.site_name)
    site_data = frappe._dict({
        'limit_for_users': site.limit_for_users,
        'expiry': site.expiry,
        'limit_for_space': site.limit_for_space,
        'limit_for_emails': site.limit_for_emails,
    })
    site_data['addon_limits'] = frappe._dict({})
    
    # Subscription Renewed
    if data.payload.get("subscription", {}):
        renewal_date = subscription_data.renewal_date
        expiry_date = str(site.expiry)
        
        # Case 1: renewal before expiry
        if(renewal_date < expiry_date):
            expiry_date = (datetime.datetime.strptime(expiry_date, '%Y-%m-%d') + datetime.timedelta(days=30)).strftime("%Y-%m-%d")
        # Case 2: renewal after expiry
        else:
            expiry_date = subscription_data.expiry_date

        site_data["limit_for_users"] = subscription_data.quantity
        site_data["expiry"] = expiry_date
            
    # Case 3: Email & Space Add-on
    # if subscription_data.emails:
    #     site_data['limit_for_emails'] = site.limit_for_emails + int(subscription_data.emails)
    # if subscription_data.space:
    #     site_data['limit_for_space'] = site.limit_for_space + int(subscription_data.space)
                
    # Case 4: Change in Users
    # if subscription_data.users:
        # User Added
        # TODO: To be added by renewal date
        # site_data['limit_for_users'] = site.limit_for_users + int(subscription_data.users)
        # TODO: Update subscription on Razorpay

        # User Reduced
        # TODO: To be reduced by next month if triggered after mid-month
    
    # Case 5: Add-on Services: Finrich & Profile Enrich
    # if subscription_data.addon:
    #     for service_name in subscription_data.addon:
    #         site_data['addon_limits'][service_name] = int(subscription_data.addon.service_name)

    update_saas_site(site, site_data)
    update_site_subscription(site.site_name, site.customer, site.base_plan, subscription_data.quantity, subscription_data.id, expiry_date)

# Downgrade will take effect after grace period [using Background Jobs] on Downgrading date


def update_site_subscription(site_name, customer, base_plan, qty, subscription_id, end_date):
    try:
        subscription = frappe.get_doc('Saas Site', site_name, ignore_permissions=True).subscription
        if len(subscriptions) == 0 :
            subscription = frappe.new_doc('Subscription')
            subscription.subscription_id = subscription_id
            subscription.reference_site = site_name
            subscription.party_type = 'Customer'
            subscription.party = customer
            subscription.current_invoice_start = nowdate()
            subscription.current_invoice_end = end_date
            subscription.generate_invoice_at_period_start = True
            subscription.append('plans', {'plan': base_plan, 'qty': qty})
            subscription.insert(ignore_permissions=True)
            frappe.db.commit()
        else:
            subscription_name = subscriptions[0].name
            
            subscription = frappe.get_doc('Subscription', subscription_name)
            for subscription_plan in subscription.plans:
                if subscription_plan.plan == base_plan:
                    subscription_plan.qty = qty
            subscription.save(ignore_permissions=True)
            frappe.db.commit()

            frappe.set_user('Administrator')
            get_subscription_updates(subscription.name)

    except Exception as e:
        log = frappe.log_error(frappe.get_traceback(), "Subscription Create Error")
        notify_failure(log)
        return {"status": "Failed", "reason": e}

def get_razorpay_subscription_data(data):

    subscription = frappe._dict(data.payload.get("subscription", {}).get("entity", {}))
    payment = frappe._dict(data.payload.get("payment", {}).get("entity", {}))
    notes = frappe._dict(data.payload.get("payment", {}).get("entity", {}).get("notes", {}))
    
    subscription_data = frappe._dict({})
    subscription_data["addon"] = frappe._dict({})

    if subscription:
            subscription_data['id'] = subscription.id
            subscription_data['plan_id'] = subscription.plan_id
            subscription_data["quantity"] = subscription.quantity
            subscription_data["renewal_date"] = datetime.datetime.fromtimestamp(subscription.current_start).strftime("%Y-%m-%d")
            subscription_data["expiry_date"] = datetime.datetime.fromtimestamp(subscription.current_end).strftime("%Y-%m-%d")
    if notes:
        for key in notes:
            if (key in ["finrich","profile_enrich"]):
                subscription_data["addon"][key] = notes[key]
            else:
                subscription_data[key] = notes[key]
        #TODO change addon services list to dynamic list
    return subscription_data


def get_razorpay_args(site_name, cart):
    args = '&site_name='+ site_name
    for cart_item in cart["cart_details"]["cart"]:
        if cart_item["upgrade_type"] != "Subscription":
            addon , qty = cart_item["upgrade_type"], str(cart_item["value"])
            args += '&{addon}={qty}'
    return args

def update_saas_site(doc, data):
    doc.limit_for_users = data.limit_for_users
    doc.expiry = data.expiry
    doc.limit_for_space = data.limit_for_space
    doc.limit_for_emails = data.limit_for_emails
    # for addon in data['addon_limits']:
    #     doc.addon_limits.service_name
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    apply_new_limits(doc.limit_for_users, doc.limit_for_emails, doc.limit_for_space, doc.limit_for_email_group, doc.expiry, doc.site_name)
    # update_addon_limits(json.dumps(doc.get('addon_limits',{})), doc.site_name)

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
