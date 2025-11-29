from flask import request, redirect, url_for, jsonify, flash
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
        inside = raw_location.split("[", 1)[1]
        location_code = inside.split("]", 1)[0]

    location_code = (location_code or "").strip().upper()

    errors = []

    # Required: location code and designation
    if not location_code:
        errors.append("Location code is required.")
    if not title:
        errors.append("Designation is required.")

    if errors:
        flash(" ".join(errors), "error")
        return _redirect_authority_tab()

    # Find location by code
    location = Location.query.filter_by(code=location_code).first()
    if not location:
        flash(f"Location code '{location_code}' does not exist.", "error")
        return _redirect_authority_tab()

    auth = Authority(
        location_id=location.id,
        authority_title=title,
        address=address or None,
    )
    db.session.add(auth)
    db.session.commit()

    flash("Authority added successfully.", "success")
    return _redirect_authority_tab()


@admin_bp.route("/authority/edit", methods=["POST"])
def edit_authority():
    """Edit an authority by ID."""
    auth_id = request.form.get("authority_id", type=int)
    title = (request.form.get("title") or "").strip()
    address = (request.form.get("address") or "").strip()

    if not auth_id:
        flash("Missing authority ID.", "error")
        return _redirect_authority_tab()

    auth = Authority.query.get(auth_id)
    if not auth:
        flash("Authority not found.", "error")
        return _redirect_authority_tab()

    # Required: designation on edit as well
    if not title:
        flash("Designation is required.", "error")
        return _redirect_authority_tab()

    auth.authority_title = title
    # allow clearing of address
    auth.address = address or None

    db.session.commit()
    flash("Authority updated successfully.", "success")
    return _redirect_authority_tab()


@admin_bp.route("/authority/quick_add", methods=["POST"])
def quick_add_authority():
    """AJAX endpoint: add an authority for a given location code and return JSON."""
    data = request.get_json(silent=True) or {}

    location_code = (data.get("location_code") or "").strip().upper()
    title = (data.get("title") or "").strip()
    address = (data.get("address") or "").strip() or None

    if not location_code or not title:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Location code and designation are required.",
                }
            ),
            400,
        )

    loc = Location.query.filter_by(code=location_code).first()
    if not loc:
        return (
            jsonify(
                {
                    "success": False,
                    "error": f"Unknown location code: {location_code}",
                }
            ),
            400,
        )

    auth = Authority(
        location_id=loc.id,
        authority_title=title,
        address=address,
    )
    db.session.add(auth)
    db.session.commit()

    return jsonify(
        {
            "success": True,
            "authority": {
                "id": auth.id,
                "title": auth.authority_title,
                "location_code": location_code,
            },
        }
    )
