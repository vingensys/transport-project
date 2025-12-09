from collections import defaultdict

from flask import render_template, request, redirect, url_for, flash

from . import admin_bp
from transport.models import (
    db,
    Company,
    Agreement,
    LorryDetails,
    Location,
    Authority,
    Route,
    Booking,
    AppConfig,
)


@admin_bp.route("/")
def dashboard():
    # Core master data for tabs
    companies = Company.query.order_by(Company.id.desc()).all()
    agreements = Agreement.query.order_by(Agreement.id.desc()).all()
    lorries = LorryDetails.query.order_by(LorryDetails.id.desc()).all()

    # ---------------------------------
    # Locations tab: paginated listing
    # ---------------------------------
    loc_page = request.args.get("loc_page", 1, type=int)
    LOC_PAGE_SIZE = 50

    locations_query = Location.query.order_by(Location.code)
    locations = locations_query.paginate(
        page=loc_page,
        per_page=LOC_PAGE_SIZE,
        error_out=False,
    )

    total_pages = locations.pages
    current_page = locations.page
    window = 4  # how many pages to show on each side of current

    start_page = max(1, current_page - window)
    end_page = min(total_pages, current_page + window)

    # ---------------------------------
    # Authorities + datalist locations
    # ---------------------------------
    authorities = Authority.query.order_by(Authority.id.desc()).all()
    all_locations = Location.query.order_by(Location.code).all()

    # Build a mapping: location code -> list of authorities at that location
    loc_code_by_id = {loc.id: loc.code for loc in all_locations}
    booking_auth_map = {}

    for auth in authorities:
        code = loc_code_by_id.get(auth.location_id)
        if not code:
            continue
        booking_auth_map.setdefault(code, []).append(
            {
                "id": auth.id,
                "title": auth.authority_title,
            }
        )

    # ---------------------------------
    # Routes
    # ---------------------------------
    routes = Route.query.order_by(Route.id.desc()).all()

    # ---------------------------------
    # Home depot config (if any)
    # ---------------------------------
    app_config = AppConfig.query.order_by(AppConfig.id.desc()).first()
    home_location = app_config.home_location if app_config else None
    home_authority = app_config.home_authority if app_config else None

    # ---------------------------------
    # Booking scope filter (active vs all)
    # ---------------------------------
    booking_scope = request.args.get("booking_scope", "active")
    if booking_scope not in ("active", "all"):
        booking_scope = "active"

    active_agreement = next(
        (a for a in agreements if getattr(a, "is_active", False)), None
    )

    bookings_query = Booking.query.order_by(Booking.id.desc())

    if booking_scope == "active":
        if active_agreement:
            bookings = bookings_query.filter_by(
                agreement_id=active_agreement.id
            ).all()
        else:
            # No active agreement; fall back to showing all bookings
            booking_scope = "all"
            bookings = bookings_query.all()
    else:
        bookings = bookings_query.all()

    # ---------------------------------
    # Booking history view model
    # ---------------------------------
    per_agreement_counter = defaultdict(int)
    booking_serials = {}

    # Order within agreement
    bookings_for_serial = sorted(
        bookings,
        key=lambda b: (b.agreement_id, b.booking_date or b.placement_date, b.id),
    )

    for b in bookings_for_serial:
        per_agreement_counter[b.agreement_id] += 1
        booking_serials[b.id] = per_agreement_counter[b.agreement_id]

    booking_rows = []

    for b in bookings:
        # All authorities in proper order
        loading_auths = [
            ba
            for ba in getattr(b, "booking_authorities", [])
            if ba.role == "LOADING"
        ]
        unloading_auths = [
            ba
            for ba in getattr(b, "booking_authorities", [])
            if ba.role == "UNLOADING"
        ]

        loading_auths.sort(key=lambda ba: ba.sequence_index or 0)
        unloading_auths.sort(key=lambda ba: ba.sequence_index or 0)

        def fmt_short(ba_list):
            out = []
            for ba in ba_list:
                auth = ba.authority
                if not auth:
                    continue
                loc = auth.location
                title = auth.authority_title or ""
                code = loc.code if loc else ""
                if code:
                    out.append(f"{title} @ {code}")
                else:
                    out.append(title)
            return ", ".join(out) if out else "-"

        def fmt_long(ba_list):
            out = []
            for ba in ba_list:
                auth = ba.authority
                if not auth:
                    continue
                loc = auth.location
                title = auth.authority_title or ""
                if loc:
                    out.append(f"{title} @ {loc.name} [{loc.code}]")
                else:
                    out.append(title)
            return ", ".join(out) if out else "-"

        booking_rows.append(
            {
                "booking": b,
                "trip_serial": booking_serials.get(b.id, 0),
                "from_display_short": fmt_short(loading_auths),
                "dest_display_short": fmt_short(unloading_auths),
                "from_display_long": fmt_long(loading_auths),
                "dest_display_long": fmt_long(unloading_auths),
            }
        )
    
    app_config = AppConfig.query.first()
    home_location = None
    home_authority = None
    if app_config:
        home_location = app_config.home_location
        home_authority = app_config.home_authority

    return render_template(
        "admin/dashboard.html",
        companies=companies,
        agreements=agreements,
        lorries=lorries,
        locations=locations,
        loc_page=current_page,
        loc_total_pages=total_pages,
        loc_start_page=start_page,
        loc_end_page=end_page,
        authorities=authorities,
        all_locations=all_locations,
        booking_auth_map=booking_auth_map,
        routes=routes,
        bookings=bookings,
        booking_rows=booking_rows,
        home_location=home_location,
        home_authority=home_authority,
        booking_scope=booking_scope,
        active_agreement=active_agreement,
        app_config=app_config,
    )

