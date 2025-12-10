from flask import request, redirect, url_for, flash, jsonify, render_template
from datetime import date, datetime

from transport.models import (
    db,
    Authority,
    Booking,
    Route,
    Location,
    RouteStop,
    Agreement,
    LorryDetails,
    BookingAuthority,
    BookingMaterial,
    BookingMaterialLine,
)

from transport.route_utils import build_route_code_and_name
from . import admin_bp


def _redirect_to_tab(tab_hash: str):
    """Redirect back to a specific dashboard tab (e.g., '#booking')."""
    return redirect(url_for("admin.dashboard") + tab_hash)


def _normalize_codes(codes):
    """Strip and uppercase location codes, dropping blanks."""
    return [c.strip().upper() for c in codes if c and c.strip()]


def _parse_materials_from_request():
    """
    Parse and validate materials from request.form.

    Returns a dict:
      {
        "mode": "ITEM" or "LUMPSUM",
        "total_quantity": float|None,
        "total_quantity_unit": str|None,
        "total_amount": float|None,
        "lines": [
          {"description": str, "unit": str|None,
           "quantity": float|None, "rate": float|None,
           "amount": float|None},
          ...
        ]
      }

    On validation error: flashes messages and returns None.
    """
    material_payload = None
    material_number_error = False

    material_mode_raw = (request.form.get("material_mode") or "").strip().upper()

    header_qty_str = (request.form.get("material_total_quantity") or "").strip()
    header_qty_unit = (request.form.get("material_total_quantity_unit") or "").strip()
    header_amount_str = (request.form.get("material_total_amount") or "").strip()

    header_qty = None
    header_amount = None

    # Parse header numbers (lenient: if blank → None)
    if header_qty_str:
        try:
            header_qty = float(header_qty_str)
        except ValueError:
            material_number_error = True

    if header_amount_str:
        try:
            header_amount = float(header_amount_str)
        except ValueError:
            material_number_error = True

    # Per-line fields
    line_descs = request.form.getlist("material_line_description[]")
    line_units = request.form.getlist("material_line_unit[]")
    line_qty_strs = request.form.getlist("material_line_quantity[]")
    line_rate_strs = request.form.getlist("material_line_rate[]")
    line_amount_strs = request.form.getlist("material_line_amount[]")

    lines_data = []
    max_len = (
        max(
            len(line_descs),
            len(line_units),
            len(line_qty_strs),
            len(line_rate_strs),
            len(line_amount_strs),
        )
        if (line_descs or line_units or line_qty_strs or line_rate_strs or line_amount_strs)
        else 0
    )

    for idx in range(max_len):
        desc = line_descs[idx] if idx < len(line_descs) else ""
        unit = line_units[idx].strip() if idx < len(line_units) else ""
        qty_str = line_qty_strs[idx].strip() if idx < len(line_qty_strs) else ""
        rate_str = line_rate_strs[idx].strip() if idx < len(line_rate_strs) else ""
        amount_str = line_amount_strs[idx].strip() if idx < len(line_amount_strs) else ""

        # Entirely empty row → skip
        if not (desc or unit or qty_str or rate_str or amount_str):
            continue

        # Description is mandatory for any non-empty row
        if not desc:
            flash(
                "Each material row must have a description if any other field is filled.",
                "error",
            )
            return None

        qty = None
        rate = None
        amount = None

        if qty_str:
            try:
                qty = float(qty_str)
            except ValueError:
                material_number_error = True

        if rate_str:
            try:
                rate = float(rate_str)
            except ValueError:
                material_number_error = True

        if amount_str:
            try:
                amount = float(amount_str)
            except ValueError:
                material_number_error = True

        lines_data.append(
            {
                "description": desc,
                "unit": unit or None,
                "quantity": qty,
                "rate": rate,
                "amount": amount,
            }
        )

    if material_number_error:
        flash(
            "Invalid number in materials section. Please check quantity, rate and amount fields.",
            "error",
        )
        return None

    has_header_values = bool(
        header_qty is not None or header_amount is not None or header_qty_unit
    )
    has_lines = bool(lines_data)

    # From now on, *every* booking must include some materials.
    # 1) Mode must be chosen
    if not material_mode_raw:
        flash(
            "Each booking must include a material list. "
            "Choose ITEM or LUMPSUM and enter at least one material.",
            "error",
        )
        return None

    # 2) Mode must be valid
    if material_mode_raw not in ("ITEM", "LUMPSUM"):
        flash("Material mode must be either ITEM or LUMPSUM.", "error")
        return None

    # 3) Per-mode minimum content
    if material_mode_raw == "ITEM":
        # ITEM mode requires at least one line
        if not has_lines:
            flash(
                "In ITEM mode, enter at least one material line.",
                "error",
            )
            return None
    elif material_mode_raw == "LUMPSUM":
        # LUMPSUM mode requires either header qty/amount OR at least one line
        if not has_header_values and not has_lines:
            flash(
                "In LUMPSUM mode, enter a header quantity/amount or at least one material line.",
                "error",
            )
            return None

    # LUMPSUM-specific validation: header total quantity vs per-line quantities
    if material_mode_raw == "LUMPSUM" and (has_header_values or has_lines):
        has_header_qty = header_qty is not None
        has_line_qty = any(line["quantity"] is not None for line in lines_data)
        if has_header_qty and has_line_qty:
            flash(
                "In LUMPSUM mode, use either the header total quantity or per-line quantities, not both.",
                "error",
            )
            return None

    # Build payload according to mode
    if material_mode_raw and (has_header_values or has_lines):
        if material_mode_raw == "ITEM":
            # ITEM mode: header quantity/unit ignored, total_amount from line amounts
            total_amt = sum(
                (line["amount"] or 0.0)
                for line in lines_data
                if line["amount"] is not None
            )
            header_qty = None
            header_qty_unit = ""
            header_amount = total_amt if lines_data else None

        material_payload = {
            "mode": material_mode_raw,
            "total_quantity": header_qty,
            "total_quantity_unit": header_qty_unit or None,
            "total_amount": header_amount,
            "lines": lines_data,
        }
    else:
        material_payload = None

    return material_payload


