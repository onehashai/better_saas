# -*- coding: utf-8 -*-
# Copyright (c) 2020, Vigneshwaran Arumainayagam. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.sessions import get_geo_ip_country
from frappe.utils.data import getdate
from frappe.utils import today, nowtime, add_days, get_formatted_email
from frappe import _, throw
import math, random, re, time, os, json,requests
from frappe.core.doctype.sms_settings.sms_settings import send_sms
from frappe.core.doctype.user.user import test_password_strength
from frappe.utils.password import get_decrypted_password

class SaasUser(Document):
	def get_login_sid(self):
		password = get_decrypted_password("Saas User", self.name, "password")
		response = requests.post(
			f"https://{self.linked_saas_site}/api/method/login",
			data={"usr": "Administrator", "pwd": password},
		)
		sid = response.cookies.get("sid")
		if sid:
			return sid
	pass

@frappe.whitelist()
def login(name,reason=None):
	return frappe.get_doc("Saas User",name).get_login_sid()
	pass

@frappe.whitelist(allow_guest=True)
def setup(account_request):
	try:			
		saas_user = frappe.get_doc("Saas User",account_request)
		saas_settings = frappe.get_doc("Saas Settings")
		mysql_password = saas_settings.mysql_root_password
		admin_password = get_decrypted_password("Saas User", saas_user.password, "password")
		key = saas_user.key
		site_name = saas_user.subdomain + "." + saas_settings.domain
		bench_path,bench,install_apps = frappe.db.get_value("OneHash Product",saas_user.product,["bench_path","bench","install_apps"]) if saas_user.product else ("/home/frappe/frappe-bench","Frappe Bench","")
		install_apps = " ".join(list(set(install_apps.replace("\n",",").split(",") + ["erpnext", "journeys"])))
		## create user 
		frappe.enqueue(create_user, timeout=2000, is_async = True, first_name = saas_user.first_name, last_name = saas_user.last_name, email = saas_user.email, password = saas_user.password)
		
		# check if stock site available
		stock_list = frappe.get_list("Stock Sites", filters={"status":"Available","bench":bench}, order_by='creation asc', ignore_permissions=True)
		stock_site_doc = None
		if stock_list:
			stock_site = stock_list[0].get("name")
			stock_site_doc = frappe.get_doc("Stock Sites", stock_site, ignore_permissions=True)
			stock_site_doc.status = "Picked"
			stock_site_doc.save(ignore_permissions=True)
			commands = ["mv sites/{} sites/{}".format(stock_site, site_name)]
			commands.append("bench --site {} set-admin-password '{}'".format(site_name, admin_password))
		else:
			commands = ["bench new-site --mariadb-root-password {mysql_password} --admin-password {admin_password} {site_name}".format(site_name=site_name,
			admin_password=admin_password, mysql_password=mysql_password)]

			# creation of site and install erpnext
			if saas_settings.install_erpnext:
				install_erpnext = "true"
				commands.append("bench --site {site_name} install-app {install_apps}".format(site_name=site_name,install_apps=install_apps))
			else:
				install_erpnext = "false"
		
		# # add custom domains
		if saas_user.domain_type == "Private":
			custom_domain = saas_user.private_domain
			commands.append("bench setup add-domain {custom_domain} --site {site_name}".format(custom_domain=custom_domain, site_name=site_name))
		elif saas_user.domain_type == "Subdomain":
			custom_domain = saas_user.subdomain + "." + saas_settings.domain
			new_subdomain = frappe.new_doc("Saas Domains")
			new_subdomain.domain = saas_user.subdomain
			new_subdomain.insert(ignore_permissions=True)	

		# # setup nginx config and reloading the nginx service
		master_site_name = frappe.conf.get("master_site_name") or "admin_onehash"
		commands.append("bench setup nginx --yes")
		commands.append("bench setup reload-nginx")
		# commands.append("bench --site "+master_site_name+" execute better_saas.better_saas.doctype.saas_user.saas_user.create_first_user_on_target_site --args="+'"'+"['{saas_user}']".format(master_site_name=master_site_name,saas_user=saas_user.name)+'"')
		limit_users,limit_emails, limit_space, limit_email_group,limit_expiry,discounted_users,customer = get_site_limits(saas_user.promocode,saas_settings)
		site_limits = {
			"email_group":limit_email_group,
			"emails":limit_emails,
			"expiry":limit_expiry,
			"space":limit_space,
			"users":limit_users
		}
		commands.append("bench --site {site_name} set-config -p limits '{site_limits}'".format(site_name=site_name,site_limits=json.dumps(site_limits)))
		command_key = today() + " " + nowtime()
		
		
		saas_site = frappe.new_doc("Saas Site")
		saas_site.site_name = site_name
		saas_site.site_status = "Active"
		saas_site.discounted_users = discounted_users
		saas_site.limit_for_users = limit_users
		saas_site.limit_for_emails = limit_emails
		saas_site.limit_for_space = limit_space
		saas_site.limit_for_email_group = limit_email_group
		saas_site.customer = customer
		saas_site.bench = bench
		saas_site.expiry = limit_expiry
		saas_site.base_plan = saas_settings.base_plan_india if saas_user.country=="India" else saas_settings.base_plan_international
		if frappe.db.exists({'doctype': 'User','name': saas_user.email}):
			saas_user.user = saas_user.email
		saas_site.set_secret_key()
		saas_site.insert(ignore_permissions=True)
		saas_user.linked_saas_site = saas_site.name
		saas_user.bench = saas_site.bench
		saas_user.linked_saas_domain = new_subdomain.name
		saas_user.key = command_key
		saas_user.save()

		commands.append(f"bench --site {site_name} set-config sk_onehash {saas_site.secret_key}")
		frappe.enqueue('bench_manager.bench_manager.utils.run_command',
			commands=commands,
			doctype="Bench Settings",
			key=command_key,
			now=True,
			cwd = bench_path
		)
		# Redeem Promocode
		if saas_user.promocode:
			promocode = frappe.get_doc("Coupon Code",{"coupon_code":saas_user.promocode}, ignore_permissions=True)
			promocode.status="Redeemed"
			promocode.linked_saas_site = saas_site.name
			promocode.used = int(promocode.used)+1
			promocode.save(ignore_permissions=True)

		# link site with Lead
		doc = frappe.get_doc("Lead",{"email_id":saas_user.email})
		doc.linked_saas_site = saas_site.name
		doc.save(ignore_permissions=True)

		if stock_site_doc:
			stock_site_doc.assigned_to = saas_user.name
			stock_site_doc.renamed = site_name
			stock_site_doc.save(ignore_permissions=True)
	except:
		frappe.log_error(frappe.get_traceback())

