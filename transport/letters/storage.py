# transport/letters/storage.py
from __future__ import annotations

from pathlib import Path
from typing import Optional

from flask import current_app

from transport.models import BookingLetter


# =============================================================================
# Storage paths
# =============================================================================

def letters_root() -> Path:
    root = Path(current_app.instance_path) / "letters"
    root.mkdir(parents=True, exist_ok=True)
    return root


def booking_letters_dir(booking_id: int) -> Path:
    d = letters_root() / f"booking_{booking_id}"
    d.mkdir(parents=True, exist_ok=True)
    return d


# =============================================================================
# Sequence helpers
# =============================================================================

def next_letter_sequence(booking_id: int, letter_type: str) -> int:
    last = (
        BookingLetter.query
        .filter_by(booking_id=booking_id, letter_type=letter_type)
        .order_by(BookingLetter.sequence_no.desc())
        .first()
    )
    return (last.sequence_no + 1) if last else 1


# =============================================================================
# Filename helpers
# =============================================================================

def is_pdf_filename(name: str) -> bool:
    return bool(name) and name.lower().endswith(".pdf")


def clean_filename_keep_spaces(name: str, max_len: int = 160) -> str:
    """
    Keep spaces, but strip characters that can break headers/paths.
    Also collapse repeated whitespace.
    """
    import re

    s = (name or "").strip()
    s = re.sub(r'[\\/:*?"<>|]+', " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > max_len:
        s = s[:max_len].rstrip()
    return s


# =============================================================================
# PDF merge
# =============================================================================

def merge_pdfs(base_pdf: Path, attachment_pdf: Path, out_pdf: Path) -> None:
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    for p in PdfReader(str(base_pdf)).pages:
        writer.add_page(p)
    for p in PdfReader(str(attachment_pdf)).pages:
        writer.add_page(p)
    with open(out_pdf, "wb") as f:
        writer.write(f)
