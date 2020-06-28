from __future__ import unicode_literals
import frappe
from frappe.sessions import get_geo_ip_country
from frappe.geo.country_info import get_country_timezone_info

def get_context(context):
    country = get_geo_ip_country(frappe.local.request_ip) if frappe.local.request_ip else None
    
    country_timezone_info = get_country_timezone_info()
    all_curency ={}
    all_country = []
    for country_name,country in country_timezone_info.country_info:
        all_curency[country.currency_name] = country.currency
        all_country.append(country_name)

    context.all_country = all_country
    context.all_curency = all_curency
    context.all_timezones = country_timezone_info.all_timezones
    context.country = country
    context.selected_country_info = country_timezone_info['country_info']['country'] if country in country_timezone_info['country_info'] else None
    return context

