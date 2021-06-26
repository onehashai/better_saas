frappe.ready(function() {
    /*frappe.socketio.init('{{ socketio_port }}');
    frappe.realtime.off("setup_site");
    frappe.realtime.on("setup_site", (data) => {
        if(data.stage_status) {
            if (data.account_request == localStorage.getItem("reference")){
                update_setup_message(data.stage_status);
                set_setup_load_percent((data.progress[0])/data.progress[1] * 100);
                redirect(data);
            }
        }
    });
    */
    function update_setup_message(message){
        $('.setup-message').html(message)
    };

    function set_setup_load_percent(percent) {
        $('.progress-bar').css({"width": percent + "%"});
    };

    frappe.call({
        method: "better_saas.better_saas.doctype.saas_user.saas_user.setup",
        args: {
            account_request: localStorage.getItem("reference")
        }
    });

    // backup method in case socketio fails
    function get_status(){
        frappe.call({
            method: "better_saas.better_saas.doctype.saas_user.saas_user.get_status",
            args: {
                account_request: localStorage.getItem("reference") || '',
            },
            callback: function(r){
                redirect(r.message);
            }
        });
    }
    setInterval(get_status, 5000);

    function redirect(data){
        
        if(data && data.status != "Wait"){

            if(data.link && !frappe.flags.is_dirty){
                if(data.user && data.password){
                    clearTimeout(get_status);
                    frappe.flags.is_dirty = true;
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
                    })
                }
                else {
                    window.open(data.link, "_self")
                }
            } else if(typeof data.status!=='undefined' && data.status=="Failed"){
                msgprint("Sorry, Your site cannot be created at the moment. You will get an Email once you site is ready.", 'Site Creation Failed')
                setInterval(window.close(), 5000);
            } else {
                window.open(data.link+'/app', "_self");
            }

    }

    };
});


