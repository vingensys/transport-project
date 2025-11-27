from flask import request, redirect, url_for
from transport.models import db, LorryDetails
from . import admin_bp


def _redirect_lorry_tab():
    return redirect(url_for("admin.dashboard") + "#lorry")


@admin_bp.route("/lorry/add", methods=["POST"])
def add_lorry():
    """Add a new lorry."""
    capacity = (request.form.get("capacity") or "").strip()
    carrier_size = (request.form.get("carrier_size") or "").strip()
    number_of_wheels = request.form.get("number_of_wheels", type=int)
    remarks = (request.form.get("remarks") or "").strip()

    # Minimal validation
    if not capacity or not carrier_size or number_of_wheels is None:
        return _redirect_lorry_tab()

    l = LorryDetails(
        capacity=capacity,
        carrier_size=carrier_size,
        number_of_wheels=number_of_wheels,
        remarks=remarks or None,
    )
    db.session.add(l)
    db.session.commit()

    return _redirect_lorry_tab()

@admin_bp.route("/lorry/edit/<int:lorry_id>", methods=["POST"])
def edit_lorry(lorry_id: int):
    """Edit an existing lorry."""
    l = LorryDetails.query.get_or_404(lorry_id)

    capacity = (request.form.get("capacity") or "").strip()
    carrier_size = (request.form.get("carrier_size") or "").strip()
    number_of_wheels = request.form.get("number_of_wheels", type=int)
    remarks = (request.form.get("remarks") or "").strip()

    # Required fields
    if capacity:
        l.capacity = capacity

    if carrier_size:
        l.carrier_size = carrier_size

    if number_of_wheels is not None:
        l.number_of_wheels = number_of_wheels

    # Optional
    l.remarks = remarks or None

    db.session.commit()

    return redirect(url_for("admin.dashboard") + "#lorry")

@admin_bp.route("/lorry/delete/<int:lorry_id>", methods=["POST"])
def delete_lorry(lorry_id: int):
    """Delete a lorry (no dependency checks yet)."""
    l = LorryDetails.query.get_or_404(lorry_id)

    db.session.delete(l)
    db.session.commit()

    return redirect(url_for("admin.dashboard") + "#lorry")
