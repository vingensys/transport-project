from flask import request, redirect, url_for
from transport.models import db, Authority, Location
from . import admin_bp

def _redirect_authority_tab():
    return redirect(url_for("admin.dashboard") + "#authority")

@admin_bp.route("/authority/add", methods=["POST"])
def add_authority():
    """Add a new authority linked to a location."""
    raw_location = (request.form.get("location_code") or "").strip()
    title = (request.form.get("title") or "").strip()
    address = (request.form.get("address") or "").strip()

    # Extract code out of patterns like "Erode Jn [ED]" or just "ED"
    location_code = raw_location
    if "[" in raw_location and "]" in raw_location:
        # Take text inside the first [ ]
        inside = raw_location.split("[", 1)[1]
        location_code = inside.split("]", 1)[0]

    location_code = (location_code or "").strip().upper()

    if not location_code or not title:
        return _redirect_authority_tab()

    # Find location by code
    location = Location.query.filter_by(code=location_code).first()
    if not location:
        # location must exist (user must select an existing one)
        return _redirect_authority_tab()

    auth = Authority(
        location_id=location.id,
        authority_title=title,
        address=address or None,
    )
    db.session.add(auth)
    db.session.commit()

    return _redirect_authority_tab()

@admin_bp.route("/authority/edit", methods=["POST"])
def edit_authority():
    """Edit an authority by ID."""
    auth_id = request.form.get("authority_id", type=int)
    title = (request.form.get("title") or "").strip()
    address = (request.form.get("address") or "").strip()

    if not auth_id:
        return _redirect_authority_tab()

    auth = Authority.query.get(auth_id)
    if not auth:
        return _redirect_authority_tab()

    if title:
        auth.authority_title = title

    # allow clearing of address
    auth.address = address or None

    db.session.commit()
    return _redirect_authority_tab()
