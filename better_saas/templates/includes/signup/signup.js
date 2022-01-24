frappe.ready(function () {
    let $page = $('#page-signup,#page-appsumo, #page-signup-1, #page-signup_ltd');
    let minimum = {
        'P-Pro-2020': 1,
        'P-Standard-2020': 1
    };

    // Get Country Codes
    const phoneInputField = document.querySelector("#tphone");
    const phoneInput = window.intlTelInput(phoneInputField, {
        initialCountry: "auto",
        preferredCountries: ["US", "IN", "SG"],
        utilsScript: "https://cdnjs.cloudflare.com/ajax/libs/intl-tel-input/17.0.8/js/utils.js",
        geoIpLookup: function (callback) {
            $.get('https://ipinfo.io', function () { }, "jsonp").always(function (resp) {
                var countryCode = (resp && resp.country) ? resp.country : "us";
                callback(countryCode);
            });
        },
    });

    // Define the signup stages
    setup_signup($('#page-signup'));
    setup_signup($('#page-signup_ltd'));
    setup_signup($('#page-appsumo'));

    //  Check for valid email
    $page.find('input[name="email"]').on('change load', function () {
        let email = $(this).val();
        $('#emailValidationMsg').text('Please enter a valid email address');
        if (!email) { return }
        else if (!valid_email(email)) {
            $(this).closest('.form-group').addClass('invalid');
        } else {
            $(this).closest('.form-group').removeClass('invalid');

            frappe.call('better_saas.www.signup.email_exists', {
                email: email
            }).then(r => {
                if (r.message) {
                    let site = r.message;
                    $('#emailValidationMsg').html(`Email already in use, try <a href="https://${site}/login" style="color:#2490ef">logging in</a>`);
                    $(this).closest('.form-group').addClass('invalid');
                } else {
                    $(this).closest('.form-group').removeClass('invalid');
                    $('#emailValidationMsg').html(`<span style="color:#0E8C4A;">Email is available</span>`).show();
                    $('input[name="email"]').css('border-color', '#0E8C4A');
                }
            });
        }
    });

    // PHONE 
    $page.find('input[name="phone_number"]').on('change focus', function () {
        const phoneNumber = phoneInput.getNumber();
        localStorage.setItem('phoneNum', phoneNumber);
    });

    // Check if Promocode is invalid
    $page.find('input[name="promocode"]').on('change', function () {
        let promocode = $(this).val();
        $(this).closest('.form-group').removeClass('invalid');

        if (promocode != '') {
            $(this).closest('.form-group').removeClass('invalid');
            frappe.call('better_saas.better_saas.doctype.saas_user.saas_user.is_valid_promocode', {
                promocode: promocode,
                is_new_user:1
            }).then(r => {
                if (!r.message || !r.message[0]) {
                    $(this).closest('.form-group').addClass('invalid');
                    $(this).css('border-color', '#D13830');
                    $(this).next().text("Please enter a valid promocode").css('color', '#D13830');
                } else {
                    $(this).closest('.form-group').removeClass('invalid');
                    $(this).css('border-color', '#0E8C4A');
                    $(this).next().text("Promocode is valid").css('color', '#0E8C4A').show();
                }
            });
        }
    });

    // Verify OTP
    $page.find('input[name="otp"]').on('keyup', () => {
        if ($page.find('input[name="otp"]').val().length == 6) {
            if ($('#otp').next().text() == "OTP verified successfully") { return; }
            $('#otp').css('border-color', '#377DE2');
            $('#otp').next().text("Verifying OTP...").css('color', '#377DE2');
            setTimeout(() => {
                verify_otp($page);
            }, 500);
        }
    });

    // Check if form is completed and all values are valid
    $page.find('.get-started-button').on('click', () => {
        if ($('.get-started-button').text() == "Get OTP") {
            setup_account_request($page);
        } else if ($('.get-started-button').text() == "Resend OTP") {
            resend_otp($page);
        } else if ($('.get-started-button').text() == "Get Started") {
            // setup_regional_details($page);
            frappe.msgprint("Work In Progress");
            return
        }
    });
});