def _create_booking_core(
    from_codes,
    dest_codes,
    trip_km: int,
    placement_date: date,
    booking_date: date,
    lorry_id: int,
    material_payload: dict | None,
    remarks_prefix: str | None = None,
):
    """
    Shared core logic for creating a Booking (normal or backdated).

    On error: flashes messages and returns None.
    On success: commits and returns the Booking instance.
    """
    # Lorry must exist
    lorry = LorryDetails.query.get(lorry_id)
    if not lorry:
        flash("Selected lorry does not exist.", "error")
        return None

    # There must be an active agreement; that defines the company as well
    active_agreement = Agreement.query.filter_by(is_active=True).first()
    if not active_agreement:
        flash(
            "No active agreement found. Please activate an agreement before creating a booking.",
            "error",
        )
        return None

    # ------------------------------------------------------------------
    # ROUTE / LOCATIONS (shared logic)
    # ------------------------------------------------------------------
    seq_codes = from_codes + dest_codes
    if len(seq_codes) < 2:
        flash("Route must contain at least two locations.", "error")
        return None

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
        return None

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
        return None

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
        return None

    # Prepare inputs for route hashing/naming:
    all_codes = [loc.code for loc in locations]
    first_code = all_codes[0]
    last_code = all_codes[-1]
    mid_codes = all_codes[1:-1]

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
            return None
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

    # -------------------------------
    # Create the Booking header
    # -------------------------------
    remarks_value = remarks_prefix if remarks_prefix else None

    booking = Booking(
        agreement_id=active_agreement.id,
        company_id=active_agreement.company_id,
        lorry_id=lorry.id,
        route_id=route.id,
        trip_km=trip_km,
        placement_date=placement_date,
        booking_date=booking_date,
        remarks=remarks_value,
    )
    db.session.add(booking)
    db.session.flush()  # get booking.id

    # -------------------------------
    # Create BookingAuthority entries
    # -------------------------------
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

    # -------------------------------
    # MATERIALS: create ORM entities
    # -------------------------------
    if material_payload:
        material = BookingMaterial(
            booking_id=booking.id,
            mode=material_payload["mode"],
            total_quantity=material_payload["total_quantity"],
            total_quantity_unit=material_payload["total_quantity_unit"],
            total_amount=material_payload["total_amount"],
        )

        # Attach lines
        for idx, line_data in enumerate(material_payload["lines"], start=1):
            line = BookingMaterialLine(
                booking_material_id=material.id if material.id is not None else None,
                sequence_index=idx,
                description=line_data["description"],
                unit=line_data["unit"],
                quantity=line_data["quantity"],
                rate=line_data["rate"],
                amount=line_data["amount"],
            )
            material.lines.append(line)

        # For ITEM mode, derive header total_amount from line amounts
        if material.mode == "ITEM":
            total_amt = sum(
                (l.amount or 0.0) for l in material.lines if l.amount is not None
            )
            material.total_amount = total_amt if material.lines else None

        booking.material_table = material
        db.session.add(material)

    db.session.commit()
    return booking


