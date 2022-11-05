// Copyright (c) 2020, Vigneshwaran Arumainayagam and contributors
// For license information, please see license.txt

frappe.ui.form.on('Saas User', {
	refresh: function(frm) {
		frm.add_custom_button(__('Login As Administrator'), 
			 () => {
				frappe.call('better_saas.better_saas.doctype.saas_user.saas_user.login', { name: frm.doc.name }).then((r)=>{
					if(r.message){
						window.open(`https://${frm.doc.linked_saas_site}/app?sid=${r.message}`, '_blank');
					} else{
						console.log(r);
						frappe.msgprint(__("Sorry, Could not login."));
					}
				});
			}
		);
	}
});
