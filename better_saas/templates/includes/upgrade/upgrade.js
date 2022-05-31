var site_name;
var email;
var onehash_partner;
var subscription;
var has_billing_address=false;
var base_plan="{{active_plan_name}}";
var currency="{{currency}}";
var current_cart = {{ cart }};
var cart = {{ cart }};
var addons ={};
var plans = {};
var current_subscription={};
var country_list = {{country}};
var indian_states = [
	'Andaman and Nicobar Islands',
	'Andhra Pradesh',
	'Arunachal Pradesh',
	'Assam',
	'Bihar',
	'Chandigarh',
	'Chhattisgarh',
	'Dadra and Nagar Haveli and Daman and Diu',
	'Delhi',
	'Goa',
	'Gujarat',
	'Haryana',
	'Himachal Pradesh',
	'Jammu and Kashmir',
	'Jharkhand',
	'Karnataka',
	'Kerala',
	'Ladakh',
	'Lakshadweep Islands',
	'Madhya Pradesh',
	'Maharashtra',
	'Manipur',
	'Meghalaya',
	'Mizoram',
	'Nagaland',
	'Odisha',
	'Other Territory',
	'Pondicherry',
	'Punjab',
	'Rajasthan',
	'Sikkim',
	'Tamil Nadu',
	'Telangana',
	'Tripura',
	'Uttar Pradesh',
	'Uttarakhand',
	'West Bengal'
   ];
   
var address_dialog= new frappe.ui.Dialog({
	title: 'Billing Information',
	fields: [{
		label: 'Billing Email',
		fieldname: 'email_id',
		fieldtype: 'Data',
		options:'Email',
		reqd:1
	},
	
		{
		label: 'Address Line 1',
		fieldname: 'address_line1',
		fieldtype: 'Data',
		reqd: 1
	},
	{
		label: 'Address Line 2',
		fieldname: 'address_line2',
		fieldtype: 'Data'
	},
	{
		label: 'City/Town',
		fieldname: 'city',
		fieldtype: 'Data',
		reqd: 1
	},
	{
		label: '',
		fieldname: 'col-1',
		fieldtype: 'Column Break',
		reqd: 1
	},
	
	{
		label: 'Phone (optional)',
		fieldname: 'phone',
		fieldtype: 'Data',
		options:"Phone"
	},
	{
		label: 'Country',
		fieldname: 'country',
		fieldtype: 'Autocomplete',
		options:country_list || [],
		reqd:1,
		onchange: function(){
			const country =this.get_value();
			if(country=="India"){
				address_dialog.set_df_property('state', 'hidden', 1);
				address_dialog.set_df_property('state_india', 'hidden', 0);
				address_dialog.set_df_property('state_india', 'reqd', 1);
			}else{
				address_dialog.set_df_property('state', 'hidden', 0);
				address_dialog.set_df_property('state_india', 'hidden', 1);
				address_dialog.set_df_property('state_india', 'reqd', 0);
			}
			console.log("Selected Country",country);
		}
	},
	{
		label: 'State/Province',
		fieldname: 'state_india',
		fieldtype: 'Autocomplete',
		options:indian_states,
		hidden:1
	},
	{
		label: 'State/Province',
		fieldname: 'state',
		fieldtype: 'Data',
		hidden:1
	},
	{
		label: 'Postal Code',
		fieldname: 'pincode',
		fieldtype: 'Data',
		reqd: 1
	},
	{
		label: '',
		fieldname: 'sec_break-1',
		fieldtype:'Section Break',
		depends_on:"eval: doc.country == 'India'"
	},
	{
		label: 'Are you registered for GSTIN?',
		fieldname: 'is_registered',
		fieldtype: 'Check',
		depends_on: "eval: doc.country == 'India'"
	},
	{
		label: 'GST State',
		fieldname: 'gst_state',
		fieldtype: 'Autocomplete',
		mandatory_depends_on: "eval:doc.is_registered == 1",
		depends_on: "eval: doc.is_registered == 1",
		options: indian_states
	},
	{
		label: "GSTIN",
		fieldname: "gstin",
		fieldtype: 'Data',
		mandatory_depends_on: "eval:doc.is_registered == 1",
		depends_on: "eval:doc.is_registered == 1",
	},
	{
		label: 'Address Name',
		fieldname: 'address_name',
		fieldtype: 'Data',
		read_only: 1,
		hidden: 1
	},
	{
		label: 'Address Type',
		fieldname: 'address_type',
		fieldtype: 'Data',
		read_only: 1,
		hidden: 1,
		default: "Billing",
	}
			]
});


	function add_address(site_name){
		address_dialog.set_values({"country":"India","email_id":"{{billing_email}}" });
		address_dialog.set_primary_action(__('Add Address'), function() {
				var args = address_dialog.get_values();
				if (args["country"]=="India"){
					args["state"] = args["state_india"];
					delete args["state_india"];
				}
				args["site_name"]=site_name;
				frappe.call({
					args: args,
					method: "better_saas.www.upgrade.add_address",
					callback: function (r) {
						if (r.message) {
							$("#address-wrapper").html(r.message);
							address_dialog.hide();
							frappe.msgprint("Address has been Added");
						}else{
							frappe.msgprint("Could not add the address.");
						}
					}
				});
			});
			address_dialog.show();
		}
		// address_dialog.show();



