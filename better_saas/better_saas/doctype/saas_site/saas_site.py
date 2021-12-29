# -*- coding: utf-8 -*-
# Copyright (c) 2020, Vigneshwaran Arumainayagam and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
import json
from frappe import _
from frappe.utils import today, nowtime, add_days
from frappe.model.document import Document
from journeys.addon_limits import update_limits
from werkzeug.exceptions import ExpectationFailed

class SaasSite(Document):
    pass            

@frappe.whitelist()
def update_addon_limits(addon_limits,site_name):
    #return json.loads(addon_limits)
    limit_dict = {}
    for limit in json.loads(addon_limits):
        limit_dict[limit["service_name"]]=limit
    return update_limits(limit_dict,site_name=site_name)

def allocate_default_add_on_limits():
    '''Used in scheduler for auto allocation of the default credits'''
    saas_settings = frappe.get_doc("Saas Settings")
    auto_allocation_limit = saas_settings.deafult_addon_limits
    for service_limit in auto_allocation_limit:
        eligible_sites = get_credit_eligible_sites(service_limit.allocate_after_days)
        allocate_credits(eligible_sites,service_limit)
        pass

def allocate_credits(eligible_sites,service_limit):
    saas_addon = frappe.get_doc("Saas AddOn",service_limit.saas_addon)
    try:
        for site in eligible_sites:
            doc = frappe.get_doc("Saas Site",site.name)
            current_limits = doc.addon_limits
            allocated = False
            for limit in current_limits:
                if limit.service_name == service_limit.saas_addon:
                    limit.available_credits = limit.available_credits + service_limit.credits
                    allocated = True
                    break
            if(not allocated):
                limits = {}
                limits["service_name"] = saas_addon.name
                limits["available_credits"] = service_limit.credits
                limits["uom"] = saas_addon.uom
                limits["rate"] = saas_addon.per_credit_price
                limits["currency"] = saas_addon.currency
                limits["minimum_quantity"] = saas_addon.minimum_quantity
                doc.append("addon_limits",limits)
            doc.save()
            update_addon_limits(frappe.as_json(doc.addon_limits),doc.name)
            send_credit_allocation_email(doc,service_limit,saas_addon)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(),"Credit Allocation Error")
        pass

def send_credit_allocation_email(saas_site,service_limit,saas_addon):
    if not service_limit.email_notification_template:
        return
    saas_user = frappe.get_list("Saas User",filters={"linked_saas_site":saas_site.name},fields=['*'])[0]
    saas_site = saas_site.as_dict()
    service_limit = service_limit.as_dict()
    saas_addon = saas_addon.as_dict()
    data = {**saas_user,**saas_site,**service_limit,**saas_addon}
    email_template = frappe.get_doc("Email Template",service_limit["email_notification_template"])
    message = frappe.render_template(email_template.response_html if email_template.use_html else email_template.response, data)
    frappe.sendmail(saas_user["email"], subject=email_template.subject, message=message)
    
def get_credit_eligible_sites(created_before_days):
    creation_date = add_days(today(), -1*int(created_before_days))
    eligible_sites = frappe.get_all("Saas Site",filters=[["creation","like",creation_date+"%"]])
    return eligible_sites

def update_user_to_main_app():
    admin_site_name = frappe.conf.get("master_site_name") or "admin_onehash"
    frappe.destroy()
    frappe.init(site=admin_site_name)
    frappe.connect()
    all_sites = frappe.get_all("Saas Site")
    for site in all_sites:
        frappe.destroy()
        current_site_name = site.name
        frappe.init(site=current_site_name)
        frappe.connect()
        enabled_system_users = frappe.get_all("User",fields=['name','email','last_active','user_type','enabled','first_name','last_name','creation'])
        
        frappe.destroy()
        frappe.init(site=admin_site_name)
        frappe.connect()        
        try:        
            site_doc = frappe.get_doc('Saas Site',current_site_name)
            site_doc.user_details = {}        
            enabled_users_count = 0
            max_last_active = None
            for user in enabled_system_users:                       
                if(user.name in ['Administrator','Guest']):
                    continue

                site_doc.append('user_details', {
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'user_type': user.user_type,
                    'active': user.enabled,
                    'emai_id': user.email,
                    'last_active':user.last_active
                })

                if(user.enabled):
                    enabled_users_count = enabled_users_count + 1

                if(user.last_active==None):
                    continue

                if(max_last_active==None):
                    max_last_active = user.last_active
                elif(max_last_active<user.last_active):
                    max_last_active = user.last_active

            site_doc.number_of_users =   (len(enabled_system_users)-2)
            site_doc.number_of_active_users= enabled_users_count
            site_doc.last_activity_time = max_last_active
            site_doc.save()
            frappe.db.commit()            
        except Exception as e:
            frappe.log_error(str(e))
        finally:
            frappe.destroy()

