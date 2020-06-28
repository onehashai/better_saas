from __future__ import unicode_literals
from frappe import _

def get_data():
	return [
		{
			"label": _("Saas Management"),
			"items": [
				{
					"type": "doctype",
					"name": "Saas User"
				},
				{
					"name": "Saas Settings",
					"type": "doctype",
					"label": _("Saas Settings"),
					"description": _("Saas Settings")
				},
				{
					"name": "Saas Domains",
					"type": "doctype",
					"label": _("Saas Domains"),
					"description": _("Saas Domains")
				},
				{
					"name": "Saas Site",
					"type": "doctype",
					"label": _("Saas Site"),
					"description": _("Saas Site")
				}
			]
		}
	]