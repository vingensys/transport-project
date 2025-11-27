from flask import request, redirect, url_for
from transport.models import db, Company
from . import admin_bp


def _redirect_company_tab():
    """Convenience redirect back to the Company tab."""
    return redirect(url_for("admin.dashboard") + "#company")


@admin_bp.route("/company/add", methods=["POST"])
def add_company():
    """Create a new company from the form on the Company tab."""
    name = (request.form.get("name") or "").strip()
    address = (request.form.get("address") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    email = (request.form.get("email") or "").strip()

    if not name or not address:
        return _redirect_company_tab()

    c = Company(name=name, address=address, phone=phone, email=email)
    db.session.add(c)
    db.session.commit()

    return _redirect_company_tab()


@admin_bp.route("/company/edit/<int:company_id>", methods=["POST"])
def edit_company(company_id: int):
    """Update an existing company via modal form."""
    c = Company.query.get_or_404(company_id)

    name = (request.form.get("name") or "").strip()
    address = (request.form.get("address") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    email = (request.form.get("email") or "").strip()

    # Only update required fields if non-empty
    if name:
        c.name = name
    if address:
        c.address = address

    # Optional fields can be blanked out
    c.phone = phone
    c.email = email

    db.session.commit()
    return _redirect_company_tab()
