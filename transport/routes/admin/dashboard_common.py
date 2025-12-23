# admin/dashboard_common.py
from __future__ import annotations

from typing import Any, Dict

from transport.models import (
    AppConfig,
    Authority,
    Company,
    Agreement,
    LorryDetails,
    Location,
    Route,
    LetterSignatory,
)


def get_core_master_data() -> Dict[str, Any]:
    """
    Data used across multiple dashboard tabs.
    Keep ordering identical to current behavior.
    """
    companies = Company.query.order_by(Company.id.desc()).all()
    agreements = Agreement.query.order_by(Agreement.id.desc()).all()
    lorries = LorryDetails.query.order_by(LorryDetails.id.desc()).all()
    routes = Route.query.order_by(Route.id.desc()).all()

    # Letter signatories (active first, then sort_order)
    letter_signatories = (
        LetterSignatory.query
        .order_by(
            LetterSignatory.is_active.desc(),
            LetterSignatory.sort_order.asc(),
            LetterSignatory.name.asc(),
            LetterSignatory.id.asc(),
        )
        .all()
    )

    return {
        "companies": companies,
        "agreements": agreements,
        "lorries": lorries,
        "routes": routes,
        "letter_signatories": letter_signatories,
    }


def get_authorities_and_locations() -> Dict[str, Any]:
    """
    Authorities list + all locations list + booking_auth_map.
    booking_auth_map is: location_code -> [{id, title}, ...]
    Ordering kept identical to current behavior.
    """
    authorities = Authority.query.order_by(Authority.id.desc()).all()
    all_locations = Location.query.order_by(Location.code).all()

    loc_code_by_id = {loc.id: loc.code for loc in all_locations}
    booking_auth_map: Dict[str, list[dict[str, Any]]] = {}

    for auth in authorities:
        code = loc_code_by_id.get(auth.location_id)
        if not code:
            continue
        booking_auth_map.setdefault(code, []).append(
            {"id": auth.id, "title": auth.authority_title}
        )

    return {
        "authorities": authorities,
        "all_locations": all_locations,
        "booking_auth_map": booking_auth_map,
    }


def get_latest_app_config() -> Dict[str, Any]:
    """
    Single source of truth:
    Always use latest row (highest id) consistently.
    """
    app_config = AppConfig.query.order_by(AppConfig.id.desc()).first()
    home_location = app_config.home_location if app_config else None
    home_authority = app_config.home_authority if app_config else None
    home_location_id = home_location.id if home_location else None

    return {
        "app_config": app_config,
        "home_location": home_location,
        "home_authority": home_authority,
        "home_location_id": home_location_id,
    }