@admin_bp.route("/booking/add", methods=["POST"])
def add_booking():
    # FROM and DESTINATION location codes from the form
    from_codes_raw = request.form.getlist("from_locations[]")
    dest_codes_raw = request.form.getlist("dest_locations[]")

    from_codes = _normalize_codes(from_codes_raw)
    dest_codes = _normalize_codes(dest_codes_raw)

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

    # MATERIALS via shared helper
    material_payload = _parse_materials_from_request()
    if material_payload is None:
        return _redirect_to_tab("#booking")

    # booking_date for normal flow is "today"
    booking_date = today

    booking = _create_booking_core(
        from_codes=from_codes,
        dest_codes=dest_codes,
        trip_km=trip_km,
        placement_date=placement_date,
        booking_date=booking_date,
        lorry_id=lorry_id,
        material_payload=material_payload,
        remarks_prefix=None,
    )

    if booking is None:
        return _redirect_to_tab("#booking")

    flash("Booking saved successfully.", "success")
    return _redirect_to_tab("#booking")


@admin_bp.route("/booking/backdated", methods=["GET"])
def backdated_booking_view():
    """
    Show the Backdated Booking entry form.
    Uses the same data structures as the main booking tab.
    """
    # Lorry list
    lorries = LorryDetails.query.order_by(LorryDetails.capacity).all()

    # All known locations (for datalist autocomplete)
    all_locations = Location.query.order_by(Location.name).all()

    # Build authority lookup map: { "CODE": [ {id, title, address}, ... ] }
    from transport.models import Authority   # import only if not already imported

    booking_auth_map = {}
    authorities = Authority.query.all()

    for auth in authorities:
        code = auth.location.code
        if code not in booking_auth_map:
            booking_auth_map[code] = []
        booking_auth_map[code].append(
            {
                "id": auth.id,
                "title": auth.authority_title,
                "address": auth.address,
            }
        )

    # Sort inside each location for cleaner UI
    for code in booking_auth_map:
        booking_auth_map[code].sort(key=lambda x: x["title"].lower())

    return render_template(
        "admin/backdated_booking.html",
        lorries=lorries,
        all_locations=all_locations,
        booking_auth_map=booking_auth_map,
    )


@admin_bp.route("/booking/backdated-add", methods=["POST"])
def add_backdated_booking():
    """
    Create a backdated booking.

    This route is intentionally separate from add_booking() so that
    post-facto entries feel non-routine ("procedure is the punishment").

    Rules:
      - booking_date <= placement_date <= today
      - reason for backdating required
      - All other invariants (materials, route, authorities, lorry, etc.)
        are handled by _create_booking_core().
    """
    from_codes_raw = request.form.getlist("from_locations[]")
    dest_codes_raw = request.form.getlist("dest_locations[]")

    from_codes = _normalize_codes(from_codes_raw)
    dest_codes = _normalize_codes(dest_codes_raw)

    errors = []

    if not from_codes:
        errors.append("Add at least one FROM location.")
    if not dest_codes:
        errors.append("Add at least one DESTINATION location.")

    today = date.today()

    booking_raw = (request.form.get("booking_date") or "").strip()
    placement_raw = (request.form.get("placement_date") or "").strip()
    reason = (request.form.get("backdated_reason") or "").strip()

    booking_date = None
    placement_date = None

    if not booking_raw:
        errors.append("Booking date is required for backdated entries.")
    else:
        try:
            booking_date = datetime.strptime(booking_raw, "%Y-%m-%d").date()
        except ValueError:
            errors.append("Invalid booking date.")

    if not placement_raw:
        errors.append("Placement date is required.")
    else:
        try:
            placement_date = datetime.strptime(placement_raw, "%Y-%m-%d").date()
        except ValueError:
            errors.append("Invalid placement date.")

    if booking_date and booking_date > today:
        errors.append("Booking date cannot be in the future.")
    if placement_date and placement_date > today:
        errors.append("Placement date cannot be in the future.")
    if booking_date and placement_date and placement_date < booking_date:
        errors.append("Placement date cannot be earlier than the booking date.")

    if not reason:
        errors.append("Reason for backdated booking is required.")

    trip_km = request.form.get("trip_km", type=int)
    lorry_id = request.form.get("lorry_id", type=int)

    if trip_km is None or trip_km <= 0:
        errors.append("Distance (KM) must be a positive integer.")
    if not lorry_id:
        errors.append("Select a lorry.")

    if errors:
        flash(" ".join(errors), "error")
        return _redirect_to_tab("#booking")

    # MATERIALS via shared helper
    material_payload = _parse_materials_from_request()
    if material_payload is None:
        return _redirect_to_tab("#booking")

    remarks_prefix = f"[BACKDATED] {reason}"

    booking = _create_booking_core(
        from_codes=from_codes,
        dest_codes=dest_codes,
        trip_km=trip_km,
        placement_date=placement_date,
        booking_date=booking_date,
        lorry_id=lorry_id,
        material_payload=material_payload,
        remarks_prefix=remarks_prefix,
    )

    if booking is None:
        return _redirect_to_tab("#booking")

    flash("Backdated booking recorded successfully.", "success")
    return _redirect_to_tab("#booking")