def get_site_limits(promocode,saas_settings):	
	coupon_code = frappe.get_doc("Coupon Code",{"coupon_code":promocode}) if promocode else None
	discounted_users = coupon_code.discounted_users if coupon_code and coupon_code.discounted_users else 0
	limit_emails = int(coupon_code.limit_for_emails) if coupon_code and int(coupon_code.limit_for_emails) else int(saas_settings.default_limit_for_emails)
	limit_space = int(coupon_code.limit_for_space) if coupon_code and int(coupon_code.limit_for_space) else int(saas_settings.default_limit_for_space)
	limit_email_group = int(coupon_code.limit_for_email_group) if coupon_code and int(coupon_code.limit_for_email_group) else int(saas_settings.default_limit_for_email_group)
	limit_users =  0 if coupon_code and coupon_code.unlimited_users else (int(coupon_code.limit_for_users) if coupon_code and coupon_code.limit_for_users else int(saas_settings.default_limit_for_users) ) ## Applying Users count from promocode
	customer = coupon_code.customer if coupon_code else ""
	if coupon_code and coupon_code.no_expiry == 1:
		limit_expiry = saas_settings.ltd_expiry
	else:
		limit_expiry = add_days(today(), int(coupon_code.expiry)) if coupon_code and coupon_code.expiry > 0 else add_days(today(), int(saas_settings.default_expiry))

	return limit_users,limit_emails, limit_space, limit_email_group,limit_expiry,discounted_users,customer

@frappe.whitelist(allow_guest=True)
def get_status(account_request):
	if frappe.db.exists("Saas User", account_request):
		doc = frappe.get_doc("Saas User", account_request)
	else:
		return {'status': "Wait"}
	commandStatus = frappe._dict()
	commandStatus["status"] = ""
	if(doc.key):
		try:
			if frappe.db.exists("Bench Manager Command", doc.key):
				commandStatus = frappe.get_doc("Bench Manager Command",doc.key)
			else:
				return {'status': "Wait"}
		except Exception as e:
			pass
	else:
		frappe.throw("You will get confirmation email once your site is ready.","ValidationError")

	result = {}
	if commandStatus.get("status") in ["", "Ongoing"]:
		result['status'] = "Wait"
		return result
	elif(doc.linked_saas_domain and commandStatus.status=="Success"):
		#update status of stock site from "Picked" to "Assigned"
		stock_site = frappe.get_value("Stock Sites", filters={"renamed": doc.linked_saas_site, "status": "Picked"})
		if stock_site:
			frappe.db.set_value('Stock Sites', stock_site, 'status', 'Assigned')
		create_first_user_on_target_site(doc.name)
		result['user'] = doc.email
		result['password'] = doc.password
		result['link'] = "https://"+doc.linked_saas_site
	elif commandStatus.status=="Failed":
		create_first_user_on_target_site(doc.name)
		result['status']="Failed"
	else:
		result['link'] = "https://"+doc.linked_saas_site
	return result
	
