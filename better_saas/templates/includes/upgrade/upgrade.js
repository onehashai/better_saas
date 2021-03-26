var site_name;
var email;
var onehash_partner;
var base_plan;
var cart={};
var addons={};

frappe.ready(function () {
    let $page = $('#page-upgrage');
    let minimum = {
        'P-Pro-2020': 1,
        'P-Standard-2020': 1
    }
    
    function set_query_params(){
        site_name = frappe.utils.get_url_arg('site');
		site_name = frappe.utils.escape_html(site_name);
        email = frappe.utils.get_url_arg('email');
		email = frappe.utils.escape_html(email);
        onehash_partner = frappe.utils.get_url_arg('onehash_partner');
		onehash_partner = frappe.utils.escape_html('onehash_partner');
    }

    function get_cart_value(){
        frappe.call('better_saas.www.upgrade.get_cart_details', {
            cart:cart,
            site_name: site_name,
            email: email,
            onehash_partner: onehash_partner
        }).then(r => {
            let cart = r.message.cart_details.cart;
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
            let row_html="";
            cart.forEach(cart_row => {
                row_html+=`<div class="row">
                <div class="col-5 py-2 px-3">
                    ${cart_row.upgrade_type}
                </div>
                <div class="col-2 py-2 px-3 text-right text-nowrap">
                    ${cart_row.value}
                </div>
                <div class="col-4 py-2 px-3  text-nowrap"><span style="float: right;"> ${cart_row.amount_to_display} </span></div>
                <div class="col-1"></div>
            </div>`;
                
            });
            let total_row = `<div class="row font-weight-bold border-top">
            <div class="col-5 py-2 px-3">
                Total
            </div>
            <div class="col-2 py-2 px-3 text-right text-nowrap"></div>
            <div class="col-4 py-2 px-3 text-right text-nowrap">
                ${r.message.cart_details.total_to_display}
            </div>
            <div class="col-1"></div>
        </div>`;
        $("#checkout-wrapper").html(checkout_header+row_html+total_row);
        });
    }

    function get_site_details(){
        frappe.call('better_saas.www.upgrade.get_site_details', {
            site_name: site_name,
            email: email,
            onehash_partner: onehash_partner
        }).then(r => {
            let site_details = r.message.site;
            base_plan = r.message.plan;
            addons = r.message.addons;
            cart["plan"] = base_plan.name;
            let formatted_expiry = r.message.formatted_expiry;
            //let expiry_date = site_details.expiry;
            let currency = base_plan.currency && base_plan.currency=="INR"?"&#8377;":"$";
            let subscribed_users = site_details.limit_for_users;
            let subscription_value = r.message.subscription_value;
            let site_usages = `<div><span>
            Your trial expires on <b> ${formatted_expiry} </b></span>
        <!---->
        </div>
        <div>
        Number of users in current subscription: <b> ${subscribed_users} </b></div>`
            $("#site_info").html(site_usages);
            $(".subscribed-users").text(subscribed_users+" Users");
            //$("#discount").text(+" Off");
            $(".subscribed-storage").text(site_details.limit_for_space+"GB Of Storage");
            $(".subscribed-emails").text(site_details.limit_for_emails+" emails per month");
            $(".currency-symbol").html(currency);
            $(".subscription-amount").html(subscription_value);
            

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
            let addon_html ="";
            for (addon in addons){
                addon = addons[addon];
                let addon_type= addon.addon_type;
                block_html=`<div class="col-12 col-md mb-3 mb-md-0">
                        <div class="card h-100">
                            <div class="card-body">
                                <h6 class="card-title text-uppercase ">${addon.addon_type}</h6>
                                <div><span>${currency}</span> <span>${addon.monthly_amount}</span> <span>/ ${addon.addon_value} ${addon.addon_type}</span> <span class="text-muted">/
                                        month</span></div>
                                <div class="mt-3">
                                    <div><a href="" class="text-dark add-on" data-addon-name="${addon_type}" data-addon-type="Add">+ Add ${addon_type}</a></div>
                                    <div><a href="" class="text-dark add-on" data-addon-type="Remove" data-addon-name="${addon_type}">- Remove ${addon_type}</a></div>
                                </div>
                            </div>
                        </div>
                    </div>`;
                addon_html+=block_html;
            }
            $("#saas-addons").html(addon_html);
            $(".add-on").off("click").on("click",function(e){
                e.preventDefault();
                let addon_type = $(this).data('addon-type');
                let addon_name = $(this).data('addon-name');
                let multiplier = (addon_type=="Remove")?-1:1;
                frappe.prompt({
                    label:"Enter No of "+addon_name,
                    fieldtype:"Int",
                    fieldname: addon_name
                },
                (values) => {
                    for(value in values){
                        cart[addon_name] = values[value]*multiplier;
                    }
                    get_cart_value();
                },
                addon_type+" "+addon_name,
                addon_type+" "+addon_name
            );
            });
            get_cart_value();
        });
    }
    $("#payment-button").off("click").on("click",function(){
        frappe.call('better_saas.www.upgrade.pay', {
            cart:cart,
            site_name: site_name,
            email: email,
            onehash_partner: onehash_partner
        }).then(r => {
            if(r.message && r.message.redirect_to){
                window.location.href = r.message.redirect_to;
            }
        });
    });
    set_query_params();
    get_site_details();
});