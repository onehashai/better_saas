# -*- coding: utf-8 -*-
# Copyright (c) 2020, Vigneshwaran Arumainayagam. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from bench_manager.bench_manager.doctype.site.site import create_site
from frappe.utils import today, nowtime, add_days
from frappe.utils.file_manager import get_file_path
import pathlib
from frappe.utils.background_jobs import enqueue
import requests
import math, random
from frappe.core.doctype.sms_settings.sms_settings import send_sms

class SaasUser(Document):
	pass

@frappe.whitelist(allow_guest=True)
def setup(account_request):
	saas_user = frappe.get_doc("Saas User",account_request)
	saas_settings = frappe.get_doc("Saas Settings")
	mysql_password = saas_settings.mysql_root_password
	admin_password = saas_user.password
	key = saas_user.key
	site_name = saas_user.subdomain + "." + saas_settings.domain

	# # create user 
	frappe.enqueue(create_user, timeout=2000, is_async = True, first_name = saas_user.first_name, last_name = saas_user.last_name, email = saas_user.email, password = saas_user.password)
	commands = ["bench new-site --mariadb-root-password {mysql_password} --admin-password {admin_password} {site_name}".format(site_name=site_name,
	admin_password=admin_password, mysql_password=mysql_password)]

	# creation of site and install erpnext
	if saas_settings.install_erpnext:
		install_erpnext = "true"
		commands.append("bench --site {site_name} install-app erpnext".format(site_name=site_name))
	else:
		install_erpnext = "false"
	
	# # add custom domains
	if saas_user.domain_type == "Private":
		custom_domain = saas_user.private_domain
	elif saas_user.domain_type == "Subdomain":
		custom_domain = saas_user.subdomain + "." + saas_settings.domain
		new_subdomain = frappe.new_doc("Saas Domains")
		new_subdomain.domain = saas_user.subdomain
		new_subdomain.insert(ignore_permissions=True)	
	commands.append("bench setup add-domain {custom_domain} --site {site_name}".format(custom_domain=custom_domain, site_name=site_name))

	# # setup nginx config and reloading the nginx service
	commands.append("bench setup nginx --yes")
	commands.append("bench setup reload-nginx")
	
	# limit_users = int(saas_settings.default_limit_for_users) 
	# limit_emails = int(saas_settings.default_limit_for_emails)
	# limit_space = int(saas_settings.default_limit_for_space)
	# limit_email_group = int(saas_settings.default_limit_for_email_group)
	# limit_expiry = add_days(today(), int(saas_settings.default_expiry))

	# commands.append("bench --site {site_name} set-limits --limit users {limit_users} --limit emails {limit_emails} --limit space {limit_space} --limit email_group {limit_email_group} --limit expiry {limit_expiry}".format(
	# 	site_name = site_name,
	# 	limit_users = limit_users,
	# 	limit_emails = limit_emails,
	# 	limit_space = limit_space,
	# 	limit_email_group = limit_email_group,
	# 	limit_expiry = limit_expiry
	# ))
	command_key = today() + " " + nowtime()
	frappe.enqueue('bench_manager.bench_manager.utils.run_command',
		commands=commands,
		doctype="Bench Settings",
		key=command_key
	)
	
	saas_site = frappe.new_doc("Saas Site")
	saas_site.site_name = site_name
	saas_site.site_status = "Active"
	# saas_site.limit_for_users = limit_users
	# saas_site.limit_for_emails = limit_emails
	# saas_site.limit_for_space = limit_space
	# saas_site.limit_for_email_group = limit_email_group
	# saas_site.expiry = limit_expiry
	saas_site.insert(ignore_permissions=True)
	saas_user.linked_saas_site = saas_site.name
	saas_user.linked_saas_domain = new_subdomain.name
	saas_user.key = command_key
	saas_user.save()

@frappe.whitelist(allow_guest=True)
def get_status(account_request):
	doc = frappe.get_doc("Saas User",account_request)
	commandStatus = frappe.get_doc("Bench Manager Command",doc.key)
	if(doc.linked_saas_domain and commandStatus.status=="Success"):
		create_first_user_on_target_site(doc)
		result = {}
		result['user'] = doc.email
		result['password'] = doc.password
		result['link'] = "https://"+doc.linked_saas_site
		return result
	else:
		return {}
	
