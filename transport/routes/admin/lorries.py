from flask import request, redirect, url_for, flash
from transport.models import db, LorryDetails
from . import admin_bp


def _redirect_lorry_tab():
    return redirect(url_for("admin.dashboard") + "#lorry")


@admin_bp.route("/lorry/add", methods=["POST"])
def add_lorry():
    """Add a new lorry *type* (not a physical vehicle)."""
    capacity_raw = (request.form.get("capacity") or "").strip()
    carrier_size = (request.form.get("carrier_size") or "").strip()
    number_of_wheels = request.form.get("number_of_wheels", type=int)
    remarks = (request.form.get("remarks") or "").strip()

    errors = []

    # Capacity: required, must be positive integer
    capacity = None
    if not capacity_raw:
        errors.append("Capacity is required.")
    else:
        try:
            capacity = int(capacity_raw)
            if capacity <= 0:
                errors.append("Capacity must be a positive integer.")
        except ValueError:
            errors.append("Capacity must be a valid integer.")

    # Carrier size: required
    if not carrier_size:
        errors.append("Carrier size is required.")

    # Number of wheels: required positive integer
    if number_of_wheels is None:
        errors.append("Number of wheels is required.")
    elif number_of_wheels <= 0:
        errors.append("Number of wheels must be a positive integer.")

    # Check for duplicate lorry type (same capacity/carrier_size/wheels)
    if capacity is not None and carrier_size and number_of_wheels is not None:
        existing = (
            LorryDetails.query
            .filter_by(
                capacity=capacity,
                carrier_size=carrier_size,
                number_of_wheels=number_of_wheels,
            )
            .first()
        )
        if existing:
            errors.append("An identical lorry type already exists.")

    if errors:
        flash(" ".join(errors), "error")
        return _redirect_lorry_tab()

    l = LorryDetails(
        capacity=capacity,
        carrier_size=carrier_size,
        number_of_wheels=number_of_wheels,
        remarks=remarks or None,
    )
    db.session.add(l)
    db.session.commit()

    flash("Lorry type added successfully.", "success")
    return _redirect_lorry_tab()


@admin_bp.route("/lorry/edit/<int:lorry_id>", methods=["POST"])
def edit_lorry(lorry_id: int):
    """Edit an existing lorry *type*."""
    l = LorryDetails.query.get_or_404(lorry_id)

    capacity_raw = (request.form.get("capacity") or "").strip()
    carrier_size = (request.form.get("carrier_size") or "").strip()
    number_of_wheels = request.form.get("number_of_wheels", type=int)
    remarks = (request.form.get("remarks") or "").strip()

    errors = []

    # Capacity: required, must be positive integer
    capacity = None
    if not capacity_raw:
        errors.append("Capacity is required.")
    else:
        try:
            capacity = int(capacity_raw)
            if capacity <= 0:
                errors.append("Capacity must be a positive integer.")
        except ValueError:
            errors.append("Capacity must be a valid integer.")

    # Carrier size: required
    if not carrier_size:
        errors.append("Carrier size is required.")

    # Number of wheels: required positive integer
    if number_of_wheels is None:
        errors.append("Number of wheels is required.")
    elif number_of_wheels <= 0:
        errors.append("Number of wheels must be a positive integer.")

    # Check for duplicate lorry type on update
    if capacity is not None and carrier_size and number_of_wheels is not None:
        existing = (
            LorryDetails.query
            .filter(
                LorryDetails.id != l.id,
                LorryDetails.capacity == capacity,
                LorryDetails.carrier_size == carrier_size,
                LorryDetails.number_of_wheels == number_of_wheels,
            )
            .first()
        )
        if existing:
            errors.append(
                "Another lorry type with the same capacity, carrier size and wheels already exists."
            )

    if errors:
        flash(" ".join(errors), "error")
        return _redirect_lorry_tab()

    l.capacity = capacity
    l.carrier_size = carrier_size
    l.number_of_wheels = number_of_wheels
    l.remarks = remarks or None

    db.session.commit()
    flash("Lorry type updated successfully.", "success")
    return _redirect_lorry_tab()


@admin_bp.route("/lorry/delete/<int:lorry_id>", methods=["POST"])
def delete_lorry(lorry_id: int):
    """Delete a lorry type.

    Note: we don't yet enforce dependency checks here. If a lorry type is
    referenced by bookings in your database, you may want to prevent deletion
    or handle it explicitly later.
    """
    l = LorryDetails.query.get_or_404(lorry_id)

    db.session.delete(l)
    db.session.commit()

    flash("Lorry type deleted.", "success")
    return _redirect_lorry_tab()