setup_signup = function (page) {
    // button for signup event
    if (!page) {
        // fallback
        var page = $('#page-signup,#page-signup-1,#page-signup_ltd');
    }
    let minimum = {
        'P-Standard-2020': '5',
        'P-Pro-2020': '10'
    }

    $('input[name="number_of_users"]').val(minimum[frappe.utils.get_query_params().plan] || 5);

    $('input[name="number_of_users"]').on('change', function () {
        let number_of_users = Number($(this).val());

        if (isNaN(number_of_users) || number_of_users <= 0) {
            $(this).closest('.form-group').addClass('invalid');
        } else if (isNaN(number_of_users) || number_of_users < minimum_users) {
            frappe.throw(`Minimum user limit is ${minimum_users}`)
        } else {
            $(this).closest('.form-group').removeClass('invalid');

            $('.number_of_users').html(number_of_users);
            $('.user-text').html(number_of_users > 1 ? 'users' : 'user');
            $('.total-cost').html((plan.pricing.monthly_amount * number_of_users).toFixed(0));
        }
    });

    //-------------------------------------- Subdoamin Validation and Avalability Check -----------------------------

    page.find('input[name="subdomain"]').on('input', function () {
        domain_input_flag = 1;
        var $this = $(this);
        clearTimeout($this.data('timeout'));
        $this.data('timeout', setTimeout(function () {
            let subdomain = $this.val();
            set_availability_status('empty');
            if (subdomain.length === 0) {
                return;
            }

            page.find('.availability-status').addClass('hidden');
            var [is_valid, validation_msg] = is_a_valid_subdomain(subdomain);
            if (is_valid) {
                // show spinner
                page.find('.availability-spinner').removeClass('hidden');
                check_if_available(subdomain, function (status) {
                    set_availability_status(status, subdomain);
                    // hide spinner
                    page.find('.availability-spinner').addClass('hidden');
                });
            } else {
                set_availability_status('invalid', subdomain, validation_msg);
            }
        }, 500));
    });

    function set_availability_status(is_available, subdomain, validation_msg) {
        // reset
        page.find('.availability-status').addClass('hidden');
        page.find('.signup-subdomain').removeClass('invalid');
        if (typeof is_available === 'string') {
            if (is_available === 'empty') {
                // blank state
            } else if (is_available === 'invalid') {
                // custom validation message
                const form_control = page.find('.signup-subdomain').addClass('invalid');
                form_control.find('.validation-message').html(validation_msg || '');
            }
            return;
        }

        page.find('.availability-status').removeClass('hidden');
        if (is_available) {
            // available state
            page.find('.availability-status i').removeClass('octicon-x text-danger');
            page.find('.availability-status i').addClass('octicon-check text-success');

            page.find('.availability-status').removeClass('text-danger');
            page.find('.availability-status').addClass('text-success');
            page.find('.availability-status span').html(`${subdomain}.onehash.ai is available!`);
        } else {
            // not available state
            page.find('.availability-status i').removeClass('octicon-check text-success');
            page.find('.availability-status i').addClass('octicon-x text-danger');

            page.find('.availability-status').removeClass('text-success');
            page.find('.availability-status').addClass('text-danger');
            page.find('.availability-status span').html(`${subdomain}.onehash.ai is not available`);
        }
    }

    page.find('.btn-request').off('click').on('click', function () {

    });


    // change help description based on subdomain change
    $('[name="subdomain"]').on("keyup", function () {
        $('.subdomain-help').text($(this).val() || "");
    });

    // distribution
    // $('.erpnext-distribution').on("click", function() {
    // 	set_distribution(true);
    // });
    //
    // set_distribution();

    function is_a_valid_subdomain(subdomain) {
        var MIN_LENGTH = 4;
        var MAX_LENGTH = 20;
        if (subdomain.length < MIN_LENGTH) {
            return [0, `Sub-domain cannot have less than ${MIN_LENGTH} characters`];
        }
        if (subdomain.length > MAX_LENGTH) {
            return [0, `Sub-domain cannot have more than ${MAX_LENGTH} characters`];
        }
        if (subdomain.search(/^[A-Za-z0-9][A-Za-z0-9]*[A-Za-z0-9]$/) === -1) {
            return [0, 'Subdomain can use only letters and numbers'];
        }
        return [1, ''];
    }

    function check_if_available(subdomain, callback) {
        setTimeout(function () {
            frappe.call({
                method: 'better_saas.better_saas.doctype.saas_user.saas_user.check_subdomain_avai',
                args: {
                    subdomain: subdomain
                },
                type: 'POST',
                callback: function (r) {
                    if (r.message.status === "True") {
                        callback(1);
                    } else {
                        callback(0);
                        callback(0);
                        callback(0);
                        callback(0);
                        callback(0);
                    }
                },
            });
        }, 2000);
    }

    var query_params = frappe.utils.get_query_params();
    if (!query_params.plan) {
        query_params.plan = "P-Standard-2019"
        $("header,footer").addClass("hidden");
    } else {
        if (query_params.for_mobile_app) {
            // for mobile app singup, hide header and footer
            $("header,footer").addClass("hidden");
        }

        $('.plan-name').html(query_params.plan);
    }

    page.find(".plan-message").text("Free 14-day Trial");

    // if (['Free', 'Free-Solo'].indexOf(query_params.plan)!==-1) {
    // 		// keeping Free-Solo for backward compatibility
    // 		page.find(".plan-message").text("Free for 1 User");
    // 	}

    $('.domain-missing-msg').addClass("hidden");
    if (query_params.domain) {
        let domain = frappe.utils.escape_html(query_params.domain);
        let subdomain = domain
        if (subdomain.indexOf(".onehash.ai")) {
            subdomain = subdomain.replace(".onehash.ai", "");
        }
        $('[name="subdomain"]').val(subdomain);

        $('.missing-domain').html(domain);
        $('.missing-domain-msg').removeClass("hidden");
    }

    window.clear_timeout = function () {
        if (window.timout_password_strength) {
            clearTimeout(window.timout_password_strength);
            window.timout_password_strength = null;
        }
    };

    //-------------------------------------- Password Strength --------------------------------------
    window.strength_indicator = $('.password-strength-indicator');
    window.strength_message = $('.password-strength-message');

    $('#passphrase').on('keyup', function () {
        window.clear_timeout();
        window.timout_password_strength = setTimeout(test_password_strength, 200);
    });

    function test_password_strength() {
        window.timout_password_strength = null;
        return frappe.call({
            type: 'GET',
            method: 'better_saas.better_saas.doctype.saas_user.saas_user.check_password_strength',
            args: {
                passphrase: $('#passphrase').val(),
                first_name: $('input[name="first_name"]').val(),
                last_name: $('input[name="last_name"]').val(),
                email: $('input[name="email"]').val()
            },
            callback: function (r) {
                if (r.message) {
                    var score = r.message.score,
                        feedback = r.message.feedback;

                    feedback.crack_time_display = r.message.crack_time_display;
                    feedback.score = score;

                    if (feedback.password_policy_validation_passed) {
                        set_strength_indicator('green', feedback);
                        $('input[name="passphrase"]').closest('.form-group').removeClass('invalid');
                    } else {
                        set_strength_indicator('red', feedback);
                        $('input[name="passphrase"]').closest('.form-group').addClass('invalid');
                    }
                }
            }
        });
    }

    function set_strength_indicator(color, feedback) {
        var message = [];
        feedback.help_msg = "";
        if (!feedback.password_policy_validation_passed) {
            feedback.help_msg = "<br>" + "Suggestions: Include symbols, numbers and at least one capital letter";
            strength_message.attr('style', `color: #377DE2 !important; 
                                            border: 1px #377ce2 solid; 
                                            padding: 0px 2px 1px 6px;
                                            margin-top: 4px;
                                            margin-right: 14px;
                                            z-index: 5;
                                            font-size:10px;
                                            border-radius:8px;
                                            background: #fff;`);
            $('#passphrase').css('border-color', '#377DE2');
        }
        if (feedback) {
            if (!feedback.password_policy_validation_passed) {
                if (feedback.suggestions && feedback.suggestions.length) {
                    message = message.concat(feedback.suggestions);
                } else if (feedback.warning) {
                    message.push(feedback.warning);
                }
                message.push(feedback.help_msg);

            } else {
                message.push("Success! You are good to go 👍");
                strength_message.attr('style', 'color: #0E8C4A !important');
                $('#passphrase').css('border-color', '#0E8C4A');
            }
        }

        strength_indicator.removeClass().addClass('password-strength-indicator indicator ' + color);
        strength_message.html(message.join(' ') || '').removeClass('hidden');
        // strength_indicator.attr('title', message.join(' ') || '');
    }
};

