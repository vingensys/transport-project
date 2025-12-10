from flask import request, redirect, url_for, flash
from transport.models import db, Agreement, Company
from . import admin_bp
from sqlalchemy import func


def _redirect_agreement_tab():
    return redirect(url_for("admin.dashboard") + "#agreement")


@admin_bp.route("/agreement/add", methods=["POST"])
def add_agreement():
    """Add a new agreement for a company."""
    company_id = request.form.get("company_id", type=int)
    loa_number = (request.form.get("loa_number") or "").strip()
    total_mt_km = request.form.get("total_mt_km", type=float)
    rate_per_mt_km = request.form.get("rate_per_mt_km", type=float)

    errors = []

    # Company required & must exist
    if not company_id:
        errors.append("Select a company.")
    else:
        company = Company.query.get(company_id)
        if not company:
            errors.append("Selected company does not exist.")

    # LOA number required
    if not loa_number:
        errors.append("LOA number is required.")

    # Validate total_mt_km
    if total_mt_km is None:
        errors.append("Total MT-KM is required.")
    elif total_mt_km <= 0:
        errors.append("Total MT-KM must be a positive number.")

    # Validate rate_per_mt_km
    if rate_per_mt_km is None:
        errors.append("Rate per MT-KM is required.")
    elif rate_per_mt_km <= 0:
        errors.append("Rate per MT-KM must be a positive value.")

    # Duplicate LOA check: same company + loa_number
    if company_id and loa_number:
        existing = (
            Agreement.query
            .filter(
                Agreement.company_id == company_id,
                func.lower(Agreement.loa_number) == loa_number.lower()
            )
            .first()
        )
        if existing:
            errors.append("An agreement with this LOA number already exists for this company.")

    if errors:
        flash(" ".join(errors), "error")
        return _redirect_agreement_tab()

    # Create Agreement
    ag = Agreement(
        company_id=company_id,
        loa_number=loa_number,
        total_mt_km=total_mt_km,
        rate_per_mt_km=rate_per_mt_km,
        is_active=False,  # always false until activated
    )

    db.session.add(ag)
    db.session.commit()

    flash("Agreement added successfully.", "success")
    return _redirect_agreement_tab()


@admin_bp.route("/agreement/edit/<int:agreement_id>", methods=["POST"])
def edit_agreement(agreement_id: int):
    """Edit an existing agreement."""
    ag = Agreement.query.get_or_404(agreement_id)

    company_id = request.form.get("company_id", type=int)
    loa_number = (request.form.get("loa_number") or "").strip()
    total_mt_km = request.form.get("total_mt_km", type=float)
    rate_per_mt_km = request.form.get("rate_per_mt_km", type=float)

    errors = []

    # Company update (optional but must exist)
    if company_id and company_id != ag.company_id:
        company = Company.query.get(company_id)
        if not company:
            errors.append("Selected company does not exist.")
        else:
            ag.company_id = company_id

    # LOA number update with duplicate check
    if loa_number and loa_number != ag.loa_number:
        existing = (
            Agreement.query
            .filter(
                Agreement.id != ag.id,
                Agreement.company_id == ag.company_id,
                func.lower(Agreement.loa_number) == loa_number.lower()
            )
            .first()
        )
        if existing:
            errors.append("Another agreement with this LOA number already exists for this company.")
        else:
            ag.loa_number = loa_number

    # MT-KM update
    if total_mt_km is not None:
        if total_mt_km <= 0:
            errors.append("Total MT-KM must be a positive number.")
        else:
            ag.total_mt_km = total_mt_km

    # Rate update
    if rate_per_mt_km is not None:
        if rate_per_mt_km <= 0:
            errors.append("Rate per MT-KM must be a positive value.")
        else:
            ag.rate_per_mt_km = rate_per_mt_km

    if errors:
        flash(" ".join(errors), "error")
        return _redirect_agreement_tab()

    db.session.commit()
    flash("Agreement updated successfully.", "success")
    return _redirect_agreement_tab()


@admin_bp.route("/agreement/activate/<int:agreement_id>", methods=["POST"])
def activate_agreement(agreement_id: int):
    """Make this the only active agreement globally."""
    ag = Agreement.query.get_or_404(agreement_id)

    # Deactivate ALL agreements
    db.session.query(Agreement).update({Agreement.is_active: False})

    # Activate this one
    ag.is_active = True
    db.session.commit()

    flash("Agreement activated.", "success")
    return _redirect_agreement_tab()
