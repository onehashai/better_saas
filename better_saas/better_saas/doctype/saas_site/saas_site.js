// Copyright (c) 2020, Vigneshwaran Arumainayagam and contributors
// For license information, please see license.txt

frappe.ui.form.on('Saas Site', {
	apply_new_limits: function(frm) {
		if (frm.doc.__unsaved) {
			frappe.throw("Please Save and then Try Again")
		}
		else{
			frappe.call({
				"method": "better_saas.better_saas.doctype.saas_user.saas_user.apply_new_limits",
				args: {
					"limit_for_users" : frm.doc.limit_for_users,
					"limit_for_emails" : frm.doc.limit_for_emails,
					"limit_for_space" : frm.doc.limit_for_space,
					"limit_for_email_group" : frm.doc.limit_for_email_group,
					"expiry" : frm.doc.expiry,
					"site_name" : frm.doc.site_name	
				},
				callback: function (r) {
					frappe.msgprint("Request Queued.. Please Wait...")
				}
			})
		}
	},
	refresh: function (frm) {
		frm.get_field("user_details").grid.cannot_add_rows = true;
		frm.refresh_field("user_details");
		if (!frm.doc.__islocal) {
			frm.add_custom_button(__('Refresh User Count'), function(){
				frappe.call({
					"method": "better_saas.better_saas.doctype.saas_user.saas_user.get_users_list",
					args: {
						"site_name" : frm.doc.name
					},
					async: false,
					callback: function (r) {
						frm.set_value("number_of_users", r.message.total_users.length);
						frm.set_value("number_of_active_users", r.message.active_users.length);
						frm.clear_table("user_details");
						for (let i = 0; i < r.message.total_users.length; i++) {
							const element = r.message.total_users[i];
							let row = frappe.model.add_child(frm.doc, "User Details", "user_details");
							row.emai_id = element.name;
							row.first_name = element.first_name;
							row.last_name = element.last_name;
							row.active = element.enabled;
						}
						frm.refresh_fields("user_details");
						frappe.show_alert({
							message: "User Count Refreshed !!",
							indicator: 'green'
						});
						frm.save();
					}
				})
			});	
			frm.add_custom_button(__('Delete Site'), function(){
				frappe.confirm(__("This action will delete this saas-site permanently. It cannot be undone. Are you sure ?"), function() {
					frappe.call({
						"method": "better_saas.better_saas.doctype.saas_user.saas_user.delete_site",
						args: {
							"site_name" : frm.doc.name
						},
						async: false,
						callback: function (r) {
							frappe.set_route("List", "Saas Site");
							frappe.msgprint("Site Deletion Queued Sucessfully !!!");
						}
					});
				}, function(){
					frappe.show_alert({
						message: "Cancelled !!",
						indicator: 'red'
					});
				});
				
			});

			if (frm.doc.site_status == "Active") {
				frm.add_custom_button(__('Disable Site'), function(){
					frappe.confirm(__("This action will disable the site. It can be undone. Are you sure ?"), function() {
						frappe.call({
							"method": "better_saas.better_saas.doctype.saas_user.saas_user.disable_enable_site",
							args: {
								"site_name" : frm.doc.name,
								"status": frm.doc.site_status
							},
							async: false,
							callback: function (r) {
								frm.set_value("site_status", "In-Active");
								frm.save();
								frappe.msgprint("Site Disabled Sucessfully !!!");
							}
						});
					}, function(){
						frappe.show_alert({
							message: "Cancelled !!",
							indicator: 'red'
						});
					});
				});
			} 
			else if (frm.doc.site_status == "In-Active"){
				frm.add_custom_button(__('Enable Site'), function(){
					frappe.confirm(__("This action will enable the site. It can be undone. Are you sure ?"), function() {
						frappe.call({
							"method": "better_saas.better_saas.doctype.saas_user.saas_user.disable_enable_site",
							args: {
								"site_name" : frm.doc.name,
								"status": frm.doc.site_status
							},
							async: false,
							callback: function (r) {
								frm.set_value("site_status", "Active");
								frm.save();
								frappe.msgprint("Site Enabled Sucessfully !!!");
							}
						});
					}, function(){
						frappe.show_alert({
							message: "Cancelled !!",
							indicator: 'red'
						});
					});
				});
			}
		}

	}
});
