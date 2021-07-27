// login.js
// don't remove this line (used in test)

window.disable_signup = {{ disable_signup and "true" or "false" }};

window.login = {};

window.verify = {};

login.bind_events = function () {
    $(window).on("hashchange", function () {
        var $btn = document.getElementsByClassName("btn btn-sm btn-primary btn-block btn-login")[0];
        $btn.disabled = true
        var $frgtbtn = document.getElementsByClassName("btn btn-sm btn-primary btn-block btn-forgot")[0];
        $frgtbtn.disabled = true
        login.route();
    });

    $('#login_email').on('change', function () {

        var paras = document.getElementById('domain_field');
        while(paras) {
            paras.parentNode.removeChild(paras);
            paras = document.getElementById('domain_field');
        };

        frappe.call('better_saas.www.better_saas_login.fetch_site_by_email', {
            'email': $("#login_email").val()
        }).then(r => {
            if (r.message) {
                login_fetch(r)
            }
        });
    });


    $('#forgot_email').on('change', function () {

        var paras = document.getElementById('domain_field');
        while(paras) {
            paras.parentNode.removeChild(paras);
            paras = document.getElementById('domain_field');
        };


        frappe.call('better_saas.www.better_saas_login.fetch_site_by_email', {
            'email': $("#forgot_email").val()
        }).then(r => {
            if (r.message) {
                forgot_fetch(r)               
            }
        });
    });
    // login here
    $(".form-login").on("submit", function (event) {
        event.preventDefault();
        var args = {};
        args.cmd = "login";
        args.usr = frappe.utils.xss_sanitise(($("#login_email").val() || "").trim());
        args.pwd = $("#login_password").val();
        args.device = "desktop";
        if (!args.usr || !args.pwd) {
            frappe.msgprint('{{ _("Both login and password required") }}');
            return false;
        }
        args.domain = $("#domain_field").val() || "";
        login.call(args);
        return false;
    });

    $(".form-signup").on("submit", function (event) {
        event.preventDefault();
        var args = {};
        args.cmd = "frappe.core.doctype.user.user.sign_up";
        args.email = ($("#signup_email").val() || "").trim();
        args.redirect_to = frappe.utils.sanitise_redirect(frappe.utils.get_url_arg("redirect-to"));
        args.full_name = frappe.utils.xss_sanitise(($("#signup_fullname").val() || "").trim());
        if (!args.email || !validate_email(args.email) || !args.full_name) {
            login.set_status('{{ _("Valid email and name required") }}', 'red');
            return false;
        }
        args.domain = ""
        login.call(args);
        return false;
    });

    $(".form-forgot").on("submit", function (event) {
        event.preventDefault();
        var args = {};
        args.cmd = "frappe.core.doctype.user.user.reset_password";
        args.user = ($("#forgot_email").val() || "").trim();
        if (!args.user) {
            login.set_status('{{ _("Valid Login id required.") }}', 'red');
            return false;
        }
        args.domain = $("#domain_field").val() || "";
        login.call(args);
        return false;
    });

    $(".toggle-password").click(function () {
        var input = $($(this).attr("toggle"));
        if (input.attr("type") == "password") {
            input.attr("type", "text");
            $(this).text('{{ _("Hide") }}')
        } else {
            input.attr("type", "password");
            $(this).text('{{ _("Show") }}')
        }
    });

    {% if ldap_settings and ldap_settings.enabled %}
    $(".btn-ldap-login").on("click", function () {
        var args = {};
        args.cmd = "{{ ldap_settings.method }}";
        args.usr = ($("#login_email").val() || "").trim();
        args.pwd = $("#login_password").val();
        args.device = "desktop";
        if (!args.usr || !args.pwd) {
            login.set_status('{{ _("Both login and password required") }}', 'red');
            return false;
        }
        login.call(args);
        return false;
    });
    {% endif %}
}


login.route = function () {
    var route = window.location.hash.slice(1);
    if (!route) route = "login";
    login[route]();
}

