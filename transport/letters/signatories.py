from __future__ import annotations

from typing import List, Optional

from transport.models import LetterSignatory


def get_active_letter_signatories() -> List[LetterSignatory]:
    """
    Return active signatories in a stable, user-friendly order.
    """
    return (
        LetterSignatory.query.filter_by(is_active=True)
        .order_by(
            LetterSignatory.sort_order.asc(),
            LetterSignatory.name.asc(),
            LetterSignatory.id.asc(),
        )
        .all()
    )


def get_signatory_by_id(raw_id: Optional[str]) -> Optional[LetterSignatory]:
    """
    Safe lookup from a request-provided id.
    Returns None on blank/invalid/non-existent.
    """
    if not raw_id:
        return None
    try:
        sid = int(str(raw_id).strip())
    except Exception:
        return None
    return LetterSignatory.query.get(sid)


def _wrap_name(name: Optional[str]) -> str:
    """
    Names must be printed wrapped in parentheses, like: (R. Prashaanth)
    If name already has surrounding (), don't double-wrap.
    """
    s = (name or "").strip()
    if not s:
        return ""
    if s.startswith("(") and s.endswith(")"):
        return s
    return f"({s})"


def signature_lines(
    signed_by: Optional[LetterSignatory],
    signed_for: Optional[LetterSignatory],
) -> List[str]:
    """
    Rule from user:

    - If (Name + Designation) match => print:
        (Name)
        Designation
    - Else print:
        (Signed by Name)
        Signed by Designation
        For <Signed for Designation>

    Fallback (legacy hardcoded) if not provided.
    """
    if signed_by and signed_for:
        by_name = _wrap_name(signed_by.name)
        for_name = (signed_for.designation or "").strip()

        if (signed_by.name == signed_for.name) and (
            signed_by.designation == signed_for.designation
        ):
            return [by_name, signed_by.designation]

        return [
            by_name,
            signed_by.designation,
            f"For {for_name}",
        ]

    # Legacy fallback (your earlier hard-coded default)
    return ["(R. Prashaanth)", "DEE/RS/ED", "For Sr.DEE/RS/ED"]
