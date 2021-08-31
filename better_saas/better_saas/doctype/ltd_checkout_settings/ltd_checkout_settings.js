// Copyright (c) 2021, Vigneshwaran Arumainayagam and contributors
// For license information, please see license.txt

frappe.ui.form.on('LTD Checkout Settings', {
	setup: function(frm) {
		frm.set_query('cost_center', function() {
			return {
				filters: {
					company: frm.doc.company
				}
			};
		});
	}
});
