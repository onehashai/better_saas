# -*- coding: utf-8 -*-
# Copyright (c) 2021, Vigneshwaran Arumainayagam and Contributors
# See license.txt
#from __future__ import unicode_literals

# import frappe
#import unittest

#class TestFacebookIntegration(unittest.TestCase):
#	pass



# -*- coding: utf-8 -*-
# Copyright (c) 2021, Vigneshwaran Arumainayagam and Contributors
# See license.txt
from __future__ import unicode_literals
from . import facebook_integration
import unittest
from unittest.mock import patch
import requests
# import frappe


class TestFacebookIntegration(unittest.TestCase):
	@patch('facebook_integration.requests')
	def test_save_subscription(patched_requests):
		data = {
			"verify_token": "dsb8943ysdbfd89w3enjd90",
			"page_id": "page1",
			"page_access_token": "token1",
			"domain": "domain1",
			"user_id": "id1",
			"user_access_token": "token2"
		}
		r = requests.Response()
		r.text = {
			"access_token": "token3",
			"data": [
				{
				"access_token": "token4"
				}
			]
			}
		patched_requests.get.return_value = r
		save_subscription(verify_token="dsb8943ysdbfd89w3enjd90", page_id="page1",
				page_access_token= "token1",domain= "domain1",user_id= "id1",
				user_access_token="token2")
