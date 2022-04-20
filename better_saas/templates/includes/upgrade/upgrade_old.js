var site_name;
var email;
var onehash_partner;
var subscription;
var has_billing_address=false;
var base_plan;
var cart = {};
var addons = {};

frappe.ready(function () {
	let $page = $('#page-upgrage');
	let minimum = {
		'P-Pro-2020': 1,
		'P-Standard-2020': 1
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
				frappe.throw(`Authorization Failed, Please contact <a href="mailto:support@onehash.ai">support@onehash.ai<a> or your site Administrator.`);
			}
			else {
				get_site_details();
			}
		});
	}

	function get_billing_address() {
		frappe.call('better_saas.www.upgrade.get_billing_address', {
			site_name: site_name
		}).then(r => {
			if (r.message.status_code !== '404') {
				$('#address-wrapper').html(r.message.address_display);
				$('#change-billing-address-text').text("Update Address");
				has_billing_address=true;
			}
			else {
				$('#address-wrapper').text("Billing Address not available");
				$('#change-billing-address-text').text("Add Address");
				has_billing_address=false;
				enable_pay_button();
			}
		});
	}

	function enable_pay_button(){
		$("#payment-button").prop("disabled",!has_billing_address);
		if(!has_billing_address){
			$("#pay-message").text("Please, Add Address to proceed.");
			$("#pay-message").removeClass("hide");
		}else{
			$("#pay-message").addClass("hide");
		}
		
	}

	function get_cart_value() {
		frappe.call('better_saas.www.upgrade.get_cart_details', {
			cart: cart,
			site_name: site_name,
			email: email,
			onehash_partner: onehash_partner
		}).then(r => {
			let cart_reponse = r.message.cart_details.cart;
			let currency = r.message.plan.currency && r.message.plan.currency == "INR" ? "&#8377;" : "$";
			let checkout_header = `<div class="row border-bottom text-muted">
                            <div class="col-md-5 col-xs-4 py-2 px-3">
                                Item
                            </div>
                            <div class="col-md-2 col-xs-3 py-2 px-3 text-center text-nowrap">
                                Qty
                            </div>
                            <div class="col-4 py-2 px-3  text-nowrap"><span style="float: right;"> Amount </span></div>
                            <div class="col-1"></div>
                        </div>`;
			let row_html = "";
			let hide_names=[];
			cart_reponse.forEach(cart_row => {
				row_html += `<div class="row">
                <div class="col-md-5 col-xs-4 py-2 px-3">
                    ${cart_row.upgrade_type}
                </div>
                <div class="col-md-2 col-xs-3 py-2 px-3 text-center text-nowrap">
				<div class="input-group number-widget">
				    <span class="input-group-prepend">
					    <button type="button" class="btn btn-outline-primary btn-number btn-xs" style="" data-type="minus" data-field="${cart_row.upgrade_type}">-</button>
					</span>                     
				<input type="text" name="${cart_row.upgrade_type}" data-upgrade-type="${cart_row.upgrade_type}" data-current-value="${cart_row.value}" class="form-control input-number text-center" value="${cart_row.value}" id="${cart_row.upgrade_type}"  min="0" data-currency="${cart_row.plan.currency}" data-rate="${cart_row.plan.monthly_amount}" step="${cart_row.plan.addon_value}">                     
				<span class="input-group-append">
				<button type="button" class="btn btn-outline-primary btn-number btn-xs" data-type="plus" data-field="${cart_row.upgrade_type}">+</button>                     </span>                 </div>
                   
                </div>
                <div class="col-4 py-2 px-3 text-nowrap"><span style="float: right;"> <span>${currency}</span> ${cart_row.amount} </span></div>
            </div><div class="col-1"></div>`;
			if(cart_row.value==0){
				hide_names.push(cart_row.upgrade_type)
			}

			});
			let total_row = `<div class="row font-weight-bold border-top">
                                <div class="col-md-5 col-xs-4 py-2 px-3">
                                </div>
                                <div class="col-md-2 col-xs-3 col-xs-3 py-2 px-3 text-right text-nowrap">Total</div>
                                <div class="col-4 py-2 px-3 text-right text-nowrap">
                                    <span>${currency}</span> ${r.message.cart_details.total}
                                </div>
								<div class="col-1"></div>
                            </div>
                            ${r.message.cart_details.total_tax > 0 ?
					`<div class="row border-top">
					<div class="col-md-5 col-xs-4 py-2 px-3">
                                </div>
								<div class="col-md-2 col-xs-3 col-xs-3 py-2 px-3 text-right text-nowrap">Tax</div>
								<div class="col-4 py-2 px-3 text-right text-nowrap">
                                    <span>${currency}</span> ${r.message.cart_details.total_tax}
                                </div>
                                <div class="col-1"></div>
                            </div>
							<div class="row font-weight-bold border-top">
							<div class="col-md-5 col-xs-4 py-2 px-3">
										</div>
										<div class="col-md-2 col-xs-3 col-xs-3 py-2 px-3 text-right text-nowrap">Grand Total</div>
										<div class="col-4 py-2 px-3 text-right text-nowrap">
											<span>${currency}</span> ${r.message.cart_details.total+r.message.cart_details.total_tax}
										</div>
										<div class="col-1"></div>
									</div>		
							
							`: ''}`;
			$("#checkout-wrapper").html(checkout_header + row_html + total_row);
			$('.btn-number').click(function(e){
				e.preventDefault();
				let fieldName = $(this).attr('data-field');
				let type      = $(this).attr('data-type');
				let input = $("input[name='"+fieldName+"']");
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
						input.val(parseInt(currentVal) + step).change();
						
					}
					cart[fieldName]=parseInt(input.val());
					get_cart_value();
				} else {
					input.val(0);
				}
			});
			
			$.each(hide_names,function(key,value){
				$("#"+value).hide();
				$("#"+value).hide();
				$("#"+value).next().children("button").text("+ Add");
				$("#"+value).prev().children("button").hide();
			});
			$('.input-number').focusin(function(){
			   $(this).data('oldValue', $(this).val());
			});
			$('.input-number').change(function() {
				
				minValue =  parseInt($(this).attr('min'));
				maxValue =  parseInt($(this).attr('max'));
				valueCurrent = parseInt($(this).val());
				let input = $(this);
				let name = $(this).attr('name');
				if(valueCurrent >= minValue) {
					$(".btn-number[data-type='minus'][data-field='"+name+"']").removeAttr('disabled');
					cart[name]=parseInt(input.val());
				} else {
					alert('Sorry, the minimum value was reached');
					$(this).val($(this).data('oldValue'));
				}
			});
			
			$(".input-number").keydown(function (e) {
				// Allow: backspace, delete, tab, escape, enter and .
				if ($.inArray(e.keyCode, [46, 8, 9, 27, 13, 190]) !== -1 ||
					 // Allow: Ctrl+A
					(e.keyCode == 65 && e.ctrlKey === true) || 
					 // Allow: home, end, left, right
					(e.keyCode >= 35 && e.keyCode <= 39)) {
						 // let it happen, don't do anything
						 return;
				}
				// Ensure that it is a number and stop the keypress
				if ((e.shiftKey || (e.keyCode < 48 || e.keyCode > 57)) && (e.keyCode < 96 || e.keyCode > 105)) {
					e.preventDefault();
				}
			});
			$(".cart-qty").on("change",(context)=>{
				let count = 0;
				$(".cart-qty").each((index,ele)=>{
					let current_value = $(ele).val();
					count= count+parseInt(current_value);
					let upgrade_type = $(ele).data('upgrade-type');
					cart[upgrade_type]=parseInt(current_value);
				});
				if(count>0){
					get_cart_value();
					$("#payment-button").prop("disabled",false);
					enable_pay_button();
				} else {
					$("#payment-button").prop("disabled",true);
					frappe.msgprint("Qty must be greater than Zero.");
				}
			});
		});
	}
	
	function get_site_details() {
		frappe.call('better_saas.www.upgrade.get_site_details', {
			site_name: site_name,
			email: email,
			onehash_partner: onehash_partner
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
	function checkout() {
		if(subscription){
			frappe.msgprint("Redirecting to Payment Gatway.");
		}
		frappe.call('better_saas.www.upgrade.pay', {
			cart: cart,
			site_name: site_name,
			email: email,
			onehash_partner: onehash_partner
		}).then(r => {
			if (r.message && r.message.redirect_to) {
				window.location.href = r.message.redirect_to;
			}
		});
	}

	$("#change-billing-address-link").off("click").on("click", function () {
		console.log("here");
		let country_list = [];
		let indian_states = [
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
		frappe.call("better_saas.www.upgrade.get_country_list").then(r=>{
			if(r.message){
				country_list = r.message
			}
			frappe.call("better_saas.www.upgrade.get_billing_address", {
				site_name: site_name
			}).then(r => {
				if (r.message.status_code !== '404') {
					frappe.call('better_saas.www.upgrade.get_address', {
						address: r.message.address_object,
					}).then(r => {
						let address = r.message;
						console.log(indian_states,country_list)
						frappe.prompt([
							{
								label: 'Address Line 1',
								fieldname: 'address_line1',
								fieldtype: 'Data',
								reqd: 1,
								default: address.address_line1,
							},
							{
								label: 'Address Line 2',
								fieldname: 'address_line2',
								fieldtype: 'Data',
								default: address.address_line2,
							},
							{
								label: 'City/Town',
								fieldname: 'city',
								fieldtype: 'Data',
								reqd: 1,
								default: address.city,
							},
							{
								label: 'Postal Code',
								fieldname: 'pincode',
								fieldtype: 'Data',
								reqd: 1,
								default: address.pincode,
							},
							{
								label: 'State/Province',
								fieldname: 'state',
								fieldtype: 'Data',
								default: address.state,
								depends_on: "eval: this.country != 'India'",
							},
							{
								label: 'Country',
								fieldname: 'country',
								fieldtype: 'Autocomplete',
								options:country_list,
								default: address.country,
							},
							{
								label: 'Are you registered for GSTIN?',
								fieldname: 'is_registered',
								fieldtype: 'Check',
							},
							{
								label: 'GST State',
								fieldname: 'gst_state',
								fieldtype: 'Autocomplete',
								mandatory_depends_on: "eval:doc.is_registered == 1",
								depends_on: "eval: doc.is_registered == 1",
								default: address.gst_state,
								options: indian_states,
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
								hidden: 1,
								default: address.name,
							},
							{
								label: 'Address Type',
								fieldname: 'address_type',
								fieldtype: 'Data',
								read_only: 1,
								hidden: 1,
								default: "Billing",
							},
							{
								label: 'Email (optional)',
								fieldname: 'email_id',
								fieldtype: 'Data',
								default: address.email_id,
							},
							{
								label: 'Phone (optional)',
								fieldname: 'phone',
								fieldtype: 'Data',
								default: address.phone,
							},
						], (values) => {
							frappe.call('better_saas.www.upgrade.update_billing_address', {
								values: values,
							}).then(r => {
								get_billing_address();
								console.log("Billig Address Update Response",r);
								if (r.message == 'success') {
									frappe.show_alert({
										message: __('Billing Address Updated'),
										indicator: 'green'
									}, 5);
								}
								else {
									frappe.show_alert({
										message: __('Billing Address Not Updated'),
										indicator: 'red'
									}, 5);
								}
							});
						},
						"Update Address",
						"Update Address"
						);
					});
				}
				else {
					frappe.prompt([
						{
							label: 'Address Line 1',
							fieldname: 'address_line1',
							fieldtype: 'Data',
							reqd: 1,
						},
						{
							label: 'Address Line 2',
							fieldname: 'address_line2',
							fieldtype: 'Data',
						},
						{
							label: 'City/Town',
							fieldname: 'city',
							fieldtype: 'Data',
							reqd: 1,
						},
						{
							label: 'Postal Code',
							fieldname: 'pincode',
							fieldtype: 'Data',
							reqd: 1,
						},
						{
							label: 'State/Province',
							fieldname: 'state',
							fieldtype: 'Data',
							depends_on: "eval: this.country != 'India'",
						},
						{
							label: 'Country',
							fieldname: 'country',
							fieldtype: 'Autocomplete',
							options:country_list
						},
						{
							label: 'Are you registered for GSTIN?',
							fieldname: 'is_registered',
							fieldtype: 'Check',
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
							label: 'Email (Optional)',
							fieldname: 'email_id',
							fieldtype: 'Data',
						},
						{
							label: 'Phone',
							fieldname: 'phone',
							fieldtype: 'Data',
						},
					], (values) => {
						frappe.call('better_saas.www.upgrade.create_billing_address', {
							site_name: site_name,
							values: values,
						}).then(r => {
							get_billing_address();
							if (r.message == 'success') {
								frappe.show_alert({
									message: __('Billing Address Updated'),
									indicator: 'green'
								}, 5);
								has_billing_address=true;
								enable_pay_button();
							}
							else {
								frappe.show_alert({
									message: __('Billing Address Not Updated'),
									indicator: 'red'
								}, 5);
							}
						});
					},
					"Add Address",
					"Add Address");
				}
			});
		});
		
	});
	$("#cancel-button").off("click").on("click", function () {
		frappe.warn('Cancel Your Subscription?',
			`<span style="font-size:1 rem;">Click <strong>"Finish Cancellation"</strong> below to cancel your Subscription.</span><br>
            <span style="font-size: smaller; font-weight: 600;"><li>Cancellation will be effective at the end of your current billing period.</li></span>`,
			() => {
				// action to perform if Continue is selected
				frappe.call('better_saas.www.upgrade.cancel', {
					site_name: site_name
				}).then(r => {
					if (r.message && r.message.redirect_to) {
						window.location.href = r.message.redirect_to;
					}
				});
			},
			'Finish Cancellation',
			false // Sets dialog as minimizable
		)
	});
	$("#payment-button").off("click").on("click", function () {
		if (subscription) {
			frappe.confirm(
				`<span>Are you sure you want to proceed?</span>
                <br>
                <span>This action will update your current subscription.</span><br>
                <span class="ml-1" style="font-size:small; font-weight:bold;">- Payment will be done automatically from your saved payment method.</span>`,
				() => {
					checkout();// action to perform if Yes is selected
				}, () => {
					// action to perform if No is selected
				})
		}
		else checkout();
	});
	set_query_params();
	verify_system_user();

	$("#promocode-form").on("submit",function(){
		let formdata = $(this).serialize();
		formdata += "&site_name="+site_name;
		$(".coupon").prop("disabled",true);
		$.ajax({
			url:"/api/method/better_saas.better_saas.doctype.saas_user.saas_user.apply_promocode",
			data: formdata,
			crossDomain:true,
			success: function(r) {
				if(r.message && r.message["success"]){
					$(".coupon").prop("disabled",false);
					$("#promo-validation-feedback").removeClass("invalid-feedback");
					$("#promo-validation-feedback").addClass("valid-feedback");
					$("#promo-validation-feedback").text(r.message["message"]);
					$("#promo-validation-feedback").show();
					$('[name="promocode"]').val("");
					setTimeout(() => {
						window.location.reload();	
					}, 2000);
				}
			},
			error:function(xhr,status,error){
				$(".coupon").prop("disabled",false);
				$("#promo-validation-feedback").show();
				message = JSON.parse(JSON.parse(xhr.responseJSON._server_messages)[0])["message"];
				$("#promo-validation-feedback").text(message);
			}
		});
	});
});