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


def _allocate_trip_amount_and_bands(
    trip_mt_km: float,
    cum_mt_km_before: float,
    total_mt_km: float,
    rate_per_mt_km: float,
):
    """
    Allocate a single trip's MT-Km across the 0–125–140–150% bands.

    Slabs:
      - 0 – 125% of total_mt_km   -> 100% of rate
      - 125 – 140% of total_mt_km -> 98% of rate
      - 140 – 150% of total_mt_km -> 96% of rate
      - > 150% of total_mt_km     -> not payable (blocked)

    Returns:
      (amount_for_trip, paid_mt_km, blocked_mt_km, cum_mt_km_after)
    """
    trip_mt_km = float(trip_mt_km or 0.0)
    cum = float(cum_mt_km_before or 0.0)
    T = float(total_mt_km or 0.0)
    R = float(rate_per_mt_km or 0.0)

    if trip_mt_km <= 0 or T <= 0 or R <= 0:
        blocked = max(trip_mt_km, 0.0)
        return 0.0, 0.0, blocked, cum + blocked

    # Band limits in absolute MT-Km
    limit_a = 1.25 * T  # 0–125% at 100%
    limit_b = 1.40 * T  # 125–140% at 98%
    limit_c = 1.50 * T  # 140–150% at 96%

    remaining = trip_mt_km
    amount = 0.0
    paid_mt_km = 0.0
    blocked_mt_km = 0.0

    def alloc_into_band(upper_limit: float, factor: float):
        nonlocal remaining, amount, paid_mt_km, cum
        if remaining <= 0 or upper_limit <= 0:
            return
        if cum >= upper_limit:
            return

        available = upper_limit - cum
        if available <= 0:
            return

        alloc = remaining if remaining <= available else available
        if alloc <= 0:
            return

        amount += alloc * R * factor
        paid_mt_km += alloc
        remaining -= alloc
        cum += alloc

    # Band A: up to 125% at 100%
    alloc_into_band(limit_a, 1.0)
    # Band B: 125–140% at 98%
    alloc_into_band(limit_b, 0.98)
    # Band C: 140–150% at 96%
    alloc_into_band(limit_c, 0.96)

    # Anything beyond 150% is blocked (not payable)
    if remaining > 0:
        blocked_mt_km = remaining
        cum += remaining
        remaining = 0.0

    return amount, paid_mt_km, blocked_mt_km, cum


