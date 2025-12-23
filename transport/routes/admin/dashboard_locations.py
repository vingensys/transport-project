# admin/dashboard_locations.py
from __future__ import annotations

from typing import Any, Dict

from flask import request
from transport.models import Location


def get_locations_pagination_context() -> Dict[str, Any]:
    """
    Locations tab pagination context.
    Behavior preserved exactly from dashboard().
    """
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

    return {
        "locations": locations,
        "loc_page": current_page,
        "loc_total_pages": total_pages,
        "loc_start_page": start_page,
        "loc_end_page": end_page,
    }
