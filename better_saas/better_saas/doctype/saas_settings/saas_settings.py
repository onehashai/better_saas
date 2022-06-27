# -*- coding: utf-8 -*-
# Copyright (c) 2020, Vigneshwaran Arumainayagam and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.utils import today, nowtime

class SaasSettings(Document):
	def on_update(self):
		commands =[]
		if self.grace_period:
			commands.append("bench set-config -g grace_period {0}".format(self.grace_period))
		if self.instafinancial_key:
			commands.append("bench set-config -g insta_financial_api_key {0}".format(self.instafinancial_key))
		frappe.enqueue('bench_manager.bench_manager.utils.run_command',
			commands=commands,
			doctype="Bench Settings",
			key=today() + " " + nowtime(),
			now = True)
		pass
