from flask import request, redirect, url_for, flash
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

    # Server-side validation
    errors = []

    if not name:
        errors.append("Company name is required.")
    if not address:
        errors.append("Company address is required.")

    # Check for duplicate by name (case-insensitive)
    if name:
        existing = (
            Company.query
            .filter(db.func.lower(Company.name) == name.lower())
            .first()
        )
        if existing:
            errors.append("A company with this name already exists.")

    if errors:
        flash(" ".join(errors), "error")
        return _redirect_company_tab()

    c = Company(
        name=name,
        address=address,
        phone=phone or None,
        email=email or None,
    )
    db.session.add(c)
    db.session.commit()

    flash("Company added successfully.", "success")
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
    if name and name != c.name:
        # Optional duplicate check on rename
        existing = (
            Company.query
            .filter(db.func.lower(Company.name) == name.lower(), Company.id != c.id)
            .first()
        )
        if existing:
            flash("Another company with this name already exists.", "error")
            return _redirect_company_tab()
        c.name = name

    if address:
        c.address = address

    # Optional fields can be blanked out
    c.phone = phone or None
    c.email = email or None

    db.session.commit()
    flash("Company updated successfully.", "success")
    return _redirect_company_tab()
