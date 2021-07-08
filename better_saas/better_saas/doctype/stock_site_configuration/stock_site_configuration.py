# -*- coding: utf-8 -*-
# Copyright (c) 2021, Vigneshwaran Arumainayagam and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.utils import nowdate, nowtime
from frappe.model.document import Document

class StockSiteConfiguration(Document):
	pass

def check_stock_sites():
	stock_site_config = frappe.get_doc("Stock Site Configuration", "Stock Site Configuration")
	if not stock_site_config.enabled:
		return
	if not stock_site_config.run_at_interval:
		return
	curtime = nowtime()
	if curtime[:2] == "00":
		curtime = "24" + curtime[2:]

	if int(curtime[:2]) % int(stock_site_config.run_at_interval) != 0:
		return

	check_sites()

def check_sites():
	stock_site_config = frappe.get_doc("Stock Site Configuration", "Stock Site Configuration")
	stock_sites = frappe.get_list("Stock Sites", filters={"status": "Available"})
	if len(stock_sites) <= int(stock_site_config.threshold_number_of_sites):
		create_sites(int(stock_site_config.number_of_sites)-int(len(stock_sites)))
	else:
		return

def create_sites(number):
	if number and number > 0:
		for n in range(number):
			frappe.enqueue(create_stock_sites, queue='default', timeout=None, event=None, is_async=True, 
                                job_name=None, now=False, enqueue_after_commit=False)

def create_stock_sites():
	try:
		doc = frappe.get_doc({
			"doctype": "Stock Sites"
		}).insert()

		saas_settings = frappe.get_doc("Saas Settings")
		mysql_password = saas_settings.mysql_root_password

		site_name = doc.name

		admin_password = frappe.generate_hash(length=15)
		doc.admin_password = admin_password
		commands = ["bench new-site --mariadb-root-password {mysql_password} --admin-password {admin_password} {site_name}".format(site_name=site_name,
		admin_password=admin_password, mysql_password=mysql_password)]

		# creation of site and install erpnext
		if saas_settings.install_erpnext:
			install_erpnext = "true"
			commands.append("bench --site {site_name} install-app erpnext journeys".format(site_name=site_name))
		else:
			install_erpnext = "false"
		
		# setup nginx config and reloading the nginx service
		commands.append("bench setup nginx --yes")
		commands.append("bench setup reload-nginx")
		
		command_key = nowdate() + " " + nowtime()
		frappe.enqueue('bench_manager.bench_manager.utils.run_command',
			commands=commands,
			doctype="Bench Settings",
			key=command_key
		)
		doc.status = "Available"
		doc.save()
	except:
		frappe.log_error(frappe.get_traceback())