def _compute_agreement_overview(agreement: Agreement):
    """
    Build overview summary + per-trip rows for the active agreement.

    Trip IDs here are based purely on Booking.id (ascending),
    and are consistent with the history tab.
    """
    if not agreement:
        return None, []

    total_mt_km = float(agreement.total_mt_km or 0.0)
    rate = float(agreement.rate_per_mt_km or 0.0)

    # All bookings for this agreement, ordered by immutable Booking.id
    bookings_q = (
        Booking.query.filter_by(agreement_id=agreement.id)
        .order_by(Booking.id.asc())
    )
    all_bookings = bookings_q.all()

    # Stable Trip ID per agreement = position in ID-ascending order
    serial_by_id: dict[int, int] = {}
    for idx, b_all in enumerate(all_bookings, start=1):
        serial_by_id[b_all.id] = idx

    # Ignore cancelled for utilisation & payments, but keep Trip ID from full set
    usable = [
        b for b in all_bookings
        if getattr(b, "status", "ACTIVE") != "CANCELLED"
    ]

    def trip_mt_km_of(b: Booking) -> float:
        km = float(b.trip_km or 0)
        cap = float(b.lorry.capacity) if getattr(b, "lorry", None) else 0.0
        return km * cap

    utilised_mt_km = sum(trip_mt_km_of(b) for b in usable)

    if total_mt_km > 0:
        utilisation_pct = (utilised_mt_km / total_mt_km) * 100.0
    else:
        utilisation_pct = 0.0

    rows = []
    amount_booked_total = 0.0
    blocked_total_mt_km = 0.0
    cum_mt_km_for_bands = 0.0

    # For display, go in Booking.id order for usable trips
    usable_sorted = sorted(usable, key=lambda b: b.id)

    for b in usable_sorted:
        trip_serial = serial_by_id.get(b.id, 0)
        trip_mt_km = trip_mt_km_of(b)

        amount_for_trip, paid_mt_km, blocked_mt_km, cum_mt_km_for_bands = (
            _allocate_trip_amount_and_bands(
                trip_mt_km,
                cum_mt_km_for_bands,
                total_mt_km,
                rate,
            )
        )

        amount_booked_total += amount_for_trip
        blocked_total_mt_km += blocked_mt_km

        # FROM / TO location codes (unique codes in sequence order)
        loading_auths = [
            ba for ba in getattr(b, "booking_authorities", [])
            if ba.role == "LOADING"
        ]
        unloading_auths = [
            ba for ba in getattr(b, "booking_authorities", [])
            if ba.role == "UNLOADING"
        ]
        loading_auths.sort(key=lambda ba: ba.sequence_index or 0)
        unloading_auths.sort(key=lambda ba: ba.sequence_index or 0)

        from_codes_list = []
        seen_from = set()
        for ba in loading_auths:
            auth = ba.authority
            loc = auth.location if auth else None
            code = loc.code if loc else None
            if code and code not in seen_from:
                from_codes_list.append(code)
                seen_from.add(code)

        to_codes_list = []
        seen_to = set()
        for ba in unloading_auths:
            auth = ba.authority
            loc = auth.location if auth else None
            code = loc.code if loc else None
            if code and code not in seen_to:
                to_codes_list.append(code)
                seen_to.add(code)

        from_codes = ", ".join(from_codes_list) if from_codes_list else "-"
        to_codes = ", ".join(to_codes_list) if to_codes_list else "-"

        rows.append(
            {
                "trip_serial": trip_serial,
                "booking": b,
                "booking_date": b.booking_date,
                "placement_date": b.placement_date,
                "from_codes": from_codes,
                "to_codes": to_codes,
                "route_km": b.trip_km,
                "lorry_capacity": getattr(b.lorry, "capacity", None),
                "trip_mt_km": trip_mt_km,
                "paid_mt_km": paid_mt_km,
                "blocked_mt_km": blocked_mt_km,
                "amount": amount_for_trip,
            }
        )

    agreement_amount = total_mt_km * rate

    summary = {
        # LOA number is the display identity
        "loa_number": agreement.loa_number,
        "agency_name": agreement.company.name if agreement.company else None,
        "total_mt_km": total_mt_km,
        "rate_per_mt_km": rate,
        "agreement_amount": agreement_amount,
        "utilised_mt_km": utilised_mt_km,
        "utilisation_pct": utilisation_pct,
        "amount_booked": amount_booked_total,
        "blocked_mt_km": blocked_total_mt_km,
    }

    return summary, rows


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
    # Home depot config (if any) – latest row
    # ---------------------------------
    app_config = AppConfig.query.order_by(AppConfig.id.desc()).first()
    home_location = app_config.home_location if app_config else None
    home_authority = app_config.home_authority if app_config else None
    home_location_id = home_location.id if home_location else None

    # ---------------------------------
    # Booking scope filter (active vs all)
    # ---------------------------------
    booking_scope = request.args.get("booking_scope", "active")
    if booking_scope not in ("active", "all"):
        booking_scope = "active"

    active_agreement = next(
        (a for a in agreements if getattr(a, "is_active", False)), None
    )

    # ---------------------------------
    # Build base sets for Trip ID and display
    # ---------------------------------
    # 1) serial_source_bookings: used ONLY to compute Trip IDs,
    #    and MUST include *all* bookings (including cancelled),
    #    ordered by immutable Booking.id per agreement.
    # 2) bookings: display set, later filtered by status/search.
    if booking_scope == "active" and active_agreement:
        # All bookings for active agreement for Trip ID calculation
        serial_source_bookings = (
            Booking.query
            .filter_by(agreement_id=active_agreement.id)
            .order_by(Booking.id.asc())
            .all()
        )
        # Display: same agreement, newest first
        bookings = (
            Booking.query
            .filter_by(agreement_id=active_agreement.id)
            .order_by(Booking.id.desc())
            .all()
        )
    else:
        # No active agreement or 'all' scope
        booking_scope = "all" if not active_agreement else booking_scope

        # Trip IDs for all agreements, per agreement, by Booking.id
        serial_source_bookings = (
            Booking.query
            .order_by(Booking.agreement_id.asc(), Booking.id.asc())
            .all()
        )
        # Display: all bookings, newest first
        bookings = Booking.query.order_by(Booking.id.desc()).all()

    # ---------------------------------
    # Booking status filter (all / active / cancelled)
    # ---------------------------------
    booking_status = request.args.get("booking_status", "all")
    if booking_status not in ("all", "active", "cancelled"):
        booking_status = "all"

    if booking_status == "active":
        # Treat anything not explicitly CANCELLED as active
        bookings = [
            b for b in bookings
            if getattr(b, "status", "ACTIVE") != "CANCELLED"
        ]
    elif booking_status == "cancelled":
        bookings = [
            b for b in bookings
            if getattr(b, "status", "ACTIVE") == "CANCELLED"
        ]

    # ---------------------------------
    # Booking search (Booking ID / Trip Serial)
    # (Will be applied after building booking_rows)
    # ---------------------------------
    booking_search = (request.args.get("booking_search") or "").strip()

    # ---------------------------------
    # Booking history view model
    # Trip ID must be stable: based on Booking.id per agreement,
    # using serial_source_bookings (unfiltered).
    # ---------------------------------
    per_agreement_counter = defaultdict(int)
    booking_serials: dict[int, int] = {}

    for b in serial_source_bookings:
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

        # --- INBOUND / OUTBOUND detection relative to home depot ---
        direction = None
        if home_location_id and b.route:
            stops = b.route.stops  # RouteStop objects
            start_stops = [s for s in stops if s.is_start_cluster]
            end_stops = [s for s in stops if s.is_end_cluster]

            home_in_start = any(s.location_id == home_location_id for s in start_stops)
            home_in_end = any(s.location_id == home_location_id for s in end_stops)

            if home_in_start and not home_in_end:
                direction = "OUTBOUND"
            elif home_in_end and not home_in_start:
                direction = "INBOUND"
            elif home_in_start and home_in_end:
                direction = "HOME"  # start & end at home cluster (loop)

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
                "direction": direction,
            }
        )

    # ---------------------------------
    # Apply search on booking_rows (by Booking ID / Trip Serial)
    # ---------------------------------
    if booking_search:
        s = booking_search.strip()

        def row_matches(row):
            b = row["booking"]
            trip_serial = row["trip_serial"]

            # Exact numeric match first
            if s.isdigit():
                try:
                    val = int(s)
                    if b.id == val or trip_serial == val:
                        return True
                except ValueError:
                    pass

            # Fallback: substring match
            return (
                s.lower() in str(b.id).lower()
                or s.lower() in str(trip_serial).lower()
            )

        booking_rows = [row for row in booking_rows if row_matches(row)]

    # ---------------------------------
    # Home config (older pattern preserved)
    # ---------------------------------
    app_config = AppConfig.query.first()
    home_location = None
    home_authority = None
    if app_config:
        home_location = app_config.home_location
        home_authority = app_config.home_authority

    # ---------------------------------
    # Agreement overview for active agreement (for Overview tab)
    # ---------------------------------
    overview_summary = None
    overview_rows = []

    if active_agreement:
        overview_summary, overview_rows = _compute_agreement_overview(active_agreement)

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
        booking_status=booking_status,
        booking_search=booking_search,
        active_agreement=active_agreement,
        app_config=app_config,
        overview_summary=overview_summary,
        overview_rows=overview_rows,
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