login.reset_sections = function (hide) {
    if (hide || hide === undefined) {
        $("section.for-login").toggle(false);
        $("section.for-email-login").toggle(false);
        $("section.for-forgot").toggle(false);
        $("section.for-signup").toggle(false);
    }
    $('section:not(.signup-disabled) .indicator').each(function () {
        $(this).removeClass().addClass('indicator').addClass('blue')
            .text($(this).attr('data-text'));
    });
}

login.login = function () {
    login.reset_sections();
    var paras = document.getElementById('domain_field');
    while(paras) {
        paras.parentNode.removeChild(paras);
        paras = document.getElementById('domain_field');
    };
    $(".for-login").toggle(true);

    if($("#login_email").val()){
        frappe.call('better_saas.www.better_saas_login.fetch_site_by_email', {
            'email': $("#login_email").val()
        }).then(r => {
            if (r.message) {
                login_fetch(r)   
                
            }
        });
    }
}

login.email = function () {
    login.reset_sections();
    var paras = document.getElementById('domain_field');
    while(paras) {
        paras.parentNode.removeChild(paras);
        paras = document.getElementById('domain_field');
    };
    $(".for-email-login").toggle(true);
    $("#login_email").focus();
}

login.steptwo = function () {
    login.reset_sections();
    $(".for-login").toggle(true);
    $("#login_email").focus();
}

login.forgot = function () {
    login.reset_sections();
    var paras = document.getElementById('domain_field');
    while(paras) {
        paras.parentNode.removeChild(paras);
        paras = document.getElementById('domain_field');
    };
    $(".for-forgot").toggle(true);
    $("#forgot_email").focus();

    if($("#forgot_email").val()){
    frappe.call('better_saas.www.better_saas_login.fetch_site_by_email', {
        'email': $("#forgot_email").val()
    }).then(r => {
        if (r.message) {
            forgot_fetch(r)            
        }
    });
    }
}

login.signup = function () {
    login.reset_sections();
    $(".for-signup").toggle(true);
    $("#signup_fullname").focus();
}


// Login
login.call = function (args, callback) {
    
    login.set_status('{{ _("Verifying...") }}', 'blue');
    if (args.domain != ""){
        document.url = "https://"+ args.domain
    }else{document.url = ""}

    $.ajax({
        method: "POST",
        url: document.url,
        dataType: "json",
        data: args,
        crossDomain: true,
        xhrFields: {
            withCredentials: true
        },
        callback: callback,
        freeze: true,
        statusCode: login.login_handlers
    });
}
login.set_status = function (message, color) {
    $('section:visible .btn-primary').text(message)
    if (color == "red") {
        $('section:visible .page-card-body').addClass("invalid");
    }
}

login.set_invalid = function (message) {
    $(".login-content.page-card").addClass('invalid-login');
    setTimeout(() => {
        $(".login-content.page-card").removeClass('invalid-login');
    }, 500)
    login.set_status(message, 'red');
    $("#login_password").focus();
}