def create_first_user_on_target_site(site_user):
	domain = site_user.linked_saas_site
	site_password = site_user.password
	is_new_user = False
	from better_saas.better_saas.doctype.saas_user.frappeclient import FrappeClient
	conn = FrappeClient("https://"+domain, "Administrator", site_password)
	try:
		user = conn.get_doc("User",site_user.email)		
	except:
		user = False		
		pass
	if(not user):		
		conn.insert({
		"doctype": "User",
		"first_name": site_user.first_name,
		"last_name": site_user.last_name,
		"email": site_user.email,
		"send_welcome_email":0,	
		"new_password":site_user.password,
		"enabled":1
		})
		is_new_user = True

	user = conn.get_doc("User",site_user.email)
	role_list = conn.get_list("Role",['name'],limit_page_length=1000,filters = [['Role','name','not in',["Administrator", "Guest", "All", "Customer", "Supplier", "Partner", "Employee"]]])
	for role in role_list:
		user['roles'].append({"role":role['name']})
	conn.update(user)

	if(is_new_user):
		STANDARD_USERS = ("Guest", "Administrator")
		subject="Welcome to OneHash"
		template="welcome_email"
		args = {
				'first_name': site_user.first_name or site_user.last_name or "user",
				'user': site_user.email,
				'title': subject,
				'login_url': "https://"+site_user.linked_saas_site,
				'site_url': "https://"+site_user.linked_saas_site,
				'help_url':"https://help.onehash.ai",
				'user_fullname': site_user.first_name+" "+site_user.last_name
			}
		sender = frappe.session.user not in STANDARD_USERS and get_formatted_email(frappe.session.user) or None
		frappe.sendmail(recipients=site_user.email, sender=sender, subject=subject,
				template=template, args=args, header=[subject, "green"],
				delayed=False)
	return True
	
def create_user(first_name, last_name, email, password):
	new_user = frappe.new_doc("User")
	new_user.first_name = first_name
	new_user.last_name = last_name
	new_user.email = email
	new_user.send_welcome_email=0
	new_user.flags.no_welcome_mail=True	
	new_user.insert(ignore_permissions=True)
	user = frappe.get_doc("User", new_user.name)
	user.new_password = password
	user.save(ignore_permissions=True)
	frappe.db.commit()

@frappe.whitelist()
def delete_site(site_name):
	saas_settings = frappe.get_doc("Saas Settings")
	mysql_password = saas_settings.mysql_root_password
	site = frappe.get_doc("Saas User", {"linked_saas_site": site_name})
	site.delete()
	user = frappe.get_doc("User", site.email)
	user.delete()
	domain = frappe.get_doc("Saas Domains", site.linked_saas_domain)
	domain.delete()
	saas_site = frappe.get_doc("Saas Site", site.linked_saas_site)
	saas_site.delete()
	
	commands = ["bench drop-site {site_name} --root-password {mysql_password}".format(site_name=site_name, mysql_password=mysql_password)]
	commands.append("bench setup nginx --yes")
	commands.append("bench setup reload-nginx")
	frappe.enqueue('bench_manager.bench_manager.utils.run_command',
		commands=commands,
		doctype="Bench Settings",
		key=today() + " " + nowtime()
	)

@frappe.whitelist()
def disable_enable_site(site_name, status):
	if status == "Active":
		commands = ["bench --site {site_name} set-maintenance-mode on".format(site_name=site_name)]
	else:
		commands = ["bench --site {site_name} set-maintenance-mode off".format(site_name=site_name)]

	frappe.enqueue('bench_manager.bench_manager.utils.run_command',
		commands=commands,
		doctype="Bench Settings",
		key=today() + " " + nowtime()
	)

@frappe.whitelist(allow_guest=True)
def check_subdomain_avai(subdomain):
	saas_settings = frappe.get_doc("Saas Settings")
	if frappe.db.exists("Saas Domains", {"domain": subdomain}):
		status = "False"
	else:
		if saas_settings.include_management_site_subdomain and saas_settings.management_subdomain == subdomain:
			status = "False"
		else:
			status = "True"

	return {"status": status}

@frappe.whitelist(allow_guest=True)
def check_email_avai(email):
	if frappe.db.exists("User", email):
		status = "False"
	else:
		status = "True"

	return {"status": status}


