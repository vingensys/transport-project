# admin/dashboard_booking.py
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

from flask import request

from transport.models import Agreement, Booking


def get_booking_history_context(
    agreements: List[Agreement],
    home_location_id: Optional[int],
) -> Dict[str, Any]:
    """
    Booking/History tab context builder.

    Behavior preserved from the original dashboard.py:
    - booking_scope: active/all (default active)
    - active_agreement: first agreement in `agreements` where is_active is True
    - Trip serial: stable by Booking.id order per agreement using serial_source_bookings
    - bookings display set: newest first (within active agreement) or all newest first
    - booking_status filter: all/active/cancelled
    - booking_search: applied AFTER booking_rows built (by booking id / trip serial)
    - direction inference relative to home_location_id using route start/end clusters
    """
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
        serial_source_bookings = (
            Booking.query
            .filter_by(agreement_id=active_agreement.id)
            .order_by(Booking.id.asc())
            .all()
        )
        bookings = (
            Booking.query
            .filter_by(agreement_id=active_agreement.id)
            .order_by(Booking.id.desc())
            .all()
        )
    else:
        booking_scope = "all" if not active_agreement else booking_scope

        serial_source_bookings = (
            Booking.query
            .order_by(Booking.agreement_id.asc(), Booking.id.asc())
            .all()
        )
        bookings = Booking.query.order_by(Booking.id.desc()).all()

    # ---------------------------------
    # Booking status filter (all / active / cancelled)
    # ---------------------------------
    booking_status = request.args.get("booking_status", "all")
    if booking_status not in ("all", "active", "cancelled"):
        booking_status = "all"

    if booking_status == "active":
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

    booking_rows: List[Dict[str, Any]] = []

    for b in bookings:
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
            stops = b.route.stops
            start_stops = [s for s in stops if s.is_start_cluster]
            end_stops = [s for s in stops if s.is_end_cluster]

            home_in_start = any(s.location_id == home_location_id for s in start_stops)
            home_in_end = any(s.location_id == home_location_id for s in end_stops)

            if home_in_start and not home_in_end:
                direction = "OUTBOUND"
            elif home_in_end and not home_in_start:
                direction = "INBOUND"
            elif home_in_start and home_in_end:
                direction = "HOME"

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

            if s.isdigit():
                try:
                    val = int(s)
                    if b.id == val or trip_serial == val:
                        return True
                except ValueError:
                    pass

            return (
                s.lower() in str(b.id).lower()
                or s.lower() in str(trip_serial).lower()
            )

        booking_rows = [row for row in booking_rows if row_matches(row)]

    return {
        "bookings": bookings,
        "booking_rows": booking_rows,
        "booking_scope": booking_scope,
        "booking_status": booking_status,
        "booking_search": booking_search,
        "active_agreement": active_agreement,
    }