login.login_handlers = (function () {
    var get_error_handler = function (default_message) {
        return function (xhr, data) {
            if (xhr.responseJSON) {
                data = xhr.responseJSON;            
            }
            var message = default_message;
            if (data._server_messages) {
                message = ($.map(JSON.parse(data._server_messages || '[]'), function (v) {
                    // temp fix for messages sent as dict
                    try {
                        return JSON.parse(v).message;
                    } catch (e) {
                        return v;
                    }
                }) || []).join('<br>') || default_message;
            }
            if (data.exc_type == "SiteExpiredError"){
                frappe.msgprint(message)
                login.set_invalid("Subscription Expired");
            }
            if (message === default_message) {
                login.set_invalid(message);
            } else {
                login.reset_sections(false);
            }

        };
    }

    var login_handlers = {
        200: function (data) {
            if (data.message == 'Logged In') {
                login.set_status('{{ _("Success") }}', 'green');
                window.location.href = document.url + (frappe.utils.sanitise_redirect(frappe.utils.get_url_arg("redirect-to")) || data.home_page);
            } else if (data.message == 'Password Reset') {
                window.location.replace = frappe.utils.sanitise_redirect(data.redirect_to);
            } else if (data.message == "No App") {
                login.set_status("{{ _('Success') }}", 'green');
                if (localStorage) {
                    var last_visited =
                        localStorage.getItem("last_visited")
                        || frappe.utils.sanitise_redirect(frappe.utils.get_url_arg("redirect-to"));
                    localStorage.removeItem("last_visited");
                }

                if (data.redirect_to) {
                    window.location.href = frappe.utils.sanitise_redirect(data.redirect_to);
                }

                if (last_visited && last_visited != "/login") {
                    window.location.href = last_visited;
                } else {
                    window.location.href = data.home_page;
                }
            } else if (window.location.hash === '#forgot') {
                if (data.message === 'not found') {
                    login.set_status('{{ _("Not a valid user") }}', 'red');
                } else if (data.message == 'not allowed') {
                    login.set_status('{{ _("Not Allowed") }}', 'red');
                } else if (data.message == 'disabled') {
                    login.set_status('{{ _("Not Allowed: Disabled User") }}', 'red');
                } else {
                    login.set_status('{{ _("Instructions Emailed") }}', 'green');
                }


            } else if (window.location.hash === '#signup') {
                if (cint(data.message[0]) == 0) {
                    login.set_status(data.message[1], 'red');
                } else {
                    login.set_status('{{ _("Success") }}', 'green');
                    frappe.msgprint(data.message[1])
                }
                //login.set_status(__(data.message), 'green');
            }

            //OTP verification
            if (data.verification && data.message != 'Logged In') {
                login.set_status('{{ _("Success") }}', 'green');

                document.cookie = "tmp_id=" + data.tmp_id;

                if (data.verification.method == 'OTP App') {
                    continue_otp_app(data.verification.setup, data.verification.qrcode);
                } else if (data.verification.method == 'SMS') {
                    continue_sms(data.verification.setup, data.verification.prompt);
                } else if (data.verification.method == 'Email') {
                    continue_email(data.verification.setup, data.verification.prompt);
                }
            }
        },
        401: get_error_handler('{{ _("Invalid Login. Try again.") }}'),
        417: get_error_handler('{{ _("Oops! Something went wrong") }}')
    };

    return login_handlers;
})();

frappe.ready(function () {
    login.bind_events();

    if (!window.location.hash) {
        window.location.hash = "#login";
    } else {
        $(window).trigger("hashchange");
    }

    $(".form-signup, .form-forgot").removeClass("hide");
    $(document).trigger('login_rendered');
});

var verify_token = function (event) {
    $(".form-verify").on("submit", function (eventx) {
        eventx.preventDefault();
        var args = {};
        args.cmd = "login";
        args.otp = $("#login_token").val();
        args.tmp_id = frappe.get_cookie('tmp_id');
        if (!args.otp) {
            frappe.msgprint('{{ _("Login token required") }}');
            return false;
        }
        login.call(args);
        return false;
    });
}

var request_otp = function (r) {
    $('.login-content').empty().append($('<div>').attr({ 'id': 'twofactor_div' }).html(
        '<form class="form-verify">\
			<div class="page-card-head">\
				<span class="indicator blue" data-text="Verification">{{ _("Verification") }}</span>\
			</div>\
			<div id="otp_div"></div>\
			<input type="text" id="login_token" autocomplete="off" class="form-control" placeholder={{ _("Verification Code") }} required="" autofocus="">\
			<button class="btn btn-sm btn-primary btn-block" id="verify_token">{{ _("Verify") }}</button>\
		</form>'));
    // add event handler for submit button
    verify_token();
}

var continue_otp_app = function (setup, qrcode) {
    request_otp();
    var qrcode_div = $('<div class="text-muted" style="padding-bottom: 15px;"></div>');

    if (setup) {
        direction = $('<div>').attr('id', 'qr_info').text('{{ _("Enter Code displayed in OTP App.") }}');
        qrcode_div.append(direction);
        $('#otp_div').prepend(qrcode_div);
    } else {
        direction = $('<div>').attr('id', 'qr_info').text('{{ _("OTP setup using OTP App was not completed. Please contact Administrator.") }}');
        qrcode_div.append(direction);
        $('#otp_div').prepend(qrcode_div);
    }
}

var continue_sms = function (setup, prompt) {
    request_otp();
    var sms_div = $('<div class="text-muted" style="padding-bottom: 15px;"></div>');

    if (setup) {
        sms_div.append(prompt)
        $('#otp_div').prepend(sms_div);
    } else {
        direction = $('<div>').attr('id', 'qr_info').text(prompt || '{{ _("SMS was not sent. Please contact Administrator.") }}');
        sms_div.append(direction);
        $('#otp_div').prepend(sms_div)
    }
}

var continue_email = function (setup, prompt) {
    request_otp();
    var email_div = $('<div class="text-muted" style="padding-bottom: 15px;"></div>');

    if (setup) {
        email_div.append(prompt)
        $('#otp_div').prepend(email_div);
    } else {
        var direction = $('<div>').attr('id', 'qr_info').text(prompt || '{{ _("Verification code email not sent. Please contact Administrator.") }}');
        email_div.append(direction);
        $('#otp_div').prepend(email_div);
    }
}

function login_fetch(r){

    if (r.message.length >= 1){
        let first_part = `
        <div class="form-group">
                <select id="domain_field"  style="border-radius: 5px;border: none;color: var(--text-color);font-size: var(--text-base);background-color: var(--control-bg);margin-bottom: 1rem;width: 100%;padding: 8px 5px 8px 5px;">`;
        let third_part = `
                </select>
        </div>`
        let second_part=""
        r.message.forEach(domain => {
            second_part += "<option value='"+domain+"'>"+domain+"</option>"
        });
        let total_html = first_part + second_part + third_part
        document.querySelectorAll('.page-card-body').forEach(elem=>{if(elem.parentNode.className == "form-signin form-login"){elem.insertAdjacentHTML('beforeend', total_html)}})
        if(r.message.length == 1){
            document.getElementById("domain_field").style.display = "none"
        }
        var $btn = document.getElementsByClassName("btn btn-sm btn-primary btn-block btn-login")[0];
        $btn.disabled = false;
        // $('#emailValidationMsg').html(``).show();

    }else{
        var $btn = document.getElementsByClassName("btn btn-sm btn-primary btn-block btn-login")[0];
        $btn.disabled = true;
        // $('#emailValidationMsg').html(`<span style=" color:#0E8C4A; font-size: 80%; font-weight: 400; margin-bottom: 0px;">Email not found</span>`).show();

    }
}

function forgot_fetch(r){

    if (r.message.length >= 1){
        let first_part = `
        <div class="form-frgt-control">
                <select id="domain_field"  style="border-radius: 5px;border: none;color: var(--text-color);font-size: var(--text-base);background-color: var(--control-bg);margin-bottom: 1rem;width: 100%;padding: 8px 5px 8px 5px;">`;
        let third_part = `
                </select>
        </div>`
        let second_part=""
        r.message.forEach(domain => {
            second_part += "<option value='"+domain+"'>"+domain+"</option>"
        });
        let total_html = first_part + second_part + third_part
        document.querySelectorAll('.page-card-body').forEach(elem=>{if(elem.parentNode.className == "form-signin form-forgot"){elem.insertAdjacentHTML('beforeend', total_html)}})
        if(r.message.length == 1){
            document.getElementById("domain_field").style.display = "none"
        }
        var $frgtbtn = document.getElementsByClassName("btn btn-sm btn-primary btn-block btn-forgot")[0];
        $frgtbtn.disabled = false
    }else{
        var $frgtbtn = document.getElementsByClassName("btn btn-sm btn-primary btn-block btn-forgot")[0];
        $frgtbtn.disabled = true;
    }
}