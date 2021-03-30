# -*- coding: utf-8 -*-
# Copyright (c) 2021, Vigneshwaran Arumainayagam and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.utils.password import get_decrypted_password
import json
import requests
import os

class FacebookIntegration(Document):
    def before_save(self):
        with open(os.getcwd()+'/common_site_config.json', 'r') as f:
            config = json.load(f)
        facebook_config = config.get("facebook_config") if config.get("facebook_config") else {}
        app_id = master_subscription_endpoint = master_domain = client_verify_token = facebook_verify_token = None
        if facebook_config:
            app_id = facebook_config.get("facebook_app_id")
            master_domain = facebook_config.get("master_domain")
            master_subscription_endpoint = facebook_config.get("master_subscription_endpoint")
            client_verify_token = facebook_config.get("client_verify_token")
            facebook_verify_token = facebook_config.get("facebook_verify_token")
        changes = False
        if self.app_id != app_id:
            facebook_config["facebook_app_id"] = self.app_id
            changes = True
        if self.master_domain != master_domain:
            facebook_config["master_domain"] = self.master_domain
            changes = True
        if self.master_subscription_endpoint != master_subscription_endpoint:
            facebook_config["master_subscription_endpoint"] = self.master_subscription_endpoint
            changes = True
        if self.client_verify_token != client_verify_token:
            facebook_config["client_verify_token"] = self.client_verify_token
            changes = True
        if self.facebook_verify_token != facebook_verify_token:
            facebook_config["facebook_verify_token"] = self.facebook_verify_token
            changes = True
        if changes:
            config["facebook_config"] = facebook_config
        with open(os.getcwd()+'/common_site_config.json', 'w') as f:
            json.dump(config, f, indent=1, sort_keys=True)

@frappe.whitelist(allow_guest=True)
def save_subscription(**kwargs):
    """
    Function to receive page_id and page_access_token from client and save in master's facebook clients
    """
    config = frappe.get_site_config()
    facebook_config = config.get("facebook_config") if config.get("facebook_config") else {}
    if not kwargs.get("verify_token") and kwargs.get("verify_token") != facebook_config.get("client_verify_token"):
        return "error"
    page_id, page_access_token, client_domain = kwargs.get("page_id"), kwargs.get("page_access_token"), kwargs.get("domain")
    user_id, user_access_token = kwargs.get("user_id"), kwargs.get("user_access_token")
    if page_id and user_id and user_access_token and page_access_token and client_domain:
        client = frappe.get_value("Facebook Clients", filters={"url": client_domain}, fieldname=["name"])
        app_id = facebook_config.get("facebook_app_id")
        if client:
            page = frappe.get_value("Facebook Pages", filters={"page_id": page_id}, fieldname=["name"])
            if page:
                page_doc = frappe.get_doc("Facebook Pages", page)
                # convert short-lived user token into long-lived page access token
                long_page_token = prolong_token(app_secret=get_decrypted_password("Facebook Integration", "Facebook Integration", "app_secret"),
                    short_user_token=user_access_token, user_id=user_id, client_domain=client_domain, app_id=app_id)
                page_doc.page_access_token = long_page_token
                page_doc.save(ignore_permissions=True)
            else:
                client_doc = frappe.get_doc("Facebook Clients", client)
                long_page_token = prolong_token(app_secret=get_decrypted_password("Facebook Integration", "Facebook Integration", "app_secret"),
                    short_user_token=user_access_token, user_id=user_id, client_domain=client_domain, app_id=app_id)
                client_doc.append("pages", {"page_id": page_id, "page_access_token": long_page_token})
                client_doc.save(ignore_permissions=True)
        else:
            client_doc = frappe.get_doc({
                "doctype": "Facebook Clients",
                "client": client_domain,
                "url": client_domain,
                "enabled": 1
            })
            long_page_token = prolong_token(app_secret=get_decrypted_password("Facebook Integration", "Facebook Integration", "app_secret"),
                short_user_token=user_access_token, user_id=user_id, client_domain=client_domain, app_id=app_id)
            client_doc.append("pages", {"page_id": page_id, "page_access_token": long_page_token})
            client_doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return "success"
    return "error"

def prolong_token(app_secret, short_user_token, user_id, client_domain, app_id):
    long_page_token = ""
    long_user_token = ""
    try:
        long_user_token = requests.get("https://graph.facebook.com/v10.0/oauth/access_token?grant_type=fb_exchange_token&client_id="
                            +app_id+"&client_secret="+app_secret+"&fb_exchange_token="+short_user_token)
        long_user_token = json.loads(long_user_token.text).get("access_token")
    except Exception as e:
        frappe.log_error("Error occured while fetching facebook client: {} long-lived user token: ".format(client_domain) + str(e), "Error Facebook Token")
    try:
        long_page_token = requests.get("https://graph.facebook.com/v10.0/"+user_id+"/accounts?access_token="+long_user_token)
        long_page_token = json.loads(long_page_token.text)["data"][0]["access_token"]
    except Exception as e:
        frappe.log_error("Error occured while fetching facebook client: {} long-lived page token: ".format(client_domain) + str(e), "Error Facebook Token")

    return long_page_token
