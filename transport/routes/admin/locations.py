from flask import request, redirect, url_for
from transport.models import db, Location
from . import admin_bp


def _redirect_location_tab():
    return redirect(url_for("admin.dashboard") + "#location")


@admin_bp.route("/location/add", methods=["POST"])
def add_location():
    """Add a new location manually."""
    code = (request.form.get("code") or "").strip().upper()
    name = (request.form.get("name") or "").strip()
    address = (request.form.get("address") or "").strip()

    if not code or not name:
        return _redirect_location_tab()

    # Prevent duplicates by code
    existing = Location.query.filter_by(code=code).first()
    if existing:
        return _redirect_location_tab()

    loc = Location(
        code=code,
        name=name,
        address=address or None
    )

    db.session.add(loc)
    db.session.commit()

    return _redirect_location_tab()

@admin_bp.route("/location/edit", methods=["POST"])
def edit_location():
    """Edit an existing location by its code."""
    code = (request.form.get("code") or "").strip().upper()
    name = (request.form.get("name") or "").strip()
    address = (request.form.get("address") or "").strip()

    if not code:
        return _redirect_location_tab()

    loc = Location.query.filter_by(code=code).first()
    if not loc:
        # If not found, just go back silently for now
        return _redirect_location_tab()

    # Only update fields if provided
    if name:
        loc.name = name
    if address or address == "":
        # Allow clearing address if user submits empty
        loc.address = address or None

    db.session.commit()
    return _redirect_location_tab()
