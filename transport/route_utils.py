import hashlib
from typing import List, Tuple


def build_route_code_and_name(
    from_codes: List[str],
    mid_codes: List[str],
    to_codes: List[str],
    total_km: int,
) -> Tuple[str, str]:
    """
    Given ordered lists of location codes for from / mid / to and the total km,
    generate a deterministic route code and a human-readable route name.

    Assumes:
      - from_codes and to_codes are non-empty
      - codes are already normalized to uppercase and stripped
    """
    all_codes = from_codes + mid_codes + to_codes

    # Canonical signature: codes in order + km
    canonical = "|".join(all_codes) + f"|km={total_km}"
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest().upper()
    short = digest[:8]

    first = from_codes[0]
    last = to_codes[-1]

    # System-generated route code
    code = f"R_{first}_{last}_{short}"

    # System-generated human-readable name
    if mid_codes:
        mid_display = ", ".join(mid_codes)
        name = f"{first} – {last} via {mid_display}"
    else:
        name = f"{first} – {last}"

    return code, name