def create_first_user_on_target_site(saas_user):
	site_user =  frappe.get_doc('Saas User',saas_user)
	domain = site_user.linked_saas_site
	site_password = get_decrypted_password("Saas User", site_user.name, "password")
	is_new_user = False
	conn=""
	user=None
	retry_count = 1
	from better_saas.better_saas.doctype.saas_user.frappeclient import FrappeClient
	while(conn==""):
		try:
			conn = FrappeClient("https://"+domain, "Administrator", site_password)
		except Exception as e:
			print("Exception in connection to site:")
			print(e)
			print("Connection Object")
			print(conn)
			print(str(retry_count)+" Retry to Connect:")
			retry_count = retry_count+1
			time.sleep(2)

		if(retry_count>3):
			break			
				
	if(retry_count>3):
		return False

	try:
		user = conn.get_list("User",filters={"email":site_user.email})
		if(len(user)==0):
			user = False
	except Exception as e:
		print(e)	
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

	if(True):
		STANDARD_USERS = ("Guest", "Administrator")
		subject="Welcome to OneHash"
		email_template="OneHash CRM Welcome Email"
		# args = {
		# 		'first_name': site_user.first_name or site_user.last_name or "user",
		# 		'user': site_user.email,
		# 		'title': subject,
		# 		'login_url': "https://"+site_user.linked_saas_site,
		# 		'site_url': "https://"+site_user.linked_saas_site,
		# 		'help_url':"https://help.onehash.ai",
		# 		'user_fullname': site_user.first_name+" "+site_user.last_name
		# 	}
		sender = frappe.session.user not in STANDARD_USERS and get_formatted_email(frappe.session.user) or None
		sender = None
		
		data = site_user.as_dict()
		email_template = frappe.get_doc("Email Template", email_template,ignore_permissions=True)
		message = frappe.render_template(email_template.response_html if email_template.use_html else email_template.response, data)
		frappe.sendmail(site_user.email,sender=sender, subject=email_template.subject, message=message,delayed=False)

		# frappe.sendmail(recipients=site_user.email, sender=sender, subject=subject,
		# 		template=template, args=args, header=[subject, "green"],
		# 		delayed=False)
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

def get_bench_path(saas_site):
	bench = frappe.get_value("Saas Site",saas_site,'bench')
	return frappe.get_value("OneHash Bench",bench,'bench_path')

@frappe.whitelist()
def delete_site(site_name):
	try:			
		saas_settings = frappe.get_doc("Saas Settings")
		mysql_password = saas_settings.mysql_root_password
		site = frappe.get_doc("Saas User", {"linked_saas_site": site_name})
		site.delete()
		domain = frappe.get_doc("Saas Domains", site.linked_saas_domain)
		domain.delete()
		saas_site = frappe.get_doc("Saas Site", site.linked_saas_site)
		bench_path = get_bench_path(site_name)
		subs = frappe.get_list("Subscription", filters={"reference_site": site_name})
		if subs:
			for sub in subs:
				sub = frappe.get_doc("Subscription", sub.get("name"))
				sub.reference_site = ""
				sub.save(ignore_permissions=True)
		integ_req = frappe.get_list("Integration Request", {"reference_docname": site_name})
		if integ_req:
			for req in integ_req:
				req_doc = frappe.get_doc("Integration Request", req.name)
				req_doc.reference_docname = ""
				req_doc.save(ignore_permissions=True)
		finrich_list = frappe.get_list("FinRich Archive", filters={"reference_site": site.name})
		if finrich_list:
			for fin in finrich_list:
				fin = frappe.get_doc("FinRich Archive", fin)
				fin.reference_site = ""
				fin.save()
		if frappe.db.exists("Saas Domains", {"domain": site_name}):
			frappe.get_doc("Saas Domains", {"domain": site_name}).delete()
		saas_site.delete(ignore_permissions=True)
		user = frappe.get_doc("User", site.email)
		user.delete()
		site_deletion_config = frappe.get_doc("Site Deletion Configuration", "Site Deletion Configuration")
		if site_deletion_config:
			template = site_deletion_config.deletion_warning_template
		if template:
			email_template = frappe.db.get_value("Email Template", {"name": template})
			if email_template:
				data = user.as_dict()
				email_template = frappe.get_doc("Email Template", email_template)
				message = frappe.render_template(email_template.response_html if email_template.use_html else email_template.response, data)
				frappe.sendmail(user.email, subject=email_template.subject, message=message)

		commands = ["bench drop-site {site_name} --root-password {mysql_password}".format(site_name=site_name, mysql_password=mysql_password)]
		commands.append("bench setup nginx --yes")
		commands.append("bench setup reload-nginx")
		frappe.enqueue('bench_manager.bench_manager.utils.run_command',
			commands=commands,
			doctype="Bench Settings",
			key=today() + " " + nowtime(),
			now = True,
			cwd = bench_path
		)
	except:
		frappe.log_error(frappe.get_traceback())

