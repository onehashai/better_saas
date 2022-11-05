import frappe
def execute():
    saas_users = frappe.get_all("Saas User")
    for saas_user in saas_users:
        doc = frappe.get_doc("Saas User",saas_user.name)
        doc.password = doc.password
        doc.save()
        frappe.db.commit()
        pass