@admin_bp.route("/booking/<int:booking_id>/materials-json", methods=["GET"])
def booking_materials_json(booking_id: int):
    booking = Booking.query.get_or_404(booking_id)

    material = getattr(booking, "material_table", None)
    if material is None:
        return jsonify(
            {
                "success": True,
                "has_materials": False,
                "mode": None,
                "header": None,
                "lines": [],
            }
        )

    lines_payload = []
    for line in material.lines:
        lines_payload.append(
            {
                "sequence_index": line.sequence_index,
                "description": line.description,
                "unit": line.unit,
                "quantity": line.quantity,
                "rate": line.rate,
                "amount": line.amount,
            }
        )

    header_payload = {
        "total_quantity": material.total_quantity,
        "total_quantity_unit": material.total_quantity_unit,
        "total_amount": material.total_amount,
    }

    return jsonify(
        {
            "success": True,
            "has_materials": True,
            "mode": material.mode,
            "header": header_payload,
            "lines": lines_payload,
        }
    )


@admin_bp.route("/booking/<int:booking_id>/cancel", methods=["POST"])
def cancel_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    # Read redirect tab + optional history filters
    redirect_tab = request.form.get("redirect_tab") or "#booking"
    booking_scope = (request.form.get("booking_scope") or "").strip()
    booking_status = (request.form.get("booking_status") or "").strip()
    booking_search = (request.form.get("booking_search") or "").strip()

    def _redirect_after_cancel():
        # When cancelling from History tab, preserve filters
        if redirect_tab == "#history":
            params = {}
            if booking_scope:
                params["booking_scope"] = booking_scope
            if booking_status:
                params["booking_status"] = booking_status
            if booking_search:
                params["booking_search"] = booking_search
            return redirect(url_for("admin.dashboard", **params) + redirect_tab)
        # Fallback: original behaviour
        return _redirect_to_tab(redirect_tab)

    if booking.status == "CANCELLED":
        flash("Booking already cancelled.", "info")
        return _redirect_after_cancel()

    reason = (request.form.get("cancel_reason") or "").strip() or None

    booking.status = "CANCELLED"
    booking.cancelled_at = datetime.utcnow()
    booking.cancel_reason = reason

    db.session.commit()
    flash(f"Booking {booking.id} cancelled.", "success")

    return _redirect_after_cancel()


