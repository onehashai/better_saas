from __future__ import unicode_literals
import frappe
from frappe.sessions import get_geo_ip_country
from frappe.geo.country_info import get_country_timezone_info
from frappe.utils.data import getdate


def get_context(context):
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


@frappe.whitelist(allow_guest=True)
def is_valid_promocode(promocode):
    promocode = frappe.get_list("Coupon Code", filters={'is_signup_scheme':1, 'coupon_code': promocode}, ignore_permissions=True)
    if not len(promocode)>0:
        return False
    # # Check for Promocode Validation
    try:
        from erpnext.accounts.doctype.pricing_rule.utils import validate_coupon_code
        validate_coupon_code(promocode[0].name)
        return True
    except:
        return False

@frappe.whitelist(allow_guest=True)
def email_exists(email):
    linked_saas_site = frappe.db.get_value('Saas User', {'email': email, 'linked_saas_site': ['!=','']}, ['linked_saas_site'])
    if linked_saas_site:
        return linked_saas_site
    return False