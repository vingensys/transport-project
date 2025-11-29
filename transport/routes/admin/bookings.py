from flask import request, redirect, url_for, flash
from datetime import date, datetime

from transport.models import (
    db,
    Booking,
    Route,
    Location,
    RouteStop,
    Agreement,
    LorryDetails,
    BookingAuthority,
)

from transport.route_utils import build_route_code_and_name
from . import admin_bp


def _redirect_to_tab(tab_hash: str):
    """Redirect back to a specific dashboard tab (e.g., '#booking')."""
    return redirect(url_for("admin.dashboard") + tab_hash)


@admin_bp.route("/booking/add", methods=["POST"])
def add_booking():
    # FROM and DESTINATION location codes from the form
    from_codes_raw = request.form.getlist("from_locations[]")
    dest_codes_raw = request.form.getlist("dest_locations[]")

    # Normalize: strip and uppercase
    def normalize(codes):
        return [c.strip().upper() for c in codes if c and c.strip()]

    from_codes = normalize(from_codes_raw)
    dest_codes = normalize(dest_codes_raw)

    errors = []

    # Need at least one FROM and one DEST location
    if not from_codes:
        errors.append("Add at least one FROM location.")
    if not dest_codes:
        errors.append("Add at least one DESTINATION location.")

    # Placement date: required and cannot be before booking date (today)
    placement_raw = (request.form.get("placement_date") or "").strip()
    placement_date = None
    today = date.today()

    if not placement_raw:
        errors.append("Placement date is required.")
    else:
        try:
            placement_date = datetime.strptime(placement_raw, "%Y-%m-%d").date()
            if placement_date < today:
                errors.append("Placement date cannot be earlier than the booking date.")
        except ValueError:
            errors.append("Invalid placement date.")

    # Trip KM and lorry_id
    trip_km = request.form.get("trip_km", type=int)
    lorry_id = request.form.get("lorry_id", type=int)

    if trip_km is None or trip_km <= 0:
        errors.append("Distance (KM) must be a positive integer.")
    if not lorry_id:
        errors.append("Select a lorry.")

    if errors:
        flash(" ".join(errors), "error")
        return _redirect_to_tab("#booking")

    # Lorry must exist
    lorry = LorryDetails.query.get(lorry_id)
    if not lorry:
        flash("Selected lorry does not exist.", "error")
        return _redirect_to_tab("#booking")

    # There must be an active agreement; that defines the company as well
    active_agreement = Agreement.query.filter_by(is_active=True).first()
    if not active_agreement:
        flash(
            "No active agreement found. Please activate an agreement before creating a booking.",
            "error",
        )
        return _redirect_to_tab("#agreement")

    # Build the full ordered sequence of location codes
    seq_codes = from_codes + dest_codes
    if len(seq_codes) < 2:
        flash("Route must contain at least two locations.", "error")
        return _redirect_to_tab("#booking")

    # Enforce that each location appears only once in this booking's route
    seen = set()
    duplicates = []
    for c in seq_codes:
        if c in seen and c not in duplicates:
            duplicates.append(c)
        seen.add(c)
    if duplicates:
        dup_str = ", ".join(duplicates)
        flash(
            f"Each location can appear only once in a booking route. Duplicates: {dup_str}.",
            "error",
        )
        return _redirect_to_tab("#booking")

    # Look up Location objects in order and ensure all exist
    locations = []
    missing_codes = []
    code_to_location = {}

    for code in seq_codes:
        if code in code_to_location:
            loc = code_to_location[code]
        else:
            loc = Location.query.filter_by(code=code).first()
            if not loc:
                missing_codes.append(code)
                continue
            code_to_location[code] = loc
        locations.append(loc)

    if missing_codes:
        human = ", ".join(sorted(set(missing_codes)))
        flash(f"Unknown location code(s): {human}.", "error")
        return _redirect_to_tab("#booking")

    # Validate authorities: at least one per FROM and DEST location
    missing_loading = []
    for code in from_codes:
        auth_ids = request.form.getlist(f"loading_{code}[]")
        if not auth_ids:
            missing_loading.append(code)

    missing_unloading = []
    for code in dest_codes:
        auth_ids = request.form.getlist(f"unloading_{code}[]")
        if not auth_ids:
            missing_unloading.append(code)

    if missing_loading or missing_unloading:
        msgs = []
        if missing_loading:
            msgs.append(
                "Select at least one loading authority for each FROM location "
                f"(missing for: {', '.join(sorted(set(missing_loading)))})."
            )
        if missing_unloading:
            msgs.append(
                "Select at least one unloading authority for each DESTINATION location "
                f"(missing for: {', '.join(sorted(set(missing_unloading)))})."
            )
        flash(" ".join(msgs), "error")
        return _redirect_to_tab("#booking")

    # Prepare inputs for route hashing/naming:
    #   first = first location code
    #   last  = last location code
    #   mids  = everything in between
    all_codes = [loc.code for loc in locations]
    first_code = all_codes[0]
    last_code = all_codes[-1]
    mid_codes = all_codes[1:-1]

    # Use shared helper to build a deterministic route code/name
    route_code, route_name = build_route_code_and_name(
        [first_code],
        mid_codes,
        [last_code],
        trip_km,
    )

    # Either fetch existing route or create a new one
    route = Route.query.filter_by(code=route_code).first()
    if route:
        # If an existing route with this pattern has a different distance, reject
        if route.total_km != trip_km:
            flash(
                f"Existing route {route.code} has total distance {route.total_km} KM, "
                f"but you entered {trip_km} KM. Please use the same distance or adjust the route.",
                "error",
            )
            return _redirect_to_tab("#booking")
    else:
        # Create the Route
        route = Route(
            code=route_code,
            name=route_name,
            total_km=trip_km,
        )
        db.session.add(route)
        db.session.flush()  # get route.id

        # Create RouteStops for this new route
        for idx, loc in enumerate(locations, start=1):
            stop = RouteStop(
                route_id=route.id,
                location_id=loc.id,
                sequence_index=idx,
                is_start_cluster=(idx == 1),
                is_end_cluster=(idx == len(locations)),
            )
            db.session.add(stop)

    # Finally, create the Booking header
    booking = Booking(
        agreement_id=active_agreement.id,
        company_id=active_agreement.company_id,
        lorry_id=lorry.id,
        route_id=route.id,
        trip_km=trip_km,
        placement_date=placement_date,
    )
    db.session.add(booking)
    db.session.flush()  # get booking.id

    # -------------------------------
    # Create BookingAuthority entries
    # -------------------------------

    # LOADING side (FROM cluster) - sequence by FROM location order
    loading_seq = 1
    for code in from_codes:
        auth_ids = request.form.getlist(f"loading_{code}[]")
        for aid in auth_ids:
            try:
                aid_int = int(aid)
            except (TypeError, ValueError):
                continue
            ba = BookingAuthority(
                booking_id=booking.id,
                authority_id=aid_int,
                role="LOADING",
                sequence_index=loading_seq,
            )
            db.session.add(ba)
            loading_seq += 1

    # UNLOADING side (DEST cluster) - sequence by DEST location order
    unloading_seq = 1
    for code in dest_codes:
        auth_ids = request.form.getlist(f"unloading_{code}[]")
        for aid in auth_ids:
            try:
                aid_int = int(aid)
            except (TypeError, ValueError):
                continue
            ba = BookingAuthority(
                booking_id=booking.id,
                authority_id=aid_int,
                role="UNLOADING",
                sequence_index=unloading_seq,
            )
            db.session.add(ba)
            unloading_seq += 1

    db.session.commit()
    flash("Booking saved successfully.", "success")
    return _redirect_to_tab("#booking")
