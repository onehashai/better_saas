# -*- coding: utf-8 -*-
# Copyright (c) 2021, Vigneshwaran Arumainayagam and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
import json
from frappe.model.document import Document
from frappe.utils import nowdate, nowtime, add_days, getdate
from better_saas.better_saas.doctype.saas_user.saas_user import delete_site

class SiteDeletionConfiguration(Document):
	pass

def check_deletable_sites():
    site_deletion_config = frappe.get_doc("Site Deletion Configuration", "Site Deletion Configuration")
    if not site_deletion_config.enabled:
        return
    if not site_deletion_config.run_at_interval:
        return
    
    curtime = nowtime()
    if curtime[:2] == "00":
        curtime = "24" + curtime[2:]

    if int(curtime[:2]) % int(site_deletion_config.run_at_interval) != 0:
        return

    check_sites()

def check_sites():
    try:
        site_deletion_config = frappe.get_doc("Site Deletion Configuration", "Site Deletion Configuration")        
        inactive_days = site_deletion_config.inactive_for_days
        inactive_days = -inactive_days if inactive_days > 0 else inactive_days
        
        intermittent_warning_days = site_deletion_config.intermittent_warning_day
        warning_days = site_deletion_config.warning_days   
        limit = site_deletion_config.limit
        expired_days = site_deletion_config.expired_for_days
        expired_days = -expired_days if expired_days > 0 else expired_days
        
        # check for sites which got recent activity but has some warning level
        # and remove their warning level
        active_list = frappe.get_list("Saas Site", filters={
        'last_activity_time': ['>', add_days(getdate(nowdate()), days=inactive_days)],
        'expiry': ['>', add_days(getdate(nowdate()), days=expired_days)],
        'warning_level': ['!=', ""]
        })

        if active_list:
            for active in active_list:
                doc = frappe.get_doc("Saas Site", active.get("name"))
                doc.warning_level = ""
                doc.warning_date = ""
                doc.save() 
        
        # check for sites which are past "inactive days" and "expiry" by limits and have no "subscription"
        # change their warning_level or delete site
        inactive_sites = frappe.get_list("Saas Site", filters={
            'last_activity_time': ['<', add_days(getdate(nowdate()), days=inactive_days)], 
            'expiry': ['<', add_days(getdate(nowdate()), days=expired_days)],
            "subscription": ""
            },
            fields=['name'], order_by='last_activity_time desc')
        
        if inactive_sites:
            chunks_list = list(chunks(inactive_sites, 20))
            for chunk in chunks_list:
                frappe.utils.background_jobs.enqueue(process_list, queue='default', timeout=None, event=None, is_async=True, 
						job_name=None, now=False, enqueue_after_commit=False, inter_warning_days=intermittent_warning_days, warning_days=warning_days, site_list=chunk, limit=limit)

        frappe.db.commit()
    except:
        frappe.log_error(frappe.get_traceback(), "Site Deletion Error")

def chunks(l, n):
    n = max(1, n)
    return (l[i:i+n] for i in range(0, len(l), n))

def process_list(inter_warning_days, warning_days, site_list=None, limit=20):
    if not site_list:
        return
    try:
        sites_to_delete = []
        for site in site_list:
            doc = frappe.get_doc("Saas Site", site.get("name"))

            # save user in saas_site if not present
            if doc and not doc.user:
                saas_user = frappe.db.get_value('Saas User', {'linked_saas_site': doc.name}, ['name'])
                if saas_user:
                    saas_user = frappe.get_doc("Saas User", saas_user)
                    email = saas_user.email
                    user = frappe.db.get_value("User", {"name": email})
                    if user:
                        doc.user = user
                        doc.save(ignore_permissions=True)
                
            if doc.warning_level in ["", None]:
                #notification set for 1st mail trigger on warning_level
                doc.warning_level = "Initial Warning"
                doc.warning_date = nowdate()
                doc.save()
            elif doc.warning_level == "Initial Warning" and getdate(nowdate()) == add_days(doc.warning_date, days=inter_warning_days):
                #notification set for 2nd mail trigger on warning_level
                doc.warning_level = "Intermittent Warning"
                doc.save()
            elif doc.warning_level == "Intermittent Warning" and getdate(nowdate()) == add_days(doc.warning_date, days=warning_days):
                #notification set for 3rd mail trigger on warning_level
                doc.warning_level = "Deletion Approved"
                doc.save()
            elif doc.warning_level == "Deletion Approved":
                if len(sites_to_delete) < limit:
                    sites_to_delete.append(doc.name)
        if sites_to_delete:
            for site in sites_to_delete:
                frappe.log_error(site, "Site Deletion Initiated")
                frappe.utils.background_jobs.enqueue(delete_site, queue='default', timeout=None, event=None, is_async=True, 
                            job_name=None, now=False, enqueue_after_commit=False, site_name=site)
        frappe.db.commit()
    except:
        frappe.log_error(frappe.get_traceback(), "Site Deletion Error")