// ------------------------------- Setup Signup Request ----------------------------------------------
function setup_account_request($page) {
    grecaptcha.ready(function () {
        grecaptcha.execute('6Lf6AeoaAAAAAASjFWeZlIS4zUpaa0jSxFAkjG2q', { action: 'submit' }).then(function (token) {
            // Add your logic to submit to your backend server here.
            if (!$page.find('input[name="first_name"]').val() ||
                !$page.find('input[name="last_name"]').val() ||
                !$page.find('input[name="subdomain"]').val() ||
                !$page.find('input[name="email"]').val() ||
                !$page.find('input[name="phone_number"]').val() ||
                !$page.find('input[name="passphrase"]').val() || !$page.find('input[name="company_name"]').val()) {

                frappe.msgprint("All fields are necessary. Please try again.");
                return false;

            } else if ($page.find('input[name="email"]').parent().hasClass('invalid')) {

                frappe.msgprint("Please enter a valid email.");
                return false;

            } else if ($page.find('input[name="email"]').parent().hasClass('not-available')) {

                frappe.msgprint("Email already in use, try logging in instead.");
                return false;

            } else if ($page.find('input[name="passphrase"]').parent().hasClass('invalid')) {

                frappe.msgprint("Please enter a strong password.");
                return false;

            } else if ($page.find('input[name="phone_number"]').parent().hasClass('invalid')) {

                frappe.msgprint("Please enter Phone Number.");
                return false;

            } else if ($page.find('input[name="company_name"]').parent().hasClass('invalid')) {
                frappe.msgprint("Please enter Company Name.");
                return false;

            } else {
                var args = Array.from($page.find('.signup-state-details input'))
                    .reduce(
                        (acc, input) => {
                            acc[$(input).attr('name')] = $(input).val();
                            return acc;
                        }, {});

                // Update Phone Number with Country Code 
                args.phone_number = localStorage.getItem('phoneNum');
                console.log("Form Data",args)
                // validate inputs
                const validations = Array.from($page.find('.form-group.invalid'))
                    .map(form_group => $(form_group).find('.validation-message').html());
                if (validations.length > 0) {
                    frappe.msgprint(validations.join("<br>"));
                    return;
                }

                if ($("input[name*='agree-checkbox']").prop("checked") === false) {
                    frappe.msgprint("Please agree to the Terms of Use and Privacy Policy.");
                    return;
                }

                // add plan to args
                var plan = frappe.utils.get_url_arg('plan');
                if (plan) args.plan = plan;

                var res = frappe.utils.get_url_arg('res');
                if (res) args.partner = res;

                
                var $btn = $page.find('.get-started-button');
                var btn_html = $btn.html();
                $btn.prop("disabled", true).html("OTP Sent");
                $page.find('input[name="otp"]').parent().removeClass('hide');
                

                // Lock Form Fields
                let inputArray = Array.from($page.find('.signup-card form input'));
                inputArray.pop();
                for (input in inputArray) {
                    console.log(inputArray[input]);
                    $(inputArray[input]).prop('readonly', true);
                }
                $("input[name*='agree-checkbox']").prop('disabled', true);
                $page.find('input[name="otp"]').prop('readonly',false);
                //goog_report_conversion(); // eslint-disable-line

                let locationParams = localStorage.getItem('urlKeywordParams')
                if (locationParams) {
                    let urlParams = new URLSearchParams(locationParams);
                    /*let ga_params = {
                        keyword: urlParams.get('utm_keyword'),
                        utm_source: urlParams.get('utm_source'),
                        campaignid: urlParams.get('utm_campaign'),
                        adgroupid: urlParams.get('adgroupid'),
                        loc_physical_ms: urlParams.get('utm_loc_physical_ms'),
                        vertical: urlParams.get('vertical')
                    }*/
                    args['utm_source'] = urlParams.get('utm_source');
                    args['utm_campaign'] = urlParams.get('utm_campaign');
                    args['utm_medium'] = urlParams.get('utm_medium');
                    args['utm_content'] = urlParams.get('utm_content');
                    args['utm_term'] = urlParams.get('utm_term');
                    //	args['ga_params'] = ga_params

                } else {
                    let urlParams = new URLSearchParams(window.location.search)
                    args['utm_source'] = urlParams.get('utm_source');
                    args['utm_campaign'] = urlParams.get('utm_campaign');
                    args['utm_medium'] = urlParams.get('utm_medium');
                    args['utm_content'] = urlParams.get('utm_content');
                    args['utm_term'] = urlParams.get('utm_term');
                }


                delete args['agree-checkbox'];

                frappe.call({
                    method: 'better_saas.better_saas.doctype.saas_user.saas_user.signup',
                    args: args,
                    type: 'POST',
                    btn: $btn,
                    callback: function (r) {
                        if (r.exc) return;

                        if (r.message) {
                            localStorage.setItem("reference", r.message.reference);
                            localStorage.setItem("email", r.message.email);
                            localStorage.setItem("mobile", r.message.mobile);
                            $('.verify-otp .email').text(r.message.email);
                            $('.mobile').text(r.message.mobile);
                            $page.find('input[name="otp"]').parent().removeClass('hide');
                            $('.get-started-button').text("Resend OTP").removeClass('btn-primary').addClass('btn-secondary');
                        }
                    },

                }).always(function () {
                    $btn.prop("disabled", false).html(btn_html);
                });
                return false;

            }
        });
    });
}

