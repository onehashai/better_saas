from __future__ import unicode_literals
import frappe,json
from frappe import _
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
    cart_details["subscribed_users"] = site_data["site"].limit_for_users
    cart_details["total_to_display"] = frappe.format_value(cart_amount,{"fieldtype":"Currency","currency":plan.currency})
    cart_details["payment_gateway"] = frappe.get_value("Payment Gateway Account",plan.payment_gateway,"payment_gateway")
    return {"cart_details":cart_details,"addons":addons, "plan":plan, "site_data":site_data}
    
@frappe.whitelist(allow_guest=True)
def pay(site_name,email,onehash_partner,cart):
    cart = get_cart_details(site_name,email,onehash_partner,cart)
    gateway_controller = cart["cart_details"]["payment_gateway"] if "payment_gateway" in cart["cart_details"] else "Razorpay"
    controller = get_payment_gateway_controller(gateway_controller)
    settings = controller.get_settings({})
    plan_id = cart["plan"].payment_plan_id if cart["plan"] else None
    if not plan_id:
        frappe.throw(_("Please setup Razorpay Plan ID"))

    subscription_details = {
        "plan_id": plan_id,
        "billing_frequency":12,
        "customer_notify": 1,
        "quantity":cart["cart_details"]["subscribed_users"]
    }
    addons=[]

    for cart_item in cart["cart_details"]["cart"]:
        if cart_item["upgrade_type"] != "Subscription":
            addons.append({"item":{"name":cart_item["upgrade_type"],"amount":cart_item["amount"],"currency":"INR"},"quantity":1})

    args = {
        "subscription_details": subscription_details,
        "addons":addons
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
    return  {"redirect_to":controller.get_payment_url(**payment_details)}


def verify_signature(data):
	if frappe.flags.in_test:
		return True
	signature = frappe.request.headers.get("X-Razorpay-Signature")

	settings = frappe.get_doc("Membership Settings")
	key = settings.get_webhook_secret()

	controller = frappe.get_doc("Razorpay Settings")

	controller.verify_signature(data, signature, key)


@frappe.whitelist(allow_guest=True)
def trigger_razorpay_subscription(*args, **kwargs):
    data = frappe.request.get_data(as_text=True)
	try:
		verify_signature(data)
	except Exception as e:
		log = frappe.log_error(e, "Webhook Verification Error")
		notify_failure(log)
		return { "status": "Failed", "reason": e}

	if isinstance(data, six.string_types):
		data = json.loads(data)
	data = frappe._dict(data)

	subscription = data.payload.get("subscription", {}).get("entity", {})
	subscription = frappe._dict(subscription)

	payment = data.payload.get("payment", {}).get("entity", {})
	payment = frappe._dict(payment)

	try:
		if not data.event == "subscription.charged":
			return

		member = get_member_based_on_subscription(subscription.id, payment.email)
		if not member:
			member = create_member(frappe._dict({
				"fullname": payment.email,
				"email": payment.email,
				"plan_id": get_plan_from_razorpay_id(subscription.plan_id)
			}))

			member.subscription_id = subscription.id
			member.customer_id = payment.customer_id
			if subscription.notes and type(subscription.notes) == dict:
				notes = "\n".join("{}: {}".format(k, v) for k, v in subscription.notes.items())
				member.add_comment("Comment", notes)
			elif subscription.notes and type(subscription.notes) == str:
				member.add_comment("Comment", subscription.notes)


		# Update Membership
		membership = frappe.new_doc("Membership")
		membership.update({
			"member": member.name,
			"membership_status": "Current",
			"membership_type": member.membership_type,
			"currency": "INR",
			"paid": 1,
			"payment_id": payment.id,
			"from_date": datetime.fromtimestamp(subscription.current_start),
			"to_date": datetime.fromtimestamp(subscription.current_end),
			"amount": payment.amount / 100 # Convert to rupees from paise
		})
		membership.insert(ignore_permissions=True)

		# Update membership values
		member.subscription_start = datetime.fromtimestamp(subscription.start_at)
		member.subscription_end = datetime.fromtimestamp(subscription.end_at)
		member.subscription_activated = 1
		member.save(ignore_permissions=True)
	except Exception as e:
		message = "{0}\n\n{1}\n\n{2}: {3}".format(e, frappe.get_traceback(), __("Payment ID"), payment.id)
		log = frappe.log_error(message, _("Error creating membership entry for {0}").format(member.name))
		notify_failure(log)
		return { "status": "Failed", "reason": e}

	return { "status": "Success" }


def notify_failure(log):
	try:
		content = """
			Dear System Manager,
			Razorpay webhook for creating renewing membership subscription failed due to some reason.
			Please check the following error log linked below
			Error Log: {0}
			Regards, Administrator
		""".format(get_link_to_form("Error Log", log.name))

		sendmail_to_system_managers("[Important] [OneHash] Razorpay membership webhook failed , please check.", content)
	except:
		pass


def get_plan_from_razorpay_id(plan_id):
	plan = frappe.get_all("Membership Type", filters={"razorpay_plan_id": plan_id}, order_by="creation desc")

	try:
		return plan[0]["name"]
	except:
		return None

