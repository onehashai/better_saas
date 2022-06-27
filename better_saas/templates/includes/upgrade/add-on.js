var site_name;
var email;
var currency;
var has_billing_address=false;
var onehash_partner;
var base_plan;
let total=0;
var final_cart=[];
var addons = {};
frappe.flags.cart={};
frappe.ready(function () {
    let $page = $('#page-add-on');
    let minimum = {
        'P-Pro-2020': 1,
        'P-Standard-2020': 1
    }

    function set_query_params() {
        site_name = frappe.utils.get_url_arg('site');
        site_name = frappe.utils.escape_html(site_name);
        email = frappe.utils.get_url_arg('email');
        currency = frappe.utils.get_url_arg('currency');
        // if(typeof frappe.boot.sysdefaults ==='undefined'){
        //     frappe.boot.sysdefaults={};
        // }
        // frappe.boot.sysdefaults["currency"]=currency;
        email = frappe.utils.escape_html(email);
        onehash_partner = frappe.utils.get_url_arg('onehash_partner');
        onehash_partner = frappe.utils.escape_html('onehash_partner');
    }

    function verify_system_user() {
        frappe.call("better_saas.www.upgrade_old.verify_system_user", {
            site_name: site_name,
            email: email,
        }).then(r => {
            if (r.message == 'false') {
                frappe.throw(_(`Authorization Failed, Please contact <a href="mailto:support@onehash.ai">support@onehash.ai<a> or your site Administrator.`));
            }
        });
    }

    function get_billing_address() {
		frappe.call('better_saas.www.upgrade_old.get_billing_address', {
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
        enable_pay_button();
	}

    function get_cart_value() {
        frappe.call('better_saas.www.add-on.get_cart_details', {
            cart: cart,
            site_name: site_name,
            email: email,
            onehash_partner: onehash_partner
        }).then(r => {
            let cart = r.message.cart_details.cart;
            var total_amount = r.message.cart_details.total;
            let currency = r.message.plan.currency && r.message.plan.currency == "INR" ? "&#8377;" : "$";
            let checkout_header = `<div class="row border-bottom text-muted">
                            <div class="col-5 py-2 px-3">
                                Item
                            </div>
                            <div class="col-2 py-2 px-3 text-right text-nowrap">
                                Qty
                            </div>
                            <div class="col-4 py-2 px-3  text-nowrap"><span style="float: right;"> Amount </span></div>
                            <div class="col-1"></div>
                        </div>`;
            let row_html = "";
            cart.forEach(cart_row => {
                row_html += `<div class="row">
                    <div class="col-5 py-2 px-3">
                    ${cart_row.upgrade_type}
                    </div>
                    <div class="col-2 py-2 px-3 text-right text-nowrap">
                    ${cart_row.value}
                    </div>
                    <div class="col-4 py-2 px-3  text-nowrap"><span style="float: right;"> ${currency} ${cart_row.amount} </span></div>
                    <div class="col-1"><button type="button" class="btn btn-link remove-button"><i class="fa fa-times" aria-hidden="true"></i></button></div>
                    </div>`;
            });
            let total_row = `<div class="row font-weight-bold border-top">
                                <div class="col-5 py-2 px-3">
                                    Total
                                </div>
                                <div class="col-2 py-2 px-3 text-right text-nowrap"></div>
                                <div class="col-4 py-2 px-3 text-right text-nowrap">
                                <span>${currency} ${total_amount}</span>
                                </div>
                                <div class="col-1"></div>
                            </div>
                            ${r.message.cart_details.total_tax > 0 ?
                    `<div class="row font-weight-bold border-top">
                                    <div class="col-5 py-2 px-3"></div>
                                    <div class="col-2 py-2 px-3 text-right text-nowrap"></div>
                                    <div class="col-4 py-2 px-3 text-right text-nowrap" style="font-size: small;">
                                        Tax amount to be charged: <span style="font-weight:bolder;">${currency} ${r.message.cart_details.total_tax}</span>
                                    </div>
                                    <div class="col-1"></div>
                                </div>`: ''}`;
            $("#checkout-wrapper").html(checkout_header + row_html + total_row);
        });
    }

    function render_cart(){
        total = 0.00;
        final_cart=[];
        $.each(frappe.flags.cart,(key,value)=>{
            total = parseFloat(total)+parseFloat(value.total);
            value.formatted_total = format_currency(value.total,currency,2);
            value.currency = currency;
            final_cart.push(value);
        });
        $page.find("#checkout-wrapper").html(frappe.render_template("addon-cart",{cart:final_cart,total:format_currency(total,currency,2)}));
        enable_pay_button();
    }

    function get_site_details() {
        
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
		frappe.call("better_saas.www.upgrade_old.get_country_list").then(r=>{
			if(r.message){
				country_list = r.message
			}
			frappe.call("better_saas.www.upgrade_old.get_billing_address", {
				site_name: site_name
			}).then(r => {
				if (r.message.status_code !== '404') {
					frappe.call('better_saas.www.upgrade_old.get_address', {
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
							frappe.call('better_saas.www.upgrade_old.update_billing_address', {
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
						frappe.call('better_saas.www.upgrade_old.create_billing_address', {
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
    $("#payment-button").off("click").on("click", function () {
        frappe.call({
            "method":"better_saas.www.add-on.buy", 
            args:{
                "cart":final_cart,
                "currency":currency,
                "site_name": site_name,
                "cancel_url":window.location.href
        },
        callback:(r)=>{
            if (r.message && r.message.redirect_to) {
                window.location.href = r.message.redirect_to;
            }
            }
        });
    });

    function enable_pay_button(){
        $("#payment-button").prop("disabled",(!has_billing_address && total==0));
		if(!has_billing_address){
			$("#pay-message").text("Please, Add Address to proceed.");
			$("#pay-message").removeClass("hide");
		}else{
			$("#pay-message").addClass("hide");
		}
		
	}

    function get_addons(){
        let formdata = "site_name="+frappe.boot.sitename;
        console.log(currency);
        frappe.call({
            method:"better_saas.www.add-on.get_addon",
            args:{
                "currency":currency
            },
            callback:function(r){
                if(!r.exc){
                    $page.find("#saas-addons").html(frappe.render_template("addons-list",{addon_list:r.message,addon_limits:{}, currency:currency}));
                }
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
                        frappe.flags.cart[fieldName]={"qty":parseInt(input.val()),"name":fieldName,"rate":parseFloat(input.data("rate")).toFixed(2),"total":(parseFloat(input.data("rate")).toFixed(2)*parseInt(input.val())).toFixed(2)}
                        render_cart();
                    } else {
                        input.val(0);
                    }
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
						frappe.flags.cart[name]={"qty":parseInt(input.val()),"name":name,"rate":parseFloat(input.data("rate")).toFixed(2),"total":(parseFloat(input.data("rate")).toFixed(2)*parseInt(input.val())).toFixed(2)}
                        render_cart();
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
            }
        });
			// $.ajax({
			// 	url:"https://"+master_domain+"/api/method/better_saas.www.add-on.get_addon",
			// 	data: {"currency":frappe.boot.sysdefaults.currency},
			// 	crossDomain:true,
			// 	success: function(r) {
			// 		if(r.message){
			// 			$(page.main).find("#saas-addon").html(frappe.render_template("addons",{addon_list:r.message,addon_limits:addon_limits,master_domain:master_domain,site_name:site_name,currency:frappe.boot.sysdefaults.currency}));
			// 		}
			// 	},
			// 	error:function(xhr,status,error){
			// 		$(page.main).find("#saas-addon").html("Sorry, Could not load Addon.");
			// 	}
			// });

    }
    set_query_params();
    get_addons();
    get_billing_address();
    // load_cart();
    
    // verify_system_user();
    // get_site_details();
});