@admin_bp.route("/booking/<int:booking_id>", methods=["GET", "POST"])
def booking_detail(booking_id):
    """View / edit a booking (safe fields only: placement_date, lorry)."""
    booking = Booking.query.get_or_404(booking_id)

    def _redirect_self_with_filters():
        """Redirect back to this detail view, preserving any history filters in the query string."""
        params = {
            "booking_id": booking.id,
            "booking_scope": request.args.get("booking_scope"),
            "booking_status": request.args.get("booking_status"),
            "booking_search": request.args.get("booking_search"),
        }
        params = {k: v for k, v in params.items() if v}
        return redirect(url_for("admin.booking_detail", **params))

    # Disallow edits on cancelled bookings
    if booking.status == "CANCELLED" and request.method == "POST":
        flash("Cancelled bookings cannot be edited.", "error")
        return _redirect_self_with_filters()

    # We'll let the user change placement_date + lorry_id only
    # Everything else is read-only for audit reasons.
    lorries = LorryDetails.query.order_by(LorryDetails.capacity).all()

    if request.method == "POST":
        errors: list[str] = []

        # Placement date: required, cannot be before booking_date
        placement_raw = (request.form.get("placement_date") or "").strip()
        placement_date = None
        if not placement_raw:
            errors.append("Placement date is required.")
        else:
            try:
                placement_date = datetime.strptime(placement_raw, "%Y-%m-%d").date()
                # booking.booking_date is already set when created
                if placement_date < booking.booking_date:
                    errors.append(
                        "Placement date cannot be earlier than the booking date."
                    )
            except ValueError:
                errors.append("Invalid placement date.")

        # Lorry: must exist
        lorry_id = request.form.get("lorry_id", type=int)
        lorry = None
        if not lorry_id:
            errors.append("Select a lorry.")
        else:
            lorry = LorryDetails.query.get(lorry_id)
            if not lorry:
                errors.append("Selected lorry does not exist.")

        if errors:
            for msg in errors:
                flash(msg, "error")
        else:
            booking.placement_date = placement_date
            booking.lorry_id = lorry.id
            db.session.commit()
            flash("Booking updated successfully.", "success")
            return _redirect_self_with_filters()

    siblings = (
        Booking.query.filter_by(agreement_id=booking.agreement_id)
        .order_by(Booking.id.asc())
        .all()
    )

    trip_serial = None
    for idx, b in enumerate(siblings, start=1):
        if b.id == booking.id:
            trip_serial = idx
            break

    # Materials (read-only)
    material = getattr(booking, "material_table", None)

    return render_template(
        "admin/booking_detail.html",
        booking=booking,
        material=material,
        lorries=lorries,
        trip_serial=trip_serial,
    )


