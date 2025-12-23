# admin/dashboard_overview.py
from __future__ import annotations

from typing import Any, Dict, Tuple

from transport.models import Agreement, Booking


def _allocate_trip_amount_and_bands(
    trip_mt_km: float,
    cum_mt_km_before: float,
    total_mt_km: float,
    rate_per_mt_km: float,
) -> Tuple[float, float, float, float]:
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

    def alloc_into_band(upper_limit: float, factor: float) -> None:
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


def get_overview_context(active_agreement: Agreement) -> Dict[str, Any]:
    """
    Dashboard overview tab context.
    """
    overview_summary = None
    overview_rows = []

    if active_agreement:
        overview_summary, overview_rows = _compute_agreement_overview(active_agreement)

    return {
        "overview_summary": overview_summary,
        "overview_rows": overview_rows,
    }