@frappe.whitelist()
def apply_new_limits(limit_for_users, limit_for_emails, limit_for_space, limit_for_email_group, expiry, site_name):
	commands = ["bench --site {site_name} set-limits --limit users {limit_users} --limit emails {limit_emails} --limit space {limit_space} --limit email_group {limit_email_group} --limit expiry {limit_expiry}".format(
		site_name = site_name,
		limit_users = limit_for_users,
		limit_emails = limit_for_emails,
		limit_space = limit_for_space,
		limit_email_group = limit_for_email_group,
		limit_expiry = expiry
	)]
	
	frappe.enqueue('bench_manager.bench_manager.utils.run_command',
		commands=commands,
		doctype="Bench Settings",
		key=today() + " " + nowtime()
	)

@frappe.whitelist()
def get_users_list(site_name):
	saas_settings = frappe.get_doc("Saas Settings")
	site = frappe.get_doc("Saas User", {"linked_saas_site": site_name})
	site_password = site.password
	domain = site.linked_saas_domain
	domain = domain + "." + saas_settings.domain
	from better_saas.better_saas.doctype.saas_user.frappeclient import FrappeClient
	conn = FrappeClient("https://"+domain, "Administrator", site_password)
	total_users = conn.get_list('User', fields = ['name', 'first_name', 'last_name', 'enabled'])
	active_users = conn.get_list('User', fields = ['name', 'first_name', 'last_name'], filters = {'enabled':'1'})
	return {"total_users":total_users, "active_users":active_users}

@frappe.whitelist(allow_guest=True)
def signup(subdomain,first_name,last_name,phone_number,email,passphrase,plan=None):
	import re
	phone_number = re.sub(r"[^0-9]","",phone_number)
	sass_user = frappe.get_doc({
			"doctype":"Saas User",
			"email": email,
			"mobile": phone_number,
			"first_name": first_name,
			"last_name": last_name,
			"subdomain": subdomain,
			"confirm_password":passphrase,
			"password":passphrase,
			"otp": generate_otp()
		})

	sass_user.flags.ignore_permissions = True
	result = sass_user.insert()
	lead = create_lead(result)
	doc = frappe.get_doc("Saas User",result.name)
	doc.otp = generate_otp()
	doc.save()
	send_otp_sms(doc.mobile,doc.otp)

	final_result = {}
	final_result["location"] = "verify"
	final_result["reference"] = result.name
	final_result['email'] = email
	return final_result

def create_lead(saas_user):
	lead = frappe.get_doc({
			"doctype":"Lead",
			"email_id": saas_user.email,
			"mobile_no": saas_user.mobile
		})
	lead.lead_name = saas_user.first_name+" "+saas_user.last_name
	lead.source = "Walk In"
	lead.flags.ignore_permissions = True
	return lead.insert()	


@frappe.whitelist(allow_guest=True)
def resend_otp(id):
	doc = frappe.get_doc("Saas User",id)
	doc.otp = generate_otp()
	doc.save()
	send_otp_sms(doc.mobile,doc.otp)
	frappe.msgprint("Verification code has been sent to registered email id and mobile.")

@frappe.whitelist(allow_guest=True)
def verify_account_request(id,otp):
	doc = frappe.get_doc("Saas User",id)
	if(doc.otp!=otp):
		frappe.throw("The OTP you entered could not be authenticated. Please try again","ValidationError")
	else:
		result = {}				
		result['location'] = "#account-setup"
		return result

@frappe.whitelist(allow_guest=True)
def update_account_request(id,country=None,industry_type=None,currency=None,language=None,timezone=None,domain=None):
	#doc = frappe.get_doc("Saas User",id)
	result = {}	
	if(industry_type):
		result['location'] = "#other-details"
	else:
		result['location'] = "../prepare_site"
	return result

def generate_otp():  
    # Declare a digits variable
    # which stores all digits
    digits = "0123456789"
    OTP = ""  
   # length of password can be chaged 
   # by changing value in range 
    for i in range(6) : 
        OTP += digits[math.floor(random.random() * 10)]  
    return OTP

def send_otp_sms(number,otp):
	receiver_list = []
	receiver_list.append(number)
	message = otp+" is OTP to verify your account request for OneHash."
	send_sms(receiver_list,message)