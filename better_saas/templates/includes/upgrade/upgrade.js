var site_name;
var email;
var onehash_partner;
var subscription;
var has_billing_address=false;
var base_plan="{{active_plan_name}}";
var currency="{{currency}}";
var cart = {{ cart }};
var addons ={};
var plans = {};
var current_subscription={};

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
			delete cart[data.name]
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
			if(plan_type=="base_plan"){
				cart["base_plan"]["qty"]=parseInt(input.val());	
			}else{
				cart["add_ons"][fieldName]=parseInt(input.val());
			}
			get_cart();
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
					if(plan_type=="base_plan"){
						cart["base_plan"]["qty"]=parseInt(input.val());	
					}else{
						cart["add_ons"][fieldName]=parseInt(input.val());
					}
					get_cart();
				} else {
					input.val(0);
				}
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