from flask import request, redirect, url_for, flash
from transport.models import db, Route, RouteStop, Location
from transport.route_utils import build_route_code_and_name
from . import admin_bp


def _redirect_route_tab():
    return redirect(url_for("admin.dashboard") + "#route")


@admin_bp.route("/route/add", methods=["POST"])
def add_route():
    """Add a new route using from/mid/to location lists."""

    # Lists of location codes from the form (hidden inputs)
    from_codes_raw = request.form.getlist("from_locations[]")
    mid_codes_raw = request.form.getlist("mid_locations[]")
    to_codes_raw = request.form.getlist("to_locations[]")

    total_km = request.form.get("total_km", type=int)
    remarks = (request.form.get("remarks") or "").strip()

    def normalize(codes):
        return [c.strip().upper() for c in codes if c and c.strip()]

    from_codes = normalize(from_codes_raw)
    mid_codes = normalize(mid_codes_raw)
    to_codes = normalize(to_codes_raw)

    errors = []

    # Need at least one origin and one destination, and a valid distance
    if not from_codes:
        errors.append("Add at least one FROM location.")
    if not to_codes:
        errors.append("Add at least one TO location.")
    if total_km is None or total_km <= 0:
        errors.append("Please enter a valid total distance (KM).")

    if errors:
        flash(" ".join(errors), "error")
        return _redirect_route_tab()

    # Full ordered sequence of codes for stops
    all_codes = from_codes + mid_codes + to_codes

    # Enforce that each location appears only once in the route
    seen = set()
    duplicates = []
    for c in all_codes:
        if c in seen and c not in duplicates:
            duplicates.append(c)
        seen.add(c)

    if duplicates:
        dup_str = ", ".join(duplicates)
        flash(
            f"Each location can appear only once in a route. Duplicates: {dup_str}.",
            "error",
        )
        return _redirect_route_tab()

    # Validate all locations exist before creating anything
    missing_codes = []
    code_to_location = {}

    for c in all_codes:
        if c in code_to_location:
            continue
        loc = Location.query.filter_by(code=c).first()
        if not loc:
            missing_codes.append(c)
        else:
            code_to_location[c] = loc

    if missing_codes:
        human = ", ".join(sorted(set(missing_codes)))
        flash(f"Unknown location code(s): {human}.", "error")
        return _redirect_route_tab()

    # Generate deterministic route code + name using shared helper
    code, name = build_route_code_and_name(from_codes, mid_codes, to_codes, total_km)

    # If a route with this exact pattern already exists, do not create a duplicate
    existing = Route.query.filter_by(code=code).first()
    if existing:
        flash(f"Route already exists with code {existing.code}.", "info")
        return _redirect_route_tab()

    # Create the Route
    route = Route(
        code=code,
        name=name,
        total_km=total_km,
        remarks=remarks or None,
    )
    db.session.add(route)
    db.session.flush()  # get route.id

    # Create RouteStops in order
    sequence_index = 1
    for c in all_codes:
        loc = code_to_location[c]

        stop = RouteStop(
            route_id=route.id,
            location_id=loc.id,
            sequence_index=sequence_index,
            is_start_cluster=(c in from_codes),
            is_end_cluster=(c in to_codes),
        )
        db.session.add(stop)
        sequence_index += 1

    db.session.commit()
    flash("Route saved successfully.", "success")
    return _redirect_route_tab()
