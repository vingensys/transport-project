# transport/letters/snapshots.py
from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from transport.models import (
    AppConfig,
    Booking,
    BookingAuthority,
    BookingMaterial,
    LetterSignatory,
)


# =============================================================================
# Trip serial (mirror the stable rule used elsewhere)
# =============================================================================

def compute_trip_serial(booking: Booking) -> int:
    """
    Stable Trip Serial within an agreement = position in Booking.id ascending.
    """
    siblings = (
        Booking.query.filter_by(agreement_id=booking.agreement_id)
        .order_by(Booking.id.asc())
        .all()
    )
    for idx, b in enumerate(siblings, start=1):
        if b.id == booking.id:
            return idx
    return 1


# =============================================================================
# Home authority helpers
# =============================================================================

def get_latest_app_config() -> Optional[AppConfig]:
    """
    Your project uses 'latest row' for AppConfig.
    """
    return AppConfig.query.order_by(AppConfig.id.desc()).first()


def booking_has_home_authority(booking: Booking) -> bool:
    """
    True if latest AppConfig has home_authority_id AND booking includes that authority.
    """
    cfg = get_latest_app_config()
    if not cfg or not cfg.home_authority_id:
        return False

    bas = booking.booking_authorities or []
    return any((ba.authority_id == cfg.home_authority_id) for ba in bas)


def _infer_traffic_direction_from_home_role(booking: Booking) -> Optional[str]:
    """
    Determines INBOUND / OUTBOUND by locating the home authority inside booking authorities:
      - if home authority role == UNLOADING => INBOUND
      - if home authority role == LOADING  => OUTBOUND
    Returns None if cannot infer.
    """
    cfg = get_latest_app_config()
    if not cfg or not cfg.home_authority_id:
        return None

    for ba in (booking.booking_authorities or []):
        if ba.authority_id != cfg.home_authority_id:
            continue
        role = (ba.role or "").upper().strip()
        if role == "UNLOADING":
            return "INBOUND"
        if role == "LOADING":
            return "OUTBOUND"

    return None


def compute_far_end_authorities_and_action(
    booking: Booking,
) -> Tuple[List[BookingAuthority], str]:
    """
    Returns (far_end_authorities, action_verb).

    Rule (exactly as in your current letters.py):
      - direction inferred from home authority role; default INBOUND if unknown
      - if INBOUND  => far end are LOADING authorities, action = "load"
      - if OUTBOUND => far end are UNLOADING authorities, action = "unload"
    """
    direction = _infer_traffic_direction_from_home_role(booking) or "INBOUND"

    loading = sorted(
        [
            ba
            for ba in (booking.booking_authorities or [])
            if (ba.role or "").upper().strip() == "LOADING"
        ],
        key=lambda x: x.sequence_index or 0,
    )
    unloading = sorted(
        [
            ba
            for ba in (booking.booking_authorities or [])
            if (ba.role or "").upper().strip() == "UNLOADING"
        ],
        key=lambda x: x.sequence_index or 0,
    )

    if direction == "INBOUND":
        return loading, "load"
    return unloading, "unload"


# =============================================================================
# Attachments
# =============================================================================

def booking_requires_attachment_pdf(booking: Booking) -> bool:
    """
    Attachment is required if any material table is ATTACHED mode.
    """
    mts = booking.material_tables or []
    return any(((mt.mode or "").upper().strip() == "ATTACHED") for mt in mts)


# =============================================================================
# Snapshot builder (runtime snapshot for PDFs)
# =============================================================================

def build_snapshot(
    booking: Booking,
    letter_date: date,
    signed_by: Optional[LetterSignatory] = None,
    signed_for: Optional[LetterSignatory] = None,
) -> Dict[str, Any]:
    """
    Runtime snapshot used by PDF generation.
    """
    ag = booking.agreement
    trip_serial = compute_trip_serial(booking)

    loading = sorted(
        [
            ba
            for ba in (booking.booking_authorities or [])
            if (ba.role or "").upper().strip() == "LOADING"
        ],
        key=lambda x: x.sequence_index or 0,
    )
    unloading = sorted(
        [
            ba
            for ba in (booking.booking_authorities or [])
            if (ba.role or "").upper().strip() == "UNLOADING"
        ],
        key=lambda x: x.sequence_index or 0,
    )

    far_end_bas, far_end_action = compute_far_end_authorities_and_action(booking)

    return {
        "booking": booking,
        "agreement": ag,
        "trip_serial": trip_serial,
        "letter_date": letter_date,
        "loading": loading,
        "unloading": unloading,
        "requires_attachment": booking_requires_attachment_pdf(booking),
        "far_end_bas": far_end_bas,
        "far_end_action": far_end_action,
        "signed_by": signed_by,
        "signed_for": signed_for,
    }


