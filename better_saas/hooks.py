# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from . import __version__ as app_version

app_name = "better_saas"
app_title = "Better Saas"
app_publisher = "Vigneshwaran Arumainayagam"
app_description = "App for Deploying a Saas based version of Frappe or ERPNEXT Site."
app_icon = "fa fa-mixcloud"
app_color = "grey"
app_email = "vignesh.this@gmail.com"
app_license = "MIT"

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/better_saas/css/better_saas.css"
# app_include_js = "/assets/better_saas/js/better_saas.js"

# include js, css files in header of web template
# web_include_css = "/assets/better_saas/css/better_saas.css"
# web_include_js = "/assets/better_saas/js/better_saas.js"

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
#	"Role": "home_page"
# }

# Website user home page (by function)
# get_website_user_home_page = "better_saas.utils.get_home_page"

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Installation
# ------------

# before_install = "better_saas.install.before_install"
# after_install = "better_saas.install.after_install"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "better_saas.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
#	}
# }

# Scheduled Tasks
# ---------------

scheduler_events = {
# 	"all": [
# 		"better_saas.tasks.all"
# 	],
 	"daily": [
 		"better_saas.better_saas.doctype.saas_site.saas_site.update_user_to_main_app",
		"better_saas.better_saas.doctype.saas_site.saas_site.mute_emails_on_expiry"
 	],
	"hourly": [
		"better_saas.better_saas.doctype.site_deletion_configuration.site_deletion_configuration.check_deletable_sites"
	],
# 	"weekly": [
# 		"better_saas.tasks.weekly"
# 	]
# 	"monthly": [
# 		"better_saas.tasks.monthly"
# 	]
}

# Testing
# -------

# before_tests = "better_saas.install.before_tests"

# Overriding Whitelisted Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "better_saas.event.get_events"
# }

