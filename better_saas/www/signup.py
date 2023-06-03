from __future__ import unicode_literals
# from better_saas.better_saas.doctype.saas_user.saas_user import apply_new_limits
import frappe
from frappe.sessions import get_geo_ip_country
from frappe.geo.country_info import get_country_timezone_info
from frappe.utils.data import add_days, getdate, today
from werkzeug.exceptions import ExpectationFailed

no_cache = 1

form_keys = ('first_name', 'last_name', 'email',
	'phone_number', 'promocode')


def get_context(context):
    context.no_cache = 1
    args = frappe.request.args
    for key in form_keys:
        if(key in args):
            value = "" if args[key]=="None" else args[key]
            context[key] = value
        else:
            context[key]=""
        
    referral_code = args["referral_code"] if "referral_code" in args else ""
    context["partner_logo"] = frappe.db.get_value("Sales Partner",{"referral_code":referral_code},"logo")
    context["hide_phonenumber"] = 0
    pass

@frappe.whitelist(allow_guest=True)
def load_dropdowns():
    geo_country = get_geo_ip_country(
        frappe.local.request_ip) if frappe.local.request_ip else None
    country_timezone_info = get_country_timezone_info()
    languages = frappe.translate.get_lang_dict()
    all_languages = []
    for lang_name, lang_code in languages.items():
        all_languages.append([lang_code, lang_name])
    all_currency = []
    all_country = []
    for country_name, country in country_timezone_info['country_info'].items():
        try:
            currency_name = country['currency']
            all_currency.append(currency_name)
            all_country.append(country_name)
        except:
            pass

    response = {}
    response['countries'] = all_country
    response['languages'] = all_languages
    response['currencies'] = all_currency
    response['default_country'] = geo_country['names']['en'] if geo_country else None
    response['country_info'] = country_timezone_info['country_info']
    response['all_timezones'] = country_timezone_info['all_timezones']
    return response


# @frappe.whitelist(allow_guest=True)
# def apply_promocode(promocode, site_name):
# 	saas_user = frappe.get_list("Saas User",filters={"linked_saas_site":site_name},ignore_permissions=True)
# 	if(len(saas_user)==0):
# 		frappe.throw("Invalid Request",ExpectationFailed)
# 		return
# 	validResult = is_valid_promocode(promocode)
# 	if(validResult):
# 		promocode = frappe.get_list("Coupon Code", filters={'coupon_code': promocode}, ignore_permissions=True)[0].name
# 		coupon_code  = frappe.get_list("Coupon Code", promocode, ignore_permissions=True)[0]

# 		base_plan = coupon_code.base_plan
# 		limit_users = int(coupon_code.limit_for_users) ## Applying Users count from promocode
# 		limit_emails = int(coupon_code.limit_for_emails)
# 		limit_space = int (coupon_code.limit_for_space)
# 		limit_email_group = int(coupon_code.limit_for_email_group)

# 		## Check for Life-Time Deals (i.e. for 100 years)
# 		if coupon_code.no_expiry == 1:
# 			limit_expiry = add_days(today(), int(36500))
		
# 		apply_new_limits(limit_users,limit_emails,limit_space,limit_email_group,limit_expiry,site_name)

# 		## Promocode Consumed
# 		coupon_code.used = coupon_code.used + 1
# 		coupon_code.save(ignore_permissions=True)
# 	else:
# 		frappe.throw("Please Enter valid code",ExpectationFailed)
# 		return False


# @frappe.whitelist(allow_guest=True)
# def is_valid_promocode(promocode):
# 	code = frappe.get_list("Coupon Code", filters={'is_signup_scheme':1, 'coupon_code': promocode}, ignore_permissions=True)
# 	print(code)
# 	if(len(code)==0):
# 		return False
#     # # Check for Promocode Validation
	
# 	from erpnext.accounts.doctype.pricing_rule.utils import validate_coupon_code
# 	return validate_coupon_code(code[0].name)
	

@frappe.whitelist(allow_guest=True)
def email_exists(email):
    email = frappe.db.get_value('Saas User', {'email': email}, ['email'])
    if email:
        return email
    return False