# =============================================================================
# Canonical snapshot + hashing (for change detection)
# =============================================================================

def _canon_authority(ba: Optional[BookingAuthority]) -> Dict[str, Any]:
    if not ba or not ba.authority:
        return {
            "authority_id": None,
            "role": None,
            "sequence_index": None,
            "title": "-",
            "location_code": "",
        }

    loc_code = ""
    if getattr(ba.authority, "location", None):
        loc_code = (ba.authority.location.code or "").strip()

    return {
        "authority_id": ba.authority_id,
        "role": (ba.role or "").upper().strip(),
        "sequence_index": ba.sequence_index or 0,
        "title": ba.authority.authority_title or "-",
        "location_code": loc_code,
    }


def _canon_material_table(mt: BookingMaterial) -> Dict[str, Any]:
    lines = sorted((mt.lines or []), key=lambda x: x.sequence_index or 0)
    return {
        "id": mt.id,
        "sequence_index": mt.sequence_index or 0,
        "booking_authority_id": mt.booking_authority_id,
        "mode": ((mt.mode or "").upper().strip() or "ITEM"),
        "total_quantity": mt.total_quantity,
        "total_quantity_unit": (mt.total_quantity_unit or "").strip(),
        "total_amount": mt.total_amount,
        "lines": [
            {
                "sequence_index": ln.sequence_index or 0,
                "description": (ln.description or "").strip(),
                "unit": (ln.unit or "").strip(),
                "quantity": ln.quantity,
                "rate": ln.rate,
                "amount": ln.amount,
            }
            for ln in lines
        ],
    }


def build_canonical_snapshot_for_placement(
    booking: Booking,
    letter_date_val: date,
) -> Dict[str, Any]:
    """
    Canonical payload for change detection.
    IMPORTANT: letter_date is present here but is excluded from hash.
    """
    ag = booking.agreement
    trip_serial = compute_trip_serial(booking)

    loading = sorted(
        [
            ba
            for ba in (booking.booking_authorities or [])
            if (ba.role or "").upper().strip() == "LOADING"
        ],
        key=lambda x: x.sequence_index or 0,
    )
    unloading = sorted(
        [
            ba
            for ba in (booking.booking_authorities or [])
            if (ba.role or "").upper().strip() == "UNLOADING"
        ],
        key=lambda x: x.sequence_index or 0,
    )

    mts = sorted(
        (booking.material_tables or []),
        key=lambda m: ((m.sequence_index or 0), (m.id or 0)),
    )

    return {
        "booking_id": booking.id,
        "agreement_id": booking.agreement_id,
        "trip_serial": trip_serial,
        "letter_date": letter_date_val.isoformat(),
        "placement_date": booking.placement_date.isoformat() if booking.placement_date else None,
        "loa_number": (ag.loa_number if ag else None),
        "placement_ref_prefix": (ag.placement_ref_prefix if ag else None),
        "company_name": (booking.company.name if booking.company else None),
        "route_id": booking.route_id,
        "route_total_km": (booking.route.total_km if booking.route else None),
        "lorry_capacity": (booking.lorry.capacity if booking.lorry else None),
        "lorry_carrier_size": (booking.lorry.carrier_size if booking.lorry else None),
        "loading": [_canon_authority(ba) for ba in loading],
        "unloading": [_canon_authority(ba) for ba in unloading],
        "materials": [_canon_material_table(mt) for mt in mts],
        "requires_attachment": booking_requires_attachment_pdf(booking),
    }


def hash_canonical_snapshot(payload: Dict[str, Any]) -> str:
    """
    IMPORTANT: letter_date is NOT part of "booking changed?" detection.
    """
    clean = dict(payload or {})
    clean.pop("letter_date", None)

    s = json.dumps(clean, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def stable_json_hash(obj: Any) -> str:
    s = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()