@admin_bp.route("/booking/<int:booking_id>/materials-edit", methods=["POST"])
def booking_materials_edit(booking_id: int):
    """Create or update the material table for an existing booking."""
    booking = Booking.query.get_or_404(booking_id)

    # Disallow edits on cancelled bookings
    if booking.status == "CANCELLED":
        flash("Cancelled bookings cannot be edited.", "error")
        return redirect(url_for("admin.booking_detail", booking_id=booking.id))

    # Mode: "", ITEM, or LUMPSUM
    mode = (request.form.get("material_mode") or "").strip().upper()

    # From now on, a booking must always have a material list.
    # So an empty mode is not allowed here.
    if not mode:
        flash(
            "Each booking must include a material list. "
            "Choose ITEM or LUMPSUM and enter at least one material.",
            "error",
        )
        return redirect(url_for("admin.booking_detail", booking_id=booking.id))

    if mode not in ("ITEM", "LUMPSUM"):
        flash("Invalid material mode.", "error")
        return redirect(url_for("admin.booking_detail", booking_id=booking.id))

    # Get or create BookingMaterial header (1:1 with Booking)
    material = getattr(booking, "material_table", None)
    if not material:
        material = BookingMaterial(booking_id=booking.id)
        db.session.add(material)

    material.mode = mode

    def parse_float(form_name: str):
        raw = request.form.get(form_name)
        if raw is None:
            return None
        raw = raw.strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            return None

    # Header totals
    if mode == "LUMPSUM":
        material.total_quantity = parse_float("material_total_quantity")
        total_unit_raw = (request.form.get("material_total_quantity_unit") or "").strip()
        material.total_quantity_unit = total_unit_raw or None
    else:
        # In ITEM mode we do not persist a header quantity
        material.total_quantity = None
        material.total_quantity_unit = None

    material.total_amount = parse_float("material_total_amount")

    # --- Rebuild lines from form data ---
    desc_list = request.form.getlist("line_description[]")
    unit_list = request.form.getlist("line_unit[]")
    qty_list = request.form.getlist("line_quantity[]")
    rate_list = request.form.getlist("line_rate[]")
    amt_list = request.form.getlist("line_amount[]")

    # Clear existing lines; relationship should be configured with delete-orphan
    material.lines.clear()

    has_line_qty = False      # track per-line quantity usage (for LUMPSUM invariant)
    has_any_line = False      # track if we have at least one logical line

    def list_float(values, idx):
        if idx >= len(values):
            return None
        raw = (values[idx] or "").strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            return None

    seq = 1
    for i, desc in enumerate(desc_list):
        desc = (desc or "").strip()
        if not desc:
            # Entirely empty / no description → skip row
            continue

        unit_val = (unit_list[i] if i < len(unit_list) else "") or ""
        unit_val = unit_val.strip() or None

        qty_val = list_float(qty_list, i)
        rate_val = list_float(rate_list, i)
        amt_val = list_float(amt_list, i)

        if qty_val is not None:
            has_line_qty = True

        if mode == "ITEM":
            # In ITEM mode, derive amount from qty * rate when both are present
            if qty_val is not None and rate_val is not None:
                amt_val = qty_val * rate_val

        line = BookingMaterialLine(
            booking_material_id=material.id if material.id else None,
            sequence_index=seq,
            description=desc,
            unit=unit_val,
            quantity=qty_val,
            rate=rate_val,
            amount=amt_val,
        )
        material.lines.append(line)
        has_any_line = True
        seq += 1

    # Enforce invariants per mode
    if mode == "ITEM":
        # At least one line required
        if not has_any_line:
            flash(
                "In ITEM mode, enter at least one material line.",
                "error",
            )
            db.session.rollback()
            return redirect(url_for("admin.booking_detail", booking_id=booking.id))

        # Derive header total_amount from line amounts
        total_amt = sum(
            (ln.amount or 0.0) for ln in material.lines if ln.amount is not None
        )
        material.total_amount = total_amt if material.lines else None

    elif mode == "LUMPSUM":
        has_header_values = bool(
            material.total_quantity is not None
            or material.total_amount is not None
            or material.total_quantity_unit
        )
        has_lines = has_any_line

        # Must have either header qty/amount OR at least one line
        if not has_header_values and not has_lines:
            flash(
                "In LUMPSUM mode, enter a header quantity/amount or at least one material line.",
                "error",
            )
            db.session.rollback()
            return redirect(url_for("admin.booking_detail", booking_id=booking.id))

        # Hard Rule A: header total qty and per-line qty must not both be used
        has_header_qty = material.total_quantity is not None
        if has_header_qty and has_line_qty:
            flash(
                "In LUMPSUM mode, use either the header total quantity or per-line quantities, not both.",
                "error",
            )
            db.session.rollback()
            return redirect(url_for("admin.booking_detail", booking_id=booking.id))

    db.session.commit()
    flash("Material list saved.", "success")
    return redirect(url_for("admin.booking_detail", booking_id=booking.id))


@admin_bp.route("/route-km-json", methods=["GET"])
def route_km_json():
    """
    Return possible KM options for routes between two endpoints.

    Used by Home Depot KM assistant:
      - If exactly one option is returned, UI may auto-fill.
      - If multiple, UI shows them as suggestions for the KM field.
    """
    from_code = (request.args.get("from") or "").strip().upper()
    to_code = (request.args.get("to") or "").strip().upper()

    if not from_code or not to_code:
        return jsonify({"options": []})

    # Validate both locations exist
    from_loc = Location.query.filter_by(code=from_code).first()
    to_loc = Location.query.filter_by(code=to_code).first()

    if not from_loc or not to_loc:
        return jsonify({"options": []})

    # Only active routes are considered
    routes = Route.query.filter_by(is_active=True).all()

    km_options = []

    for r in routes:
        # Collect start / end cluster codes from RouteStop flags
        start_codes = [s.location.code for s in r.stops if s.is_start_cluster]
        end_codes = [s.location.code for s in r.stops if s.is_end_cluster]

        # Match in either direction: from→to or to→from
        ok_1 = from_code in start_codes and to_code in end_codes
        ok_2 = to_code in start_codes and from_code in end_codes

        if ok_1 or ok_2:
            km_options.append(
                {
                    "km": r.total_km,
                    "route_code": r.code,
                    "route_name": r.name,
                }
            )

    # Deduplicate by (km, route_code) just in case
    seen = set()
    unique = []
    for opt in km_options:
        key = (opt["km"], opt["route_code"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(opt)

    return jsonify({"options": unique})
