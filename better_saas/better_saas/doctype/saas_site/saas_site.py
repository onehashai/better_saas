# -*- coding: utf-8 -*-
# Copyright (c) 2020, Vigneshwaran Arumainayagam and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
import json
import journeys
from frappe.model.document import Document
from journeys.addon_limits import update_limits

class SaasSite(Document):
    pass            

@frappe.whitelist()
def update_addon_limits(addon_limits,site_name):
    #return json.loads(addon_limits)
    limit_dict = {}
    for limit in json.loads(addon_limits):
        limit_dict[limit["service_name"]]=limit
    return update_limits(limit_dict,site_name=site_name)

def update_user_to_main_app():
    admin_site_name = "admin_onehash"
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
            print(e)
        finally:
            frappe.destroy()

def get_all_database_config():
    try:
        admin_site_name = "admin_onehash"
        frappe.destroy()
        frappe.init(site=admin_site_name)
        frappe.connect()
        all_sites = frappe.get_all("Saas Site")
        for site in all_sites:
            frappe.destroy()
            current_site_name = site.name
            frappe.init(site=current_site_name)
            frappe.connect()
            conf = frappe.local.conf
            #print(current_site_name+","+conf['db_name']+","+conf['db_password']+"\r\n")
            print("CREATE USER '"+conf['db_name']+"'@'%' IDENTIFIED BY '"+conf['db_password']+"';")
            print("GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, INDEX, ALTER, CREATE TEMPORARY TABLES, CREATE VIEW, EVENT, TRIGGER, SHOW VIEW, CREATE ROUTINE, ALTER ROUTINE, EXECUTE ON "+conf["db_name"]+".* TO `"+conf["db_name"]+"`@`%`;")

    except Exception as e:
        pass