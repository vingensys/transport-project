# transport/letters/pdf_common.py
from __future__ import annotations

import re
import textwrap
from datetime import date
from pathlib import Path
from typing import List, Optional

from flask import current_app
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# =============================================================================
# Fonts
# =============================================================================

def register_verdana_fonts() -> None:
    font_dir = Path(current_app.root_path) / "static" / "fonts" / "Verdana"
    pdfmetrics.registerFont(TTFont("Verdana", str(font_dir / "Verdana.ttf")))
    pdfmetrics.registerFont(TTFont("Verdana-Bold", str(font_dir / "Verdana-Bold.ttf")))
    pdfmetrics.registerFont(TTFont("Verdana-Italic", str(font_dir / "Verdana-Italic.ttf")))
    pdfmetrics.registerFont(TTFont("Verdana-BoldItalic", str(font_dir / "Verdana-BoldItalic.ttf")))


# =============================================================================
# Common formatting
# =============================================================================

def fmt_date_ddmmyyyy(d: date) -> str:
    return d.strftime("%d-%m-%Y")


def build_ref_no(prefix: str, trip_serial: int) -> str:
    p = (prefix or "").strip().strip("/")
    return f"No.{p}/Transport/Placement/{trip_serial}"


def build_mod_ref_no(prefix: str, trip_serial: int, mod_seq: int) -> str:
    p = (prefix or "").strip().strip("/")
    return f"No.{p}/Transport/Placement/Mod/{trip_serial}/{mod_seq}"


def clean_filename_keep_spaces(name: str, max_len: int = 160) -> str:
    """
    Keep spaces, but strip characters that can break headers/paths.
    Also collapse repeated whitespace.
    """
    s = (name or "").strip()
    s = re.sub(r'[\\/:*?"<>|]+', " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > max_len:
        s = s[:max_len].rstrip()
    return s


# =============================================================================
# Company block helpers
# =============================================================================

def wrap_address(address: str, width: int = 30) -> str:
    addr = (address or "").strip()
    if not addr:
        return "-"
    wrapped_lines = textwrap.wrap(
        addr,
        width=width,
        break_long_words=False,
        break_on_hyphens=False,
    )
    return "<br/>".join(wrapped_lines) if wrapped_lines else addr


def format_company_contact_block(company) -> str:
    lines: List[str] = []
    lines.append(wrap_address(getattr(company, "address", "") or "", width=30))

    phone = (getattr(company, "phone", None) or "").strip()
    email = (getattr(company, "email", None) or "").strip()

    if phone:
        lines.append(f"Phone : {phone}")
    if email:
        lines.append(f"Email : {email}")

    return "<br/>".join(lines)


# =============================================================================
# Authority text helpers (HTML-like strings for Paragraph)
# =============================================================================

def authority_designation(ba) -> str:
    return ba.authority.authority_title if ba and getattr(ba, "authority", None) else "-"


def authority_address(ba) -> str:
    if not ba or not getattr(ba, "authority", None):
        return ""
    return (ba.authority.address or "").strip()


def authority_block(authorities) -> str:
    """
    Multi authority block within ONE CELL (two lines per authority).
    If exactly ONE authority -> no (i) prefix.
    If multiple -> (i), (ii), ... prefix.
    """
    if not authorities:
        return "-"

    if len(authorities) == 1:
        ba = authorities[0]
        desig = authority_designation(ba)
        addr = authority_address(ba)
        return f"{desig}<br/>&nbsp;&nbsp;&nbsp;&nbsp;{addr}" if addr else desig

    blocks: List[str] = []
    roman = ["(i)", "(ii)", "(iii)", "(iv)", "(v)", "(vi)", "(vii)", "(viii)", "(ix)", "(x)"]
    for i, ba in enumerate(authorities):
        tag = roman[i] if i < len(roman) else f"({i+1})"
        desig = authority_designation(ba)
        addr = authority_address(ba)
        if addr:
            blocks.append(f"{tag} {desig}<br/>&nbsp;&nbsp;&nbsp;&nbsp;{addr}")
        else:
            blocks.append(f"{tag} {desig}")
    return "<br/><br/>".join(blocks)
