# -*- coding: utf-8 -*-
# Copyright (c) 2021, Vigneshwaran Arumainayagam and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
import journeys
from frappe import _
import json
from frappe.model.document import Document

class ProfileEnrichArchive(Document):
	pass

def insert_profile_enrich_archive(profile_enrich_request):
	journeys.connect_admin_db()
	profile_enrich_archive = frappe.get_doc({
		"doctype":"Profile Enrich Archive",
		"reference_doctype":profile_enrich_request.reference_doctype,
		"reference_docname":profile_enrich_request.reference_docname,
		"email":profile_enrich_request.email,
		"mobile_no":profile_enrich_request.mobile_no,
		"reference_profile_enrich_request":profile_enrich_request.name,
		"requested_by":profile_enrich_request.owner,
		"status":"Queued",
		"reference_site":profile_enrich_request.reference_profile_enrich_site
	}).insert(ignore_permissions=True)
	frappe.db.commit()
	journeys.destroy_admin_connection()
	return profile_enrich_archive

def update_profile_enrich_archive_request(profile_enrich, profile_enrich_archive, profile_enrich_request):
	journeys.connect_admin_db()
	profile_enrich_archive_name = profile_enrich_archive.name
	profile_enrich_archive = frappe.get_doc('Profile Enrich Archive',profile_enrich_archive_name)
	message, request_data, traceback, status = parse_profile_enrich_response(profile_enrich)
	profile_enrich_archive.message = message
	profile_enrich_archive.request_data = json.dumps(request_data, indent=1)
	profile_enrich_archive.traceback = traceback
	profile_enrich_archive.status=status
	profile_enrich_archive.save()
	frappe.db.commit()
	journeys.destroy_admin_connection()
	return update_profile_enrich_request(profile_enrich_archive,profile_enrich_request)
	


def update_profile_enrich_request(profile_enrich_archive,profile_enrich_request):
	journeys.switch_to_site_db()
	profile_enrich_request = frappe.get_doc('Profile Enrich Request',profile_enrich_request.name)
	profile_enrich_request.request_data = profile_enrich_archive.request_data
	profile_enrich_request.traceback = profile_enrich_archive.traceback
	profile_enrich_request.message = profile_enrich_archive.message
	profile_enrich_request.status=profile_enrich_archive.status
	profile_enrich_request.save(ignore_permissions=True)
	frappe.db.commit()
	return profile_enrich_request

def parse_profile_enrich_response(profile_enrich):
	message=""
	request_data=""
	traceback = ""
	#print("Insta Summary",profile_enrich)
	if("Response" in profile_enrich and profile_enrich['Response']['Status']=='error'):
		message = _(str(profile_enrich['Response']['Type']))
		traceback = frappe.get_traceback()
		request_data = profile_enrich['Response']
		status = "Error"
		company_name=""
	else:
		request_data = profile_enrich
		status = "Success"
	return message,request_data,traceback,status