@admin_bp.route("/app-config/save", methods=["POST"])
def save_app_config():
    """Create or update the single AppConfig row."""
    # Home depot location input is like: "Erode Jn [ED]"
    raw_loc = (request.form.get("home_location_input") or "").strip()
    raw_auth = (request.form.get("home_authority_id") or "").strip()

    if not raw_loc:
        flash("Home depot location is required.", "error")
        return redirect(url_for("admin.dashboard") + "#config")

    # Try to extract station code from trailing [CODE]
    code = None
    if "[" in raw_loc and "]" in raw_loc:
        # pick the last [...] pair
        start = raw_loc.rfind("[")
        end = raw_loc.rfind("]")
        if start != -1 and end != -1 and end > start + 1:
            code = raw_loc[start + 1 : end].strip().upper()

    if not code:
        # fallback: last token
        parts = raw_loc.split()
        if parts:
            code = parts[-1].strip("[]").upper()

    if not code:
        flash("Could not determine station code from home depot input.", "error")
        return redirect(url_for("admin.dashboard") + "#config")

    home_location = Location.query.filter_by(code=code).first()
    if not home_location:
        flash(f"Unknown location code for home depot: {code}", "error")
        return redirect(url_for("admin.dashboard") + "#config")

    # Home authority is optional
    home_authority = None
    if raw_auth:
        try:
            auth_id = int(raw_auth)
            home_authority = Authority.query.get(auth_id)
            if not home_authority:
                flash("Selected home authority does not exist.", "error")
                return redirect(url_for("admin.dashboard") + "#config")
        except ValueError:
            flash("Invalid home authority selection.", "error")
            return redirect(url_for("admin.dashboard") + "#config")

    # There should be only one AppConfig row
    app_config = AppConfig.query.first()
    if not app_config:
        app_config = AppConfig()
        db.session.add(app_config)

    app_config.home_location_id = home_location.id
    app_config.home_authority_id = home_authority.id if home_authority else None

    db.session.commit()
    flash(
        f"Home depot set to {home_location.name} [{home_location.code}].",
        "success",
    )
    return redirect(url_for("admin.dashboard") + "#config")
