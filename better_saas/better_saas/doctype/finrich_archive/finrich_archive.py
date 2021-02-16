# -*- coding: utf-8 -*-
# Copyright (c) 2021, Vigneshwaran Arumainayagam and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
import journeys
from frappe import _
import json
from frappe.model.document import Document

class FinRichArchive(Document):
	pass

def insert_finrich_archive(finrich_request):
	journeys.connect_admin_db()
	finrich_archive = frappe.get_doc({
		"doctype":"FinRich Archive",
		"reference_doctype":finrich_request.reference_doctype,
		"reference_docname":finrich_request.reference_docname,
		"cin":finrich_request.cin,
		"reference_finrich_request":finrich_request.name,
		"requested_by":finrich_request.owner,
		"status":"Queued",
		"reference_site":finrich_request.reference_finrich_site
	}).insert(ignore_permissions=True)
	frappe.db.commit()
	return finrich_archive

def update_finrich_archive_request(insta_summary,finrich_archive):
	journeys.connect_admin_db()
	finrich_archive_name = finrich_archive.name
	finrich_archive = frappe.get_doc('FinRich Archive',finrich_archive_name)
	message, request_data, traceback, status,company_name = parse_insta_summary_response(insta_summary)
	finrich_archive.message = message
	finrich_archive.request_data = json.dumps(request_data, indent=1)
	finrich_archive.traceback = traceback
	finrich_archive.status=status
	finrich_archive.company_name = company_name
	finrich_archive.save()
	frappe.db.commit()
	return update_finrich_request(finrich_archive)
	


def update_finrich_request(finrich_archive):
	journeys.switch_to_site_db()
	finrich_request = frappe.get_doc('FinRich Request',finrich_archive.reference_finrich_request)
	finrich_request.request_data = finrich_archive.request_data
	finrich_request.traceback = finrich_archive.traceback
	finrich_request.message = finrich_archive.message
	finrich_request.status=finrich_archive.status
	finrich_request.company_name = finrich_archive.company_name
	finrich_request.save(ignore_permissions=True)
	frappe.db.commit()
	return finrich_request

def parse_insta_summary_response(insta_summary):
	message=""
	request_data=""
	traceback = ""
	#print("Insta Summary",insta_summary)
	if("Response" in insta_summary and insta_summary['Response']['Status']=='error'):
		message = _(str(insta_summary['Response']['Type']))
		traceback = frappe.get_traceback()
		request_data = insta_summary['Response']
		status = "Error"
		company_name=""
	else:
		request_data = insta_summary
		company_name = request_data["InstaSummary"]["CompanyMasterSummary"]["CompanyName"]
		status = "Success"
	return message,request_data,traceback,status,company_name
