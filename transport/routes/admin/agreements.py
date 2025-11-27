from flask import request, redirect, url_for
from transport.models import db, Agreement, Company
from . import admin_bp


def _redirect_agreement_tab():
    return redirect(url_for("admin.dashboard") + "#agreement")


@admin_bp.route("/agreement/add", methods=["POST"])
def add_agreement():
    """Add a new agreement for a company."""
    company_id = request.form.get("company_id", type=int)
    loa_number = (request.form.get("loa_number") or "").strip()
    total_mt_km = request.form.get("total_mt_km", type=float)
    rate_per_mt_km = request.form.get("rate_per_mt_km", type=float)

    # Basic validation
    if not company_id or not loa_number or total_mt_km is None or rate_per_mt_km is None:
        return _redirect_agreement_tab()

    # Ensure company exists
    company = Company.query.get(company_id)
    if not company:
        return _redirect_agreement_tab()

    ag = Agreement(
        company_id=company_id,
        loa_number=loa_number,
        total_mt_km=total_mt_km,
        rate_per_mt_km=rate_per_mt_km,
        is_active=False,  # default
    )

    db.session.add(ag)
    db.session.commit()

    return _redirect_agreement_tab()

@admin_bp.route("/agreement/edit/<int:agreement_id>", methods=["POST"])
def edit_agreement(agreement_id: int):
    """Edit an existing agreement."""
    ag = Agreement.query.get_or_404(agreement_id)

    company_id = request.form.get("company_id", type=int)
    loa_number = (request.form.get("loa_number") or "").strip()
    total_mt_km = request.form.get("total_mt_km", type=float)
    rate_per_mt_km = request.form.get("rate_per_mt_km", type=float)

    # Update fields only if present
    if company_id:
        company = Company.query.get(company_id)
        if company:
            ag.company_id = company_id

    if loa_number:
        ag.loa_number = loa_number

    if total_mt_km is not None:
        ag.total_mt_km = total_mt_km

    if rate_per_mt_km is not None:
        ag.rate_per_mt_km = rate_per_mt_km

    db.session.commit()
    return redirect(url_for("admin.dashboard") + "#agreement")

@admin_bp.route("/agreement/activate/<int:agreement_id>", methods=["POST"])
def activate_agreement(agreement_id: int):
    """Make this the only active agreement globally."""
    ag = Agreement.query.get_or_404(agreement_id)

    # Deactivate ALL agreements
    db.session.query(Agreement).update({Agreement.is_active: False})

    # Activate this one
    ag.is_active = True

    db.session.commit()
    return redirect(url_for("admin.dashboard") + "#agreement")