function update_address(context){
	let address_id = $(context).data("name");
	frappe.call({
		args: {name:address_id},
		method: "better_saas.www.upgrade.get_address_by_id",
		callback: function (r) {
			if (r.message) {
				if (r.message.email_id==""){
					r.message.email_id ="{{billing_email}}";
				}
				if(r.message.country=="India"){
					r.message.state_india = r.message.state;
					delete r.message.state;
				}
				address_dialog.set_values(r.message);
				address_dialog.set_primary_action(__('Update Address'), function() {
					var args = address_dialog.get_values();
					if (args["country"]=="India"){
						args["state"] = args["state_india"];
						delete args["state_india"];
					}
					args["site_name"]=site_name;
					args["name"]=address_id;
					frappe.call({
						args: args,
						method: "better_saas.www.upgrade.update_address",
						callback: function (r) {
							if (r.message) {
								$("#address-wrapper").html(r.message);
								address_dialog.hide();
								frappe.msgprint("Address has been updated");
							}else{
								frappe.msgprint("Could not update the address.");
							}
						}
					});
				});
				address_dialog.show();
			}else{
				frappe.msgprint("Could not add the address.");
			}
		}
	});
	console.log("Hurrey Update Address Called");
}

function add_balance(context){
	frappe.prompt({
		label: 'Amount',
		fieldname: 'amount',
		fieldtype: 'Currency',
		options:currency,
		reqd:1,
		non_negative:1
	}, (values) => {
		frappe.call({
			args:{"amount":values.amount,"site_name":site_name,"currency":currency},
			method: "better_saas.www.upgrade.add_balance",
			callback: function(r){
				if(r.message.redirect_to){
					window.location.href=r.message.redirect_to;
				}else{
					frappe.msgprint(r.message.message)
				}
			}
		});
	},__("Enter Amount"),__("Add Balance"));
}

function mark_address_primary(context){
	address_id = $(context).data("name");
	frappe.call({
		args: {name:address_id,site_name:site_name},
		method: "better_saas.www.upgrade.mark_address_primary",
		callback: function (r) {
			if (r.message) {
				$("#address-wrapper").html(r.message);
				frappe.msgprint("Address has been set as Default.");
			}else{
				frappe.msgprint("Could not add the address.");
			}
		}
	});
	console.log("Hurrey Mark address Called");
}