function verify_otp($page) {
    if (!$page.find('input[name="otp"]').val()) {
        $('#otp').parent().addClass('invalid');
        $('.invalid input').css('border-color', '#E5A403');
        $('#otp').next().text("OTP can't be empty").css('color', '#E5A403');
        return false;
    }

    var args = Array.from($page.find('input[name="otp"]'))
        .reduce(
            (acc, input) => {
                acc[$(input).attr('name')] = $(input).val();
                return acc;
            }, {});
    args['id'] = localStorage.getItem("reference");

    var $btn = $page.find('.get-started-button');

    frappe.call({
        method: 'better_saas.better_saas.doctype.saas_user.saas_user.verify_account_request',
        args: args,
        type: 'POST',
        btn: $btn,
        callback: function (r) {
            if (r.message == 'Invalid OTP') {
                $('#otp').parent().addClass('invalid');
                $('.invalid input').css('border-color', '#D13830');
                $('#otp').next().text("Please enter valid OTP").css('color', '#D13830');
                return false;
            } else if (r.message == 'OTP Expired') {
                $('#otp').parent().addClass('invalid');
                $('.invalid input').css('border-color', '#E5A403');
                $('#otp').next().text("Your OTP has expired").css('color', '#E5A403');
                return false;
            } else if (r.message == 'OTP Verified') {
                $('#otp').css('border-color', '#0E8C4A').prop("readonly", true);
                $('#otp').next().text("OTP verified successfully").css('color', '#0E8C4A').show();
                $('.get-started-button').text("OTP Verified").addClass('btn-primary').removeClass('btn-secondary');
                setTimeout(() => {
                    $('.get-started-button').text("Getting Started")
                    setTimeout(() => {
                        window.location.href = "../prepare_site";
                    }, 500);
                }, 500);
            }
        },
    });
}

function resend_otp($page) {
    var $btn = $page.find('.get-started-button');
    var btn_html = $btn.html();
    $btn.prop("disabled", true);
    $btn.text("Sending OTP").addClass('btn-primary').removeClass('btn-secondary');

    frappe.call({
        method: 'better_saas.better_saas.doctype.saas_user.saas_user.resend_otp',
        args: { "id": localStorage.getItem("reference") },
        type: 'POST',
        btn: $btn,
    }).always(function () {
        $('#otp').css('border-color', '#377DE2');
        $('#otp').next().text("OTP resent").css('color', '#377DE2').show();
        $btn.prop("disabled", false).html(btn_html);
        $btn.text("Resend OTP").removeClass('btn-primary').addClass('btn-secondary');
    });
}



function toggle_button(event) {
    let button = $(".get-started-button");
    button.prop("disabled", !event.target.checked);
    button.text(event.target.checked ? "Get OTP" : "Get Started");
}