# mute emails for the site which are going to expire tomorrow unsubscribe from Schedule Error notification
def mute_emails_on_expiry():
    try:
        all_sites = frappe.get_all("Saas Site",filters=[["Saas Site","expiry","Timespan","yesterday"]])
        for site in all_sites:
            commands = ["bench --site {site_name} set-config mute_emails true".format(site_name = site.name)]
            frappe.enqueue('bench_manager.bench_manager.utils.run_command',
                commands=commands,
                doctype="Bench Settings",
                key=today() + " " + nowtime()
            )
    except Exception as e:
        frappe.error_log(str(e),title="Error while muting Email")
        pass

@frappe.whitelist()
def set_site_config(site_name,key,value):
    if not site_name:
        frappe.throw(_("Site name is mandatory",ExpectationFailed))
    
    commands = ["bench --site {site_name} set-config {key} {value}".format(site_name = site_name,key=key,value=value)]
    frappe.enqueue('bench_manager.bench_manager.utils.run_command',
                commands=commands,
                doctype="Bench Settings",
                key=today() + " " + nowtime()
            )

def get_all_database_config():
    try:
        admin_site_name = frappe.conf.get("master_site_name") or "admin_onehash"
        frappe.destroy()
        frappe.init(site=admin_site_name)
        frappe.connect()
        all_sites = frappe.get_list("Saas Site")
        for site in all_sites:
            frappe.destroy()
            current_site_name = site.name
            frappe.init(site=current_site_name)
            frappe.connect()
            conf = frappe.local.conf
            print("--"+current_site_name+","+conf['db_name']+","+conf['db_password']+"\r\n")
            print("CREATE USER '"+conf['db_name']+"'@'%' IDENTIFIED BY '"+conf['db_password']+"';")
            #print("CREATE DATABASE '"+conf['db_name']+"'@'%' IDENTIFIED BY '"+conf['db_password']+"';")
            #print("GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, INDEX, ALTER, CREATE TEMPORARY TABLES, CREATE VIEW, EVENT, TRIGGER, SHOW VIEW, CREATE ROUTINE, ALTER ROUTINE, EXECUTE ON "+conf["db_name"]+".* TO `"+conf["db_name"]+"`@`%`;")
            print("GRANT ALL PRIVILEGES ON `"+conf["db_name"]+"`.* TO '"+conf["db_name"]+"'@'%';")
    except Exception as e:
        print("-- Error: Could not connect with site "+current_site_name)
        print(e)
        pass

@frappe.whitelist(allow_guest=True)
def add_custom_domain(site_name,custom_domain,user):
    if(not site_name):
        frappe.throw(_("Site Name is Required"))
    if(not custom_domain):
        frappe.throw(_("Site Name is Required"))
    
    commands = ["bench setup add-domain {custom_domain} --site {site_name}".format(custom_domain=custom_domain, site_name=site_name)]
    command_key = today() + " " + nowtime()
    frappe.enqueue('bench_manager.bench_manager.utils.run_command',
			commands=commands,
			doctype="Bench Settings",
			key=command_key,
            now=True
		)
    
    saas_site = frappe.get_doc("Saas Site",site_name)
    saas_site.custom_domain = custom_domain
    saas_site.command_key = command_key
    saas_site.domain_status = 'Unverified'
    saas_site.save(ignore_permissions=True)
    return True

@frappe.whitelist(allow_guest=True)
def remove_custom_domain(site_name,custom_domain,user):
    if(not site_name):
        frappe.throw(_("Site Name is Required"))
    if(not custom_domain):
        frappe.throw(_("Domain Name is Required"))
    
    commands = ["bench setup remove-domain {custom_domain} --site {site_name}".format(custom_domain=custom_domain,site_name=site_name)]
    commands.append("bench setup nginx --yes")
    commands.append("bench setup reload-nginx")
    command_key = today() + " " + nowtime()
    frappe.enqueue('bench_manager.bench_manager.utils.run_command',
			commands=commands,
			doctype="Bench Settings",
			key=command_key,
            is_async=False
		)
    saas_site = frappe.get_doc("Saas Site",site_name)
    saas_site.custom_domain = ""
    saas_site.domain_status = ""
    saas_site.save(ignore_permissions=True)
    return True

@frappe.whitelist(allow_guest=True)
def verify_domain(site_name,custom_domain,user):
    if(not site_name):
        frappe.throw(_("Site Name is Required"))
    if(not custom_domain):
        frappe.throw(_("Site Name is Required"))
    import socket
    custom_domain_ip = socket.gethostbyname(custom_domain)
    onehash_site_ip = socket.gethostbyname(site_name)
    if(onehash_site_ip!=custom_domain_ip):
        return False
    
    commands = []
    commands.append("sudo -H bench setup lets-encrypt {site_name} -n --custom-domain {custom_domain}".format(site_name=site_name, custom_domain=custom_domain))
    command_key = today() + " " + nowtime()
    frappe.enqueue('bench_manager.bench_manager.utils.run_command',
			commands=commands,
			doctype="Bench Settings",
			key=command_key,now=True,
            job_name=site_name+custom_domain
		)
    saas_site = frappe.get_doc("Saas Site",site_name)
    saas_site.custom_domain = custom_domain
    saas_site.domain_status = "Verified"
    saas_site.save(ignore_permissions=True)
    return True