frappe.ready(function () {
	let $page = $('#page-upgrade');
	
	function reset_base_plan_selection(){
		$('a[data-type="plan"]').each((key,elem)=>{
			console.log(elem,$(elem).text())
			if($(elem).text()!="Current Plan"){
				$(elem).text("Select");
				$(elem).data("selected",0);
			}
		});
	}

	$(".plan").on("click",function(){
		let data = $(this).data();
		if(data.selected==1){
			if(data.type=="plan"){
				cart["base_plan"] = current_cart["base_plan"];
			} else {
				delete cart["add_ons"][data.name];
			}
			$(this).text("Select");
			$(this).data("selected",0);
		}else {
			if(data.type=="plan"){
				reset_base_plan_selection()
				cart["base_plan"]={"plan":data.name,"qty":1}
			}else{
				cart["add_ons"][data.name]=1
			}
			$(this).text("Selected");
			$(this).data("selected",1);
		}
		get_cart()
	});
	$(".input-number").change(function(){
		let input = $(this);
		let plan_type = input.attr("data-type");
		let fieldName = input.attr("name");
		let current_value = parseInt(input.val());
		let max_value = input.attr("max")!=undefined?input.attr("max"):0;
		let min_value = input.attr("min")!=undefined?input.attr("min"):0;
		if(max_value>0 && current_value>max_value){
			input.val(parseInt(max_value))
		}
		if(current_value<0){
			input.val(0)
		}
		if(plan_type=="base_plan"){
			cart["base_plan"]["qty"]=parseInt(input.val());	
		}else{
			cart["add_ons"][fieldName]=parseInt(input.val());
		}
		get_cart();
	});

	$('.btn-number').click(function(e){
		e.preventDefault();
		let fieldName = $(this).attr('data-field');
		let type      = $(this).attr('data-type');
		let input = $("input[name='"+fieldName+"']");
		let plan_type = input.attr("data-type");
		let currentVal = parseInt(input.val());
		let step = parseInt(input.attr('step'));
		if (!isNaN(currentVal)) {
			if(type == 'minus') {
				if(currentVal > input.attr('min')) {
					input.val(parseInt(currentVal) - step).change();
				} 
				if(parseInt(input.val()) == input.attr('min')) {
					$(this).attr('disabled', true);
				}
				if(parseInt(input.val())==0){
					$(this).hide();
					$(input).hide();
					$(input).next().children("button").text("+ Add");
				}
			} else if(type == 'plus') {
				
				$(input).prev().children("button").show();
				$(input).show();
				$(this).text("+");
				if(input.attr('max')==undefined ||  currentVal < input.attr('max')) {
					input.val(parseInt(currentVal) + step).change();
				} 
				if(parseInt(input.val()) == input.attr('max')) {
					$(this).attr('disabled', true);
				}
				
			}
			// if(plan_type=="base_plan"){
			// 	cart["base_plan"]["qty"]=parseInt(input.val());	
			// }else{
			// 	cart["add_ons"][fieldName]=parseInt(input.val());
			// }
			// get_cart();
		} else {
			input.val(0);
		}
	});

	$("#payment-button").click(function(){
		frappe.call({"method":"better_saas.www.upgrade.pay", args:{
			cart: cart,
			site_name: site_name,
			email: email,
			currency:currency,
			onehash_partner: onehash_partner
		},freeze:true,freeze_message:"Updating subscription"}).then(r=>{
			if(r.message){
				if(r.message.redirect_to){
					window.location.href=r.message.redirect_to;
				}else{
					frappe.msgprint(r.message.message)
				}
			} 
		});
	});

	function get_cart(){
		frappe.call({"method":"better_saas.www.upgrade.get_cart_value", args:{
			cart: cart,
			site_name: site_name,
			email: email,
			currency:currency,
			onehash_partner: onehash_partner
		},freeze:true,freeze_message:"getting cart value"}).then(r=>{
			$("#checkout-wrapper").html(r.message)
			$('.btn-number').click(function(e){
				e.preventDefault();
				let fieldName = $(this).attr('data-field');
				let type      = $(this).attr('data-type');
				let input = $("input[name='"+fieldName+"']");
				let plan_type = input.attr("data-type");
				let currentVal = parseInt(input.val());
				let step = parseInt(input.attr('step'));
				if (!isNaN(currentVal)) {
					if(type == 'minus') {
						if(currentVal > input.attr('min')) {
							input.val(parseInt(currentVal) - step).change();
						} 
						if(parseInt(input.val()) == input.attr('min')) {
							$(this).attr('disabled', true);
						}
						if(parseInt(input.val())==0){
							$(this).hide();
							$(input).hide();
							$(input).next().children("button").text("+ Add");
						}
					} else if(type == 'plus') {
						$(input).prev().children("button").show();
						$(input).show();
						$(this).text("+");
						if(input.attr('max')==undefined ||  currentVal < input.attr('max')) {
							input.val(parseInt(currentVal) + step).change();
						}
						if(parseInt(input.val()) == input.attr('max')) {
							frappe.msgprint("You have added the max allowed limit");
						}
						
					}
					// if(plan_type=="base_plan"){
					// 	cart["base_plan"]["qty"]=parseInt(input.val());	
					// }else{
					// 	cart["add_ons"][fieldName]=parseInt(input.val());
					// }
					// get_cart();
				} else {
					input.val(0);
				}
			});
			$(".input-number").change(function(){
				let input = $(this);
				let plan_type = input.attr("data-type");
				let fieldName = input.attr("name");
				let current_value = parseInt(input.val());
				let max_value = input.attr("max")!=undefined?input.attr("max"):0;
				let min_value = input.attr("min")!=undefined?input.attr("min"):0;
				if(max_value>0 && current_value>max_value){
					input.val(parseInt(max_value))
				}
				if(current_value<0){
					input.val(0)
				}
				if(plan_type=="base_plan"){
					cart["base_plan"]["qty"]=parseInt(input.val());	
				}else{
					cart["add_ons"][fieldName]=parseInt(input.val());
				}
				get_cart();
			});
		});
	}
	function set_query_params() {
		site_name = frappe.utils.get_url_arg('site');
		site_name = frappe.utils.escape_html(site_name);
		email = frappe.utils.get_url_arg('email');
		email = frappe.utils.escape_html(email);
		onehash_partner = frappe.utils.get_url_arg('onehash_partner');
		onehash_partner = frappe.utils.escape_html('onehash_partner');
	}

	function verify_system_user() {
		frappe.call("better_saas.www.upgrade.verify_system_user", {
			site_name: site_name,
			email: email,
		}).then(r => {
			if (r.message == false) {
				$("#cancel-button").hide();
				$("#payment-button").hide();
				frappe.throw(`You don't have permission to access this page. Please contact <a href="mailto:support@onehash.ai">support@onehash.ai<a> or your site Administrator.`);
				return
			}
			//get_site_details();
		});
	}

	function get_site_details() {
		frappe.call('better_saas.www.upgrade.get_current_limits', {
			site_name: site_name
		}).then(r => {
			let site_details = r.message.site;
			base_plan = r.message.plan;
			subscription = site_details.subscription;
			if(subscription){
				checkout()
			}
			addons = r.message.addons;
			cart["plan"] = base_plan.name;
			let formatted_expiry = r.message.formatted_expiry;
			//let expiry_date = site_details.expiry;
			let currency = base_plan.currency && base_plan.currency == "INR" ? "&#8377;" : "$";
			let subscribed_users = site_details.limit_for_users;
			let subscription_value = r.message.subscription_value;
			let discounted_users = r.message.discounted_users;
			let non_discounted_subscription_amount = r.message.non_discounted_subscription_amount;
			let site_usages = `<div><span>
                                    ${(new Date(formatted_expiry) < new Date()) ? 'Your subscription expired on' : 'Your subscription renews on'}<b> ${formatted_expiry} </b></span>
                                    <!---->
                                </div>
                                <div>
                                    Number of users in current subscription: <b> ${subscribed_users} </b>
                                </div>
                                ${discounted_users > 0 ? `<div>
                                    Number of discounted users in current subscription: <b> ${discounted_users} </b>
                                </div>`: ''}`
			$("#site_info").html(site_usages);
			$(".subscribed-users").html(subscribed_users + " Users @ "+currency+base_plan.cost+"/User/"+base_plan.billing_interval );
			//$("#discount").text(+" Off");
			$(".subscribed-storage").text(site_details.limit_for_space + "GB Of Storage");
			$(".subscribed-emails").text(site_details.limit_for_emails + " emails per month");
			$(".currency-symbol").html(currency);
			$(".subscription-amount").html(subscription_value);
			console.log(parseInt(non_discounted_subscription_amount) != parseInt(subscription_value), non_discounted_subscription_amount, subscription_value, parseInt(subscription_value), parseInt(non_discounted_subscription_amount))
			if (parseInt((non_discounted_subscription_amount).toString().split(",").join("")) != parseInt((subscription_value).toString().split(",").join(""))) {
				$(".non-discounted-subscription-amount").html(
					`<s>${currency} ${non_discounted_subscription_amount}</s>
                    <span class="text-muted billing-frequency" style="font-size: 16px;">/month</span>`);
			}

			if (subscription) {
				//$("#cancel-button").show();
				$("#payment-button").text("Update Subscription");
			}
			else {
				$("#cancel-button").hide();
				$("#payment-button").text("Pay Now");
			}
			/* Subscripiton Plans */

			/*let { site, plans, addons, address, legacy_plan, pending_downgrades, formatted_expiry, site_users, plan_wise_discount } = r.message;
			this.site = site;
			this.plans = plans;
			this.address = address;
			this.legacy_plan = legacy_plan;
			this.pending_downgrades = pending_downgrades;
			this.formatted_expiry = formatted_expiry;
			this.addons = addons;
			this.cart.plan = this.site.base_plan;
			this.cart.billing_cycle = this.site.subscription_type;
			this.site_users = site_users;
			this.plan_wise_discount = plan_wise_discount;*/
			let addon_html = "";
			for (addon in addons) {
				addon = addons[addon];
				let addon_type = addon.addon_type;
				block_html = `
                                <div class="card h-100" style="border: 1px solid black; 
                                                                width: fit-content;
                                                                min-width: 23%;
                                                                padding-bottom: 10px;
                                                                padding-right: 10px;
                                                                margin: 10px;">  
                                    <div class="card-body">
                                        <h6 class="card-title text-uppercase ">${addon.addon_type}</h6>
                                        <div><span>${currency}</span> <span>${addon.monthly_amount}</span> <span>/ ${addon.addon_value} ${addon.addon_type == "Space" ? 'GB' : ''} ${addon.addon_type}</span> 
                                        <span class="text-muted">/month</span></div>
                                        <div class="mt-3">
                                            <div><a href="" class="text-dark add-on" data-addon-name="${addon_type}" data-addon-type="Add">+ Add ${addon_type}</a></div>
                                            <div><a href="" class="text-dark add-on" data-addon-type="Remove" data-addon-name="${addon_type}">- Remove ${addon_type}</a></div>
                                        </div>
                                    </div>
                                </div>
                            `;
				addon_html += block_html;
			}
			$("#saas-addons").html(addon_html);
			$(".add-on").off("click").on("click", function (e) {
				e.preventDefault();
				let addon_type = $(this).data('addon-type');
				let addon_name = $(this).data('addon-name');
				let multiplier = (addon_type == "Remove") ? -1 : 1;
				frappe.prompt({
					label: "Enter No of " + addon_name,
					fieldtype: "Int",
					fieldname: addon_name
				},
					(values) => {
						for (value in values) {
							cart[addon_name] = (cart[addon_name] != null ? cart[addon_name] : 0) + values[value] * multiplier;
						}
						get_cart_value();
					},
					addon_type + " " + addon_name,
					addon_type + " " + addon_name
				);
			});
			get_billing_address();
			get_cart_value();
		});
	}

	set_query_params();
	verify_system_user();

});