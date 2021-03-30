# -*- coding: utf-8 -*-
# Copyright (c) 2021, Vigneshwaran Arumainayagam and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
import requests
import json

class FacebookLeadgen(Document):
	def after_insert(self):
		if self.page_id and self.leadgen_id and self.status:
			client, page_access_token = frappe.get_value("Facebook Pages", filters={"page_id": self.page_id}, fieldname=["parent", "page_access_token"])
			if page_access_token:
				self.status = "Queued"
				self.save()
				frappe.utils.background_jobs.enqueue(lead_insertion, queue='default', timeout=None, event=None,	is_async=True, 
					job_name=None, now=False, enqueue_after_commit=False, doc=self, client=client, page_access_token=page_access_token)
			else:
				self.status = "Failed"
				self.save()
				frappe.log_error("Page access token was not found for facebook leadgen: "+self.name, 'No Page Access Token')
			frappe.db.commit()

def lead_insertion(doc, client, page_access_token):
	master_site = frappe.local.site
	try:
		lead_data = requests.get("https://graph.facebook.com/v10.0/"+doc.leadgen_id+"?access_token="+page_access_token)
		lead_data = json.loads(lead_data.text)
	except Exception as e:
		doc.status = "Failed"
		doc.save()
		frappe.log_error("Error occured while fetching facebook leadgen data for leadgen id: {} ".format(doc.leadgen_id) + str(e), "Error Facebook Leadgen")
	#facebook form fields: lead field
	field_mapping = {
		"city": "city",
		"state": "state",
		"gender": "gender",
		"email":  "email_id",
		"country":   "country",
		"full_name": "lead_name",
		"phone_number":"mobile_no",
		"company_name": "company_name"
		}
	lead_doc = {"doctype": "Lead"}
	if lead_data and lead_data.get("error"):
		doc.status = "Failed"
		doc.save()
		frappe.log_error("Facebook leadgen data fetch produced this error: "+str(lead_data.get("error")), "Error Facebook Leadgen")
	else:
		for data in lead_data["field_data"]:
			if data["name"] in field_mapping:
				lead_doc[field_mapping[data["name"]]] = data["values"][0]
		try:
			client_domain = frappe.get_value("Facebook Clients", client, "url")
			frappe.local.initialised = False
			frappe.connect(site=client_domain)
			lead_doc = frappe.get_doc(lead_doc)					
			res = lead_doc.insert(ignore_permissions=True)
			frappe.db.commit()
			frappe.destroy()
			frappe.local.initialised = False
			frappe.connect(site=master_site)
		except Exception as e:
			res = {}
			frappe.local.initialised = False
			frappe.connect(site=master_site)
			frappe.log_error("Error occured while saving lead into client: {} :".format(client_domain)+str(e), 
				"Error Saving Lead")
		if res.get("name"):
			doc.status = "Success"
			doc.save()
		else:
			doc.status = "Failed"
			doc.save()
			frappe.log_error("Saving lead on client's system: {} failed for leadgen id: {}".format(client_domain, doc.leadgen_id), "Lead Creation Failed")
