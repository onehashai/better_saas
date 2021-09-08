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
			if frappe.get_value("Facebook Forms", self.form_id, "enabled") == 0:
				self.status = "Failed"
				self.save()
				frappe.log_error("Facebook Form is disabled for facebook leadgen: "+self.name, 'Facebook Form Disabled')
			else:
				client, page_access_token = frappe.get_value("Facebook Pages", filters={"page_id": self.page_id}, fieldname=["parent", "page_access_token"])
				if page_access_token:
					self.status = "Queued"
					self.save()
					frappe.utils.background_jobs.enqueue(lead_insertion, queue='default', timeout=None, event=None,	is_async=True, 
						job_name=None, now=False, enqueue_after_commit=False, doc=self, client=client, page_access_token=page_access_token)
				else:
					self.status = "Failed"
					self.save()
					frappe.log_error("Page access token was not found for facebook leadgen: "+self.name, 'No Facebook Page Access Token')
			frappe.db.commit()

def lead_insertion(doc, client, page_access_token):
	master_site = frappe.local.site
	try:
		lead_data = requests.get("https://graph.facebook.com/v10.0/"+doc.leadgen_id+"?access_token="+page_access_token)
		lead_data = json.loads(lead_data.text)
	except Exception as e:
		doc.status = "Failed"
		doc.save()
		frappe.log_error("Error occured while fetching facebook leadgen data for leadgen id: {} ".format(doc.leadgen_id) + frappe.get_traceback(), "Error Facebook Leadgen")
		return

	#facebook form fields: lead label
	field_mapping = {}

	if doc.form_id:
		try:
			fm_docs = frappe.get_doc("Facebook Forms", doc.form_id).get("field_mapping")
			for fm in fm_docs:
				if fm.lead_field_label != "Do Not Map":
					field_mapping[fm.facebook_fieldname] = [fm.lead_fieldname, fm.lead_field_type]
		except:
			doc.status = "Failed"
			doc.save()
			frappe.log_error("Facebook Form {} not found for leadgen id: {} \n".format(doc.form_id, doc.leadgen_id) + frappe.get_traceback(), "Error: Facebook Form Not Found")
			return

	lead_doc = {"doctype": "Lead", "source": "Facebook"}
	if lead_data and lead_data.get("error"):
		doc.status = "Failed"
		doc.save()
		frappe.log_error("Facebook leadgen data fetch produced this error: "+str(lead_data.get("error")), "Error Facebook Leadgen")
		return
	else:
		for data in lead_data["field_data"]:
			if data["name"] in field_mapping:
				if data["name"] == "country":
					country_name = frappe.get_value("Country", filters={"code": data["values"][0].lower()}, fieldname=["name"])
					lead_doc[field_mapping[data["name"]][0]] = country_name if country_name else ""
					continue
				if field_mapping[data["name"]][1] == "Date":
					lead_doc[field_mapping[data["name"]][0]] = frappe.utils.getdate(data["values"][0])
					continue
				if field_mapping[data["name"]][1] == "Datetime":
					lead_doc[field_mapping[data["name"]][0]] = frappe.utils.get_datetime(frappe.utils.format_datetime(data["values"][0]))
					continue					
				lead_doc[field_mapping[data["name"]][0]] = data["values"][0]
		try:
			if "address_line1" not in lead_doc:
				lead_doc["address_line1"] = "default address_line1"
			if "city" not in lead_doc:
				lead_doc["city"] = "default city"

			client_domain = frappe.get_value("Facebook Clients", client, "url")
			frappe.local.initialised = False
			frappe.connect(site=client_domain)
			lead_doc = frappe.get_doc(lead_doc)					
			res = lead_doc.insert(ignore_permissions=True, ignore_mandatory=True)# ignore_links=True)
			frappe.db.commit()
			frappe.destroy()
			frappe.local.initialised = False
			frappe.connect(site=master_site)
		except Exception as e:
			res = {}
			frappe.local.initialised = False
			frappe.connect(site=master_site)
			frappe.log_error("Error occured while saving lead into client: {} :".format(client_domain)+frappe.get_traceback(), 
				"Error Saving Facebook Lead")
		if res.get("name"):
			doc.status = "Success"
			doc.save()
		else:
			doc.status = "Failed"
			doc.save()
			frappe.log_error("Saving lead on client's system: {} failed for leadgen id: {}".format(client_domain, doc.leadgen_id), "Facebook Lead Creation Failed")