@frappe.whitelist()
def disable_enable_site(site_name, status):
	bench_path = get_bench_path(site_name)
	if status == "Active":
		commands = ["bench --site {site_name} set-maintenance-mode on".format(site_name=site_name)]
	else:
		commands = ["bench --site {site_name} set-maintenance-mode off".format(site_name=site_name)]

	frappe.enqueue('bench_manager.bench_manager.utils.run_command',
		commands=commands,
		doctype="Bench Settings",
		key=today() + " " + nowtime(),
		now = True,
		cwd = bench_path
	)

@frappe.whitelist(allow_guest=True)
def check_subdomain_avai(subdomain):	
	if(not bool(re.match('^[a-zA-Z0-9]+$',subdomain))):		
		frappe.throw("Sub-domain can only contain letters and numbers","ValidationError")		

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
	bench_path = get_bench_path(site_name)
	commands = ["bench --site {site_name} set-limits --limit users {limit_users} --limit emails {limit_emails} --limit space {limit_space} --limit email_group {limit_email_group} --limit expiry {limit_expiry}".format(
		site_name = site_name,
		limit_users = limit_for_users,
		limit_emails = limit_for_emails,
		limit_space = limit_for_space,
		limit_email_group = limit_for_email_group,
		limit_expiry = expiry
	)]
	mute_email_flag = 1 if (not (expiry and str(expiry)>=today())) else 0
	commands.append("bench --site {site_name} set-config mute_emails {mute_emails}".format(site_name=site_name,mute_emails=mute_email_flag)) 
	frappe.enqueue('bench_manager.bench_manager.utils.run_command',
		commands=commands,
		doctype="Bench Settings",
		key=today() + " " + nowtime(),
		now = True,
		cwd = bench_path
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
	total_users = conn.get_list('User', fields = ['name', 'first_name', 'last_name', 'enabled', 'last_active','user_type'],limit_page_length=10000)
	active_users = conn.get_list('User', fields = ['name', 'first_name', 'last_name','last_active','user_type'], filters = {'enabled':'1'},limit_page_length=10000)
	return {"total_users":total_users, "active_users":active_users}

@frappe.whitelist(allow_guest=True)
def check_password_strength(passphrase,first_name,last_name,email):
	user_data = (first_name, "", last_name, email, "")
	if("'" in passphrase or '"' in passphrase):
		return {"feedback":{"password_policy_validation_passed":False,"suggestions":["Password should not contain ' or \""]}}
	return test_password_strength(passphrase,user_data=user_data)

@frappe.whitelist(allow_guest=True)
def signup(subdomain,first_name,last_name,phone_number,email,passphrase,company_name=None,country=None,promocode=None,utm_source=None,utm_campaign=None,utm_medium=None,utm_content=None,utm_term=None,plan=None,product=None):
	phone_number = re.sub(r"[^0-9]","",phone_number)
	subdomain = re.sub(r"[^a-zA-Z0-9]","",subdomain)
	geo_country = get_geo_ip_country(frappe.local.request_ip) if frappe.local.request_ip else None
	country = country if country else (geo_country['names']['en'] if geo_country else None)
	password_test_result = check_password_strength(passphrase,first_name,last_name,email)
	if(not password_test_result['feedback']['password_policy_validation_passed']):
		frappe.throw(password_test_result['feedback']['warning']+"\r\n"+password_test_result['feedback']['suggestions'][0],"ValidationError")
	
	existing_saas_user = frappe.get_list('Saas User', filters={'email': email, 'linked_saas_site': ''})
	if len(existing_saas_user)>0:
		saas_user = frappe.get_doc("Saas User",existing_saas_user[0]['name'])
		saas_user.email = email
		saas_user.mobile = phone_number
		saas_user.first_name = first_name
		saas_user.last_name = last_name
		saas_user.subdomain = subdomain.lower()
		saas_user.password = passphrase
		saas_user.confirm_password = passphrase
		saas_user.promocode = promocode
		saas_user.company_name = company_name
		saas_user.country = country
		saas_user.otp = generate_otp()
		saas_user.flags.ignore_permissions=True
		saas_user.product = product
		result = saas_user.save()
		lead = create_lead(result)
	else:
		sass_user = frappe.get_doc({
				"doctype":"Saas User",
				"email": email,
				"mobile": phone_number,
				"first_name": first_name,
				"last_name": last_name,
				"subdomain": subdomain.lower(),
				"confirm_password":passphrase,
				"password":passphrase,
				"promocode":promocode,
				"otp": generate_otp(),
				"utm_source":utm_source,
				"utm_medium":utm_medium,
				"utm_content":utm_content,
				"utm_term":utm_term,
				"country":country,
				"company_name":company_name,
				"utm_campaign":utm_campaign,
				"product":product
			})
		#sass_user.flags.ignore_permissions = True
		result = sass_user.insert(ignore_permissions=True)
		lead = create_lead(result)

	doc = frappe.get_doc("Saas User",result.name)
	doc.otp = generate_otp()
	doc.save()
	send_otp_sms(doc.mobile,doc.otp)
	send_otp_email(doc)
	final_result = {}
	# final_result["location"] = "verify"
	final_result["reference"] = result.name
	final_result['email'] = email
	final_result['mobile'] = phone_number
	return final_result

def create_lead(saas_user):
	#frappe.set_user("Administrator")
	existing_lead = frappe.get_value("Lead",filters={"email_id":saas_user.email})
	if(saas_user.promocode):
		customer = frappe.get_value("Coupon Code",{"coupon_code":saas_user.promocode},"customer")
		if customer and not existing_lead:
			existing_lead = frappe.get_value("Customer",customer,"lead_name")
			
	if(existing_lead):
		lead_doc = frappe.get_doc("Lead",existing_lead,ignore_permissions=True)
		if(lead_doc.contact_date and lead_doc.contact_date.strftime("%Y-%m-%d %H:%M:%S.%f") < frappe.utils.now()):
			lead_doc.contact_date = ""

		lead_doc.email_id = saas_user.email
		lead_doc.mobile_no = saas_user.mobile
		lead_doc.primary_mobile = saas_user.mobile
		lead_doc.promocode = saas_user.promocode
		lead_doc.industry_type = saas_user.industry_type
		lead_doc.product = saas_user.product
		lead_doc.company_name = saas_user.company_name
		lead_doc.expected_users = saas_user.expected_users
		lead_doc.flags.ignore_permissions = True
		lead_doc.save(ignore_permissions=True)
		
	else:
		lead = frappe.get_doc({
				"doctype":"Lead",
				"email_id": saas_user.email,
				"mobile_no": saas_user.mobile,
				"primary_mobile": saas_user.mobile,
				"promocode": saas_user.promocode,
				"lead_stage": "Lead",
				"utm_source":saas_user.utm_source,
				"utm_campaign":saas_user.utm_campaign,
				"utm_medium":saas_user.utm_medium,
				"utm_term":saas_user.utm_term,
				"utm_content":saas_user.utm_content,
				"product":saas_user.product
			})
		lead.lead_name = saas_user.first_name+" "+saas_user.last_name
		lead.source = "Walk In"
		return lead.save(ignore_permissions=True)	


@frappe.whitelist(allow_guest=True)
def resend_otp(id):
	doc = frappe.get_doc("Saas User",id)
	if frappe.utils.time_diff_in_seconds(frappe.utils.now(),doc.modified.strftime("%Y-%m-%d %H:%M:%S.%f"))>600:
		doc.otp = generate_otp()
		doc.save()
	send_otp_sms(doc.mobile,doc.otp)
	send_otp_email(doc)
	# frappe.msgprint("Verification code has been sent to registered email id and mobile.")

@frappe.whitelist(allow_guest=True)
def verify_account_request(id,otp):
	doc = frappe.get_doc("Saas User",id)
	# if(doc.otp!=otp):
		# frappe.throw("Please enter valid OTP","ValidationError")

	if frappe.utils.time_diff_in_seconds(frappe.utils.now(),doc.modified.strftime("%Y-%m-%d %H:%M:%S.%f"))>600:
		return 'OTP Expired'
	elif doc.otp != otp:
		return 'Invalid OTP'
	else:
		return 'OTP Verified'

@frappe.whitelist(allow_guest=True)
def update_account_request(id,country=None,industry_type=None,currency=None,language=None,timezone=None,domain=None):
	doc = frappe.get_doc("Saas User",id)
	try:
		doc.country = country
		doc.industry_type = industry_type
		doc.currency = currency
		doc.language  = language
		doc.timezone = timezone
		doc.save()
	except Exception as e:
		print("Exception While Updating Data slide 3")
		print(e)

	result = {}	
	if(industry_type):
		result['location'] = "#other-details"
	return result

@frappe.whitelist(allow_guest=True)
def update_other_details_request(id,company=None,users=None,designation=None,referral_source=None):
	doc = frappe.get_doc("Saas User",id)
	try:
		doc.company_name = company
		doc.expected_users = users
		doc.designation = designation
		doc.referral_source  = referral_source
		doc.save()
	except Exception as e:
		print("Exception While Updating Data slide 4")
		print(e)
		
	result = {}
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
	if not number:
		return
	receiver_list = []
	receiver_list.append(number)
	message = otp+" is OTP to verify your account request for OneHash."
	send_sms(receiver_list,message, sender_name = '', success_msg = False)

def send_otp_email(site_user):
	STANDARD_USERS = ("Guest", "Administrator")
	subject="Please confirm this email address for OneHash"
	email_template="Signup OTP verification"
	args = {
			'first_name': site_user.first_name or site_user.last_name or "user",
			'last_name': site_user.last_name,
			'title': subject,
			'otp':site_user.otp
			}
	sender = None
	data = site_user.as_dict()
	email_template = frappe.get_doc("Email Template", email_template,ignore_permissions=True)
	message = frappe.render_template(email_template.response_html if email_template.use_html else email_template.response, data)
	frappe.sendmail(site_user.email,sender=sender, subject=email_template.subject,bcc=["anand@onehash.ai"], message=message,delayed=False)

	# frappe.sendmail(recipients=site_user.email, sender=sender, subject=subject, bcc=["anand@onehash.ai"],
	# 		template=template, args=args, header=[subject, "green"],
	# 		delayed=False)
	return True

@frappe.whitelist(allow_guest=True)
def apply_promocode(promocode, site_name):
	# return True
	saas_user = frappe.get_list("Saas User",filters={"linked_saas_site":site_name},ignore_permissions=True)
	if(len(saas_user)==0):
		frappe.throw("Invalid Request")
		return
	saas_site = frappe.get_doc("Saas Site",site_name,ignore_permissions=True)
	is_new_user = False if saas_site.customer else True
	validResult = is_valid_promocode(promocode,is_new_user)
	if(not validResult[0]):
		frappe.throw(_("Please enter a valid code."))
	
	coupon_name = frappe.get_list("Coupon Code", filters={'coupon_code': promocode}, ignore_permissions=True)[0].name
	coupon_code  = frappe.get_doc("Coupon Code", coupon_name, ignore_permissions=True)
	
	saas_user_doc = frappe.get_doc("Saas User",saas_user[0].name)
	is_no_expiry = coupon_code.no_expiry
	expiry_days = coupon_code.expiry
	is_unlimited_users = coupon_code.unlimited_users
	# Calcualte new limits
	base_plan = coupon_code.base_plan if saas_user_doc.country=="India" else coupon_code.base_plan_international
	if(coupon_code.is_stackable and (saas_site.subscription or saas_site.discounted_users>0)):
		stack_count = frappe.db.count("Coupon Code", {"status": "Redeemed","linked_saas_site":site_name,"deal_code":coupon_code.deal_code})
		if stack_count>=coupon_code.max_stack_limit:
			throw(_("Maximum stack limit "+str(coupon_code.max_stack_limit)+" reached."))
			return False
		coupon_limit_for_users = coupon_code.stack_limits[stack_count].limit_for_users
		coupon_discounted_users = coupon_code.stack_limits[stack_count].discounted_users
		# coupon_max_discounted_user_limit = coupon_code.stack_limits[stack_count].max_discounted_user_limit
		limit_users =  saas_site.limit_for_users + coupon_limit_for_users if coupon_limit_for_users else saas_site.limit_for_users
		discounted_users =  saas_site.discounted_users + coupon_discounted_users if coupon_discounted_users else saas_site.discounted_users
		
		coupon_limit_for_emails = coupon_code.stack_limits[stack_count].limit_for_emails
		coupon_limit_for_space = coupon_code.stack_limits[stack_count].limit_for_space
		coupon_limit_for_email_group = coupon_code.stack_limits[stack_count].limit_for_email_group
		is_no_expiry = coupon_code.stack_limits[stack_count].no_expiry
		expiry_days = coupon_code.stack_limits[stack_count].expiry
		is_unlimited_users = coupon_code.stack_limits[stack_count].unlimited_users
	
		# if coupon_max_discounted_user_limit and discounted_users > coupon_max_discounted_user_limit:
		# 	throw(_("Maximum allowed stack user limit is "+str(coupon_max_discounted_user_limit)))
		# 	return False

		limit_emails =  saas_site.limit_for_emails + int(coupon_limit_for_emails) if int(coupon_limit_for_emails) else saas_site.limit_for_emails
		limit_space =  saas_site.limit_for_space + int(coupon_limit_for_space) if int(coupon_limit_for_space) else saas_site.limit_for_space
		limit_email_group =  saas_site.limit_for_email_group + int(coupon_limit_for_email_group) if int(coupon_limit_for_email_group) else saas_site.limit_for_email_group
	else:
		discounted_users = coupon_code.discounted_users if coupon_code.discounted_users else saas_site.discounted_users
		limit_emails = int(coupon_code.limit_for_emails) if int(coupon_code.limit_for_emails) else saas_site.limit_for_emails
		limit_space = int(coupon_code.limit_for_space) if int(coupon_code.limit_for_space) else saas_site.limit_for_space
		limit_email_group = int(coupon_code.limit_for_email_group) if int(coupon_code.limit_for_email_group) else saas_site.limit_for_email_group
		limit_users =  0 if is_unlimited_users else (int(coupon_code.limit_for_users) if coupon_code.limit_for_users else saas_site.limit_for_users) ## Applying Users count from promocode
		
	## Check for Life-Time Deals (i.e. for 100 years)
	if is_no_expiry:
		saas_settings = frappe.get_doc("Saas Settings")
		limit_expiry = saas_settings.ltd_expiry
	else:
		limit_expiry = add_days(today(), int(expiry_days)) if expiry_days > 0 else saas_site.expiry
	
	saas_site.customer = coupon_code.customer if coupon_code.customer and not saas_site.customer else saas_site.customer

	saas_site.limit_for_users = limit_users
	saas_site.limit_for_emails = limit_emails
	saas_site.limit_for_space = limit_space
	saas_site.limit_for_email_group = limit_email_group
	saas_site.expiry = limit_expiry
	saas_site.discounted_users = discounted_users
	saas_site.base_plan = base_plan if base_plan else saas_site.base_plan
	saas_site.save(ignore_permissions=True)
	
	apply_new_limits(limit_users,limit_emails,limit_space,limit_email_group,limit_expiry,site_name)

	## Promocode Consumed
	try:
		coupon_code.used = int(coupon_code.used)+1
		coupon_code.linked_saas_site = saas_site.name
		coupon_code.status = "Redeemed"
		coupon_code.save(ignore_permissions=True)
	except Exception as e:
		frappe.log_error(frappe.get_traceback(),"Coupon Code exception")

	
	if saas_site.subscription:
		# Cancel Subscription coupon is lifetime and for unlimited users
		if((is_unlimited_users or (int(saas_site.limit_for_users)-int(saas_site.discounted_users)<=0)) and is_no_expiry):
			from better_saas.www.upgrade import cancel
			cancel(saas_site.name)

	update_promocode_on_reference_docs(saas_user[0].name,promocode)
	success_message = coupon_code.success_message if coupon_code.success_message else _("Promocode has been Applied Successfully.")
	frappe.db.commit()
	return {"success":True,"message":success_message}

def update_promocode_on_reference_docs(saas_user,promocode):
	saas_user = frappe.get_doc("Saas User",saas_user)
	saas_user.promocode = promocode if not saas_user.promocode else saas_user.promocode+","+promocode
	saas_user.save(ignore_permissions=True)

	lead = frappe.get_list("Lead",filters={"email_id":saas_user.email},ignore_permissions=True)
	if(len(lead)>0):
		lead_doc = frappe.get_doc("Lead",lead[0].name,ignore_permissions=True)
		lead_doc.promocode = saas_user.promocode
		lead_doc.save(ignore_permissions=True)


def validate_coupon_code(coupon_name):
	is_valid=True
	error_message=""
	coupon = frappe.get_doc("Coupon Code", coupon_name)
	if coupon.valid_from and coupon.valid_from > getdate(today()):
		is_valid = False
		error_message = _("Sorry, this coupon code's validity has not started")
	elif coupon.valid_upto and coupon.valid_upto < getdate(today()):
		is_valid = False
		error_message = _("Sorry, this coupon code's validity has expired")
	elif coupon.used >= coupon.maximum_use:
		is_valid = False
		error_message = _("Sorry, this coupon code is no longer valid")
	return is_valid,error_message

@frappe.whitelist(allow_guest=True)
def is_valid_promocode(promocode,is_new_user=False):
	filters = {'is_signup_scheme':1, 'coupon_code': promocode }
	if not is_new_user:
		filters["for_new_users"]=0

	code = frappe.get_list("Coupon Code", filters=filters, ignore_permissions=True)
	if(len(code)==0):
		return False,_("Please Enter a valid code")
    # # Check for Promocode Validation
	return validate_coupon_code(code[0].name)


@frappe.whitelist(allow_guest=True)
def refund_promocode(promocode):
	# return True
	coupon_name = frappe.get_list("Coupon Code", filters={'coupon_code': promocode}, ignore_permissions=True)[0].name
	coupon_code  = frappe.get_doc("Coupon Code", coupon_name, ignore_permissions=True)
	
	if(not coupon_code):
		return {"success":False,"message":_("Invalid Promocode")}
	if(coupon_code.status=="Available" or coupon_code.status=="Sold"):
		coupon_code.status="Refunded"
		coupon_code.save(ignore_permissions=True)
		success_message =  _("Promocode has been Refunded Successfully.")
		frappe.db.commit()
		return {"success":True,"message":success_message}
	elif coupon_code.status=="Refunded":
		success_message =  _("Promocode Already Refunded.")
		return {"success":False,"message":success_message}
	else:
		site_name = coupon_code.linked_saas_site
		saas_user = frappe.get_list("Saas User",filters={"linked_saas_site":site_name},ignore_permissions=True)
		if(len(saas_user)==0):
			frappe.throw("Invalid Request")
			return
		saas_site = frappe.get_doc("Saas Site",site_name,ignore_permissions=True)
		is_new_user = False if saas_site.customer else True
		
		saas_user_doc = frappe.get_doc("Saas User",saas_user[0].name)
		saas_settings = frappe.get_doc("Saas Settings")
		# Calcualte new limits
		base_plan = coupon_code.base_plan if saas_user_doc.country=="India" else coupon_code.base_plan_international
		is_no_expiry = coupon_code.no_expiry
		expiry_days = coupon_code.expiry
		is_unlimited_users = coupon_code.unlimited_users
		stack_count=0
		if(coupon_code.is_stackable):
			stack_count = frappe.db.count("Coupon Code", {"status": "Redeemed","linked_saas_site":site_name,"deal_code":coupon_code.deal_code})
			stack_limits = coupon_code.stack_limits[stack_count-1]
			coupon_limit_for_users = stack_limits.limit_for_users
			coupon_discounted_users = stack_limits.discounted_users
			# coupon_max_discounted_user_limit = coupon_code.stack_limits[stack_count].max_discounted_user_limit
			limit_users =  saas_site.limit_for_users - coupon_limit_for_users if saas_site.limit_for_users - coupon_limit_for_users>0 else saas_settings.default_limit_for_users  if coupon_limit_for_users else saas_site.limit_for_users
			discounted_users =  saas_site.discounted_users - coupon_discounted_users if coupon_discounted_users else saas_site.discounted_users
			coupon_limit_for_emails = stack_limits.limit_for_emails
			coupon_limit_for_space = stack_limits.limit_for_space
			coupon_limit_for_email_group = stack_limits.limit_for_email_group
			is_no_expiry = stack_limits.no_expiry
			expiry_days = stack_limits.expiry
			is_unlimited_users = stack_limits.unlimited_users

			limit_emails =  saas_site.limit_for_emails - int(coupon_limit_for_emails) if int(coupon_limit_for_emails) else saas_site.limit_for_emails
			limit_space =  saas_site.limit_for_space - int(coupon_limit_for_space) if int(coupon_limit_for_space) else saas_site.limit_for_space
			limit_email_group =  saas_site.limit_for_email_group - int(coupon_limit_for_email_group) if int(coupon_limit_for_email_group) else saas_site.limit_for_email_group
			# limit_expiry = add_days(today(), int(expiry_days)) if expiry_days > 0 else saas_site.expiry
		else:
			discounted_users = 0 if coupon_code.discounted_users else saas_site.discounted_users
			limit_emails = saas_settings.default_limit_for_emails if int(coupon_code.limit_for_emails) else saas_site.limit_for_emails
			limit_space = saas_settings.default_limit_for_space if int(coupon_code.limit_for_space) else saas_site.limit_for_space
			limit_email_group = saas_settings.default_limit_for_email_group if int(coupon_code.limit_for_email_group) else saas_site.limit_for_email_group
			limit_users =  saas_settings.default_limit_for_users if coupon_code.unlimited_users else saas_settings.default_limit_for_users if coupon_code.limit_for_users else saas_site.limit_for_users ## Applying Users count from promocode
			# limit_expiry = add_days(saas_site.expiry, -1*int(coupon_code.expiry)) if coupon_code.expiry > 0 else saas_site.expiry
			
		## Check for Life-Time Deals (i.e. for 100 years)
		if is_no_expiry:
			limit_expiry = saas_settings.ltd_expiry if stack_count>1 else today()
		else:
			limit_expiry = add_days(saas_site.expiry, -1*int(expiry_days)) if expiry_days > 0 else saas_site.expiry
		
		saas_site.limit_for_users = limit_users
		saas_site.limit_for_emails = limit_emails
		saas_site.limit_for_space = limit_space
		saas_site.limit_for_email_group = limit_email_group
		saas_site.expiry = limit_expiry
		saas_site.discounted_users = discounted_users
		saas_site.base_plan = base_plan if base_plan else saas_site.base_plan
		saas_site.save(ignore_permissions=True)
		
		apply_new_limits(limit_users,limit_emails,limit_space,limit_email_group,limit_expiry,site_name)

		## Promocode Consumed
		try:
			#coupon_code.used = int(coupon_code.used)+1
			coupon_code.linked_saas_site = saas_site.name
			coupon_code.status = "Refunded"
			coupon_code.save(ignore_permissions=True)
		except Exception as e:
			frappe.log_error(frappe.get_traceback(),"Coupon Code exception")

		#update_promocode_on_reference_docs(saas_user[0].name,promocode)
		success_message =  _("Promocode has been Refunded Successfully.")
		frappe.db.commit()
		return {"success":True,"message":success_message}


@frappe.whitelist(allow_guest=True)
def get_promocode_benefits(site_name):
	saas_user = frappe.get_doc("Saas User",{"linked_saas_site":site_name},ignore_permissions=True)
	if(saas_user.promocode):
		promocode = saas_user.promocode.split(",")
		coupon_codes = frappe.get_list("Coupon Code",filters=[["coupon_code","in",promocode],["status","!=","Refunded"]], fields=["name","coupon_code","status","success_message","no_expiry","sales_partner"], ignore_permissions=True)	
	else:
		coupon_codes = []
	return coupon_codes