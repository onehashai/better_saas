let app_url="https://app.onehash.ai";
$(document).ready(function(){
    $("#submit").hide();
    $("#otp").hide();
    setTimeout(() => {
        $(".grecaptcha-badge").css({ 
            "visibility": "hidden"
        });    
    }, 250);
    
    function is_a_valid_subdomain(subdomain) {
        let MIN_LENGTH = 4;
        let MAX_LENGTH = 20;
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

    function validate_input(element,validation_method,arguments,error_message){

    }
    //Subdomain validation
    $(document).find('input[name="subdomain"]').on('input', function () {
            let subdomain = $(this).val();
            let element = this;
            if (subdomain.length === 0) {
                return;
            }
            let [is_valid, validation_msg] = is_a_valid_subdomain(subdomain);
            if (is_valid) {
                setTimeout(() => {
                    $.ajax({
                        "url":app_url+"/api/method/better_saas.better_saas.doctype.saas_user.saas_user.check_subdomain_avai",
                        "data":{
                            subdomain: subdomain
                        },
                        type: 'POST',
                        success: function (r) {
                            if (r.message.status === "True") {
                                element.setCustomValidity('');
                            } else {
                                element.setCustomValidity(subdomain+'.onehash.ai is not available');
                                element.reportValidity();
                            }
                        }
                    });    
                }, 250);
                
            } else {
                //set_availability_status('invalid', subdomain, validation_msg);
            }
        
    });

    //Email Validation
    $(document).find('input[name="email"]').on('change', function () {
        let email = $(this).val();
        let element  = this;
        if(!element.validity.typeMismatch) {
            $.ajax({
                url: app_url+"/api/method/better_saas.www.signup.email_exists",
                data:{"email":email},
                method: 'POST',
            }).done(function (r){
                if (r.message) {
                    let site = r.message;
                    element.setCustomValidity(`Email ${email} already in use, please login to https://${site}/login`);
                    element.reportValidity();
                }else{
                    element.setCustomValidity('');
                }
            });
        }
    });

    const phoneInputField = document.querySelector("#phone_number");
    if(typeof phoneInputField!=='undefined' && phoneInputField!=null){
        const phoneInput = window.intlTelInput(phoneInputField, {
            initialCountry: "auto",
            preferredCountries: ["US", "IN", "SG"],
            utilsScript: "https://cdnjs.cloudflare.com/ajax/libs/intl-tel-input/17.0.8/js/utils.js",
            geoIpLookup: function (callback) {
                $.get('https://ipinfo.io', function () { }, "jsonp").always(function (resp) {
                    let countryCode = (resp && resp.country) ? resp.country : "us";
                    callback(countryCode);
                });
            },
        });
        $(document).find('input[name="phone_number"]').on('change focus load', function () {
            if(typeof phoneInput!=='undefined'){
                const phoneNumber = phoneInput.getNumber();
                $(this).val(phoneNumber);
            }
        });
    }

    

    $(document).find('input[name="passphrase"]').on('change', function () {
        let element = this;
        $.ajax({
            "url":app_url+"/api/method/better_saas.better_saas.doctype.saas_user.saas_user.check_password_strength",
            "data": {
                passphrase: $('input[name="passphrase"]').val(),
                first_name: $('input[name="first_name"]').val(),
                last_name: $('input[name="last_name"]').val(),
                email: $('input[name="email"]').val()
            },
            success: function (r) {
                if (r.message) {
                    let feedback = r.message.feedback;
                    if (!feedback.password_policy_validation_passed) {
                        element.setCustomValidity('Plese enter strong password. '+(feedback.suggestions.length>0)?feedback.suggestions.join("\n"):"");
                        element.reportValidity();
                    }else{
                        element.setCustomValidity('');
                    }
                }
            }
        });
    });

    $(document).find('input[name="promocode"]').on('change', function () {
        let promocode = $(this).val();
        let element = this;
        if (promocode != '') {
            $.ajax({
                url:app_url+"/api/method/better_saas.better_saas.doctype.saas_user.saas_user.is_valid_promocode",
                data:{
                    "promocode": promocode,
                    "is_new_user":1
                }
            }).done(r => {
                if (!r.message || !r.message[0]) {
                    element.setCustomValidity(`Please enter a valid promocode.`);
                    element.reportValidity();
                } else {
                    element.setCustomValidity('');
                }
            });
        }
    });

    function setup_account_request($page) {
        // grecaptcha.ready(function () {
        //     grecaptcha.execute('6Lf6AeoaAAAAAASjFWeZlIS4zUpaa0jSxFAkjG2q', { action: 'submit' }).then(function (token) {
                // Add your logic to submit to your backend server here.
                if (!$page.find('input[name="first_name"]').val() ||
                    !$page.find('input[name="last_name"]').val() ||
                    !$page.find('input[name="subdomain"]').val() ||
                    !$page.find('input[name="email"]').val() ||
                    !$page.find('input[name="phone_number"]').val() ||
                    !$page.find('input[name="passphrase"]').val() || !$page.find('input[name="company_name"]').val()) {    
                    alert("All fields are necessary. Please try again.");
                    return false;
                } else if (!$page.find('input[name="email"]')[0].checkValidity()) {
                    $page.find('input[name="email"]')[0].reportValidity();
                    return false;
                } else if (!$page.find('input[name="passphrase"]')[0].checkValidity()) {
                    $page.find('input[name="passphrase"]')[0].reportValidity();
                    return false;
                } else if (!$page.find('input[name="phone_number"]')[0].checkValidity()) {
                    $page.find('input[name="phone_number"]')[0].reportValidity();
                    return false;    
                } else if (!$page.find('input[name="company_name"]')[0].checkValidity()) {
                    $page.find('input[name="phone_number"]')[0].reportValidity();
                    return false;
                } else {
                    var args = Array.from($page.find('#wf-form-Use-Cases-Form input'))
                        .reduce(
                            (acc, input) => {
                                acc[$(input).attr('name')] = $(input).val();
                                return acc;
                            }, {});
    
                    // Update Phone Number with Country Code 
                    //args.phone_number = localStorage.getItem('phoneNum');
                    console.log("Form Data",args)
                    
    
                    if ($("input[name*='checkbox']").prop("checked") === false) {
                        alert("Please agree to the Terms of Use and Privacy Policy.");
                        return;
                    }
    
                    // add plan to args
                    // var plan = frappe.utils.get_url_arg('plan');
                    // if (plan) args.plan = plan;
    
                    // var res = frappe.utils.get_url_arg('res');
                    // if (res) args.partner = res;
    
                    
                    var $btn = $page.find('#get-otp');
                    var btn_html = $btn.html();
                    $btn.prop("disabled", true).html("OTP Sent on email and mobile");
                    $page.find('input[name="otp"]').show();
                    
    
                    // // Lock Form Fields
                    // let inputArray = Array.from($page.find('.signup-card form input'));
                    // inputArray.pop();
                    // for (input in inputArray) {
                    //     console.log(inputArray[input]);
                    //     $(inputArray[input]).prop('readonly', true);
                    // }
                    // $("input[name*='agree-checkbox']").prop('disabled', true);
                    // $page.find('input[name="otp"]').prop('readonly',false);
                    // //goog_report_conversion(); // eslint-disable-line
    
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
                    $.ajax({
                        url:app_url+"/api/method/better_saas.better_saas.doctype.saas_user.saas_user.signup",
                        method: "POST",
                        data:args,
                        success:function (r) {
                            if (r.exc) return;
    
                            if (r.message) {
                                localStorage.setItem("reference", r.message.reference);
                                localStorage.setItem("email", r.message.email);
                                localStorage.setItem("mobile", r.message.mobile);
                                $('.verify-otp .email').text(r.message.email);
                                $('.mobile').text(r.message.mobile);
                                $page.find('input[name="otp"]').show();
                                $('#get-otp').text("Resend OTP").removeClass('btn-primary').addClass('btn-secondary');
                            }
                        }
                    });
                    return false;
                }
        //     });
        // });
    }

    $("#get-otp").on('click',()=>{
        let otptext = $('#get-otp').text(); 
        if ( otptext == "Get OTP") {
            setup_account_request($(document));
        } else if (otptext == "Resend OTP") {
            resend_otp($(document));
        }
    });
    // Verify OTP
    $(document).find('input[name="otp"]').on('keyup', () => {
        if ($(document).find('input[name="otp"]').val().length == 6) {
            let element = document.querySelector('input[name="otp"]');
            console.log(element);
            let args={};
            args['otp']=$('input[name="otp"]').val();
            args['id'] = localStorage.getItem("reference");
            
            setTimeout(() => {
                $.ajax({
                    url: app_url+"/api/method/better_saas.better_saas.doctype.saas_user.saas_user.verify_account_request",
                    data: args,
                    method: 'POST',
                    success: function (r) {
                        if (r.message == 'Invalid OTP') {
                            element.setCustomValidity(`Please enter valid OTP`);
                            element.reportValidity();
                            return false;
                        } else if (r.message == 'OTP Expired') {
                            element.setCustomValidity(`Your OTP has expired`);
                            element.reportValidity();
                            return false;
                        } else if (r.message == 'OTP Verified') {
                            element.setCustomValidity('');
                            element.reportValidity();
                            $('#get-otp').text("OTP Verified");
                            setTimeout(() => {
                                $('#get-otp').text("Creating Site...");
                                $("#wf-form-Use-Cases-Form").prop('disabled',true);
                                let is_dirty=false;
                                setTimeout(() => {
                                    $.ajax({
                                        url: app_url+"/api/method/better_saas.better_saas.doctype.saas_user.saas_user.setup",
                                        data: {
                                            account_request: localStorage.getItem("reference")
                                        },
                                        method: 'POST',
                                        success: function (r) {
                                            function get_status(){
                                                $.ajax({
                                                    url: app_url+"/api/method/better_saas.better_saas.doctype.saas_user.saas_user.get_status",
                                                    crossDomain: true,
                                                    data:{
                                                        account_request: localStorage.getItem("reference") || '',
                                                    },
                                                    method: 'POST',
                                                }).done(function (r){
                                                    redirect(r.message);
                                                });
                                            }
                                            setInterval(get_status, 5000);
                                        
                                            function redirect(data){
                                                if(data && data.status != "Wait"){
                                                    $('#wf-form-Use-Cases-Form').submit();
                                                    $("#get-otp").text("Site Created Successfully");
                                                    if(data.link && !is_dirty){
                                                        if(data.user && data.password){
                                                            is_dirty = true;
                                                            $.ajax({
                                                                method: "POST",
                                                                url: data.link,
                                                                data: {
                                                                    cmd: "login",
                                                                    usr: data.user,
                                                                    pwd: data.password,
                                                                    device: "desktop"
                                                                },
                                                                tryCount : 0,
                                                                retryLimit: 3,
                                                                crossDomain: true,
                                                                xhrFields: {
                                                                    withCredentials: true
                                                                },
                                                                dataType    : 'json',
                                                                success: function(res) {
                                                                    localStorage.removeItem("reference");
                                                                    localStorage.removeItem("email");
                                                                    localStorage.removeItem("mobile");
                                                                    window.open(data.link+'/app', "_self");
                                                                },
                                                                error : function(xhr, textStatus, errorThrown ) {
                                                                    if (textStatus == 'timeout' || textStatus == 'parsererror') {
                                                                        this.tryCount++;
                                                                        if (this.tryCount <= this.retryLimit) {
                                                                            //try again
                                                                            $.ajax(this);
                                                                            return;
                                                                        }                            
                                                                        return;
                                                                    }
                                                                }
                                                            });
                                                        }
                                                        else {
                                                            window.open(data.link, "_self")
                                                        }
                                                    } else if(typeof data.status!=='undefined' && data.status=="Failed"){
                                                        alert("Sorry, Your site cannot be created at the moment. You will get an Email once you site is ready.");
                                                        setInterval(window.close(), 5000);
                                                    } else {
                                                        window.open(data.link+'/app', "_self");
                                                    }
                                            }
                                        
                                            };
                                        }
                                    });
                                }, 500);
                            }, 500);
                        }
                    }
                });
            }, 250);
        }
    });

    $('#wf-form-Use-Cases-Form').submit(function() {
        // DO STUFF...
        let formdata = $(this).serialize();
        console.log(formdata);
        //return false; // return false to cancel form action
    });
    let param_string = window.location.href.split("?")[1];
    let current_href = $(document).find(".button-9").attr("href");
    let updated_url = current_href+(typeof param_string!=='undefined'?"?"+param_string:"");
    $(document).find(".button-9").attr("href",updated_url);
    setTimeout(() => {
        $(".grecaptcha-badge").css({ 
            "visibility": "hidden"
        });    
    }, 2000);
    

});