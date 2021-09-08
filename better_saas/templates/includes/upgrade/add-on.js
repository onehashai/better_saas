var site_name;
var email;
var onehash_partner;
var base_plan;
var cart = {};
var addons = {};

frappe.ready(function () {
    let $page = $('#page-upgrade');
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
            if (r.message == 'false') {
                frappe.throw(_(`Authorization Failed, Please contact <a href="mailto:support@onehash.ai">support@onehash.ai<a> or your site Administrator.`));
            }
        });
    }

    function get_billing_address() {
        frappe.call('better_saas.www.upgrade.get_billing_address', {
            site_name: site_name
        }).then(r => {
            if (r.message.status_code !== '404') {
                frappe.call('frappe.contacts.doctype.address.address.get_address_display', {
                    address_dict: r.message
                }).then(r => {
                    $('#address-wrapper').html(r.message);
                    $('#change-billing-address-text').text("Change Billing Address");
                });
            }
            else {
                $('#address-wrapper').text("Billing Address not available");
                $('#change-billing-address-text').text("Add Billing Address");
            }
        });
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

    function get_site_details() {
        frappe.call('better_saas.www.add-on.get_site_details', {
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
            let currency = base_plan.currency && base_plan.currency == "INR" ? "&#8377;" : "$";
            let subscribed_users = site_details.limit_for_users;
            let subscription_value = r.message.subscription_value;
            let site_usages = `<div><span>
            Your subscription expires on <b> ${formatted_expiry} </b></span>
        <!---->
        </div>
        <div>
        Number of users in current subscription: <b> ${subscribed_users} </b></div>`
            $("#site_info").html(site_usages);
            $(".subscribed-users").text(subscribed_users + " Users");
            //$("#discount").text(+" Off");
            $(".subscribed-storage").text(site_details.limit_for_space + "GB Of Storage");
            $(".subscribed-emails").text(site_details.limit_for_emails + " emails per month");
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
            let addon_html = "";
            for (addon in addons) {
                addon = addons[addon];
                let addon_type = addon.addon_type;
                let addon_value = addon.addon_value;
                if (addon_type !== "Users") {

                    block_html = `
                                    <div class="card h-100" style="border: 1px solid black; 
                                                                    min-width: 23%;
                                                                    width: fit-content;
                                                                    padding-bottom: 10px;
                                                                    padding-right: 10px;
                                                                    margin: 10px;">
                                        <div class="card-body">
                                            <h6 class="card-title text-uppercase ">${addon.addon_type}</h6>
                                            <div><span>${currency}</span> <span>${addon.per_credit_price}</span> <span>/ ${addon.addon_value}
                                                    ${(addon.addon_type == "Space") ? `GB` : ''} ${addon.addon_type}</span></div>
                                            <div class="mt-3">
                                                <div><a href="" class="text-dark add-on" data-addon-name="${addon_type}" data-addon-value="${addon_value}" data-addon-type="Add">+ Add
                                                        ${addon_type}</a></div>
                                            </div>
                                        </div>
                                    </div>
                                `;
                    addon_html += block_html;
                }
            }
            $("#saas-addons").html(addon_html);
            $(".add-on").off("click").on("click", function (e) {
                e.preventDefault();
                let addon_type = $(this).data('addon-type');
                let addon_name = $(this).data('addon-name');
                let min_purchase_value = $(this).data('addon-value');
                let multiplier = (addon_type == "Remove") ? -1 : 1;
                frappe.prompt({
                    label: "Enter No of " + addon_name,
                    fieldtype: "Int",
                    fieldname: addon_name
                },
                    (values) => {
                        for (value in values) {
                            cart[addon_name] = values[value] * min_purchase_value * multiplier;
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
    $("#change-billing-address-link").off("click").on("click", function () {
        frappe.call("better_saas.www.upgrade.get_billing_address", {
            site_name: site_name
        }).then(r => {
            if (r.message.status_code !== '404') {
                frappe.call('better_saas.www.upgrade.get_address', {
                    address: r.message,
                }).then(r => {
                    let address = r.message;
                    frappe.prompt([
                        {
                            label: 'Address Title',
                            fieldname: 'address_title',
                            fieldtype: 'Data',
                            read_only: 1,
                            default: address.address_title,
                        },
                        {
                            label: 'Address Type',
                            fieldname: 'address_type',
                            fieldtype: 'Data',
                            read_only: 1,
                            default: "Billing",
                        },
                        {
                            label: 'Email',
                            fieldname: 'email_id',
                            fieldtype: 'Data',
                            default: address.email_id,
                        },
                        {
                            label: 'Phone',
                            fieldname: 'phone',
                            fieldtype: 'Data',
                            default: address.phone,
                        },
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
                            label: 'State/Province',
                            fieldname: 'state',
                            fieldtype: 'Data',
                            default: address.state,
                            depends_on: "eval: this.country != 'India'",
                        },
                        {
                            label: 'Country',
                            fieldname: 'country',
                            fieldtype: 'Data',
                            default: address.country,
                        },
                    ], (values) => {
                        frappe.call('better_saas.www.upgrade.update_billing_address', {
                            values: values,
                        }).then(r => {
                            get_billing_address();
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
                    });
                });
            }
            else {
                frappe.prompt([
                    {
                        label: 'Address Title',
                        fieldname: 'address_title',
                        fieldtype: 'Data',
                        reqd: 1,
                    },
                    {
                        label: 'Address Type',
                        fieldname: 'address_type',
                        fieldtype: 'Data',
                        read_only: 1,
                        default: "Billing",
                    },
                    {
                        label: 'Email',
                        fieldname: 'email_id',
                        fieldtype: 'Data',
                    },
                    {
                        label: 'Phone',
                        fieldname: 'phone',
                        fieldtype: 'Data',
                    },
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
                        label: 'State/Province',
                        fieldname: 'state',
                        fieldtype: 'Data',
                        depends_on: "eval: this.country != 'India'",
                    },
                    {
                        label: 'Country',
                        fieldname: 'country',
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
                        }
                        else {
                            frappe.show_alert({
                                message: __('Billing Address Not Updated'),
                                indicator: 'red'
                            }, 5);
                        }
                    });
                });
            }
        });
    });
    $("#cancel-button").off("click").on("click", function () {
        frappe.warn('Are you sure you want to proceed?',
            'Your account will get deactivated, if you cancel this subscription.',
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
            'Continue',
            false // Sets dialog as minimizable
        )
    });
    $("#payment-button").off("click").on("click", function () {
        frappe.call('better_saas.www.ltd_checkout.pay', {
            // cart: cart,
            // site_name: site_name,
            // email: email,
            // onehash_partner: onehash_partner
        }).then(r => {
            if (r.message && r.message.redirect_to) {
                window.location.href = r.message.redirect_to;
            }
        });
    });
    set_query_params();
    verify_system_user();
    get_site_details();
});