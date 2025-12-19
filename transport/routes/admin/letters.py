from __future__ import annotations

import re, hashlib, json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from flask import (
    request,
    redirect,
    url_for,
    flash,
    render_template,
    send_file,
    current_app,
)
from werkzeug.utils import secure_filename

from transport.models import (
    db,
    AppConfig,
    Booking,
    BookingAuthority,
    BookingMaterial,
    BookingLetter,
    BookingLetterAttachment,
)

from . import admin_bp

# ---------- PDF ----------
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
from reportlab.pdfgen import canvas as pdfcanvas

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from pypdf import PdfReader, PdfWriter


# =============================================================================
# Storage helpers
# =============================================================================

def _letters_root() -> Path:
    root = Path(current_app.instance_path) / "letters"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _booking_letters_dir(booking_id: int) -> Path:
    d = _letters_root() / f"booking_{booking_id}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _next_letter_sequence(booking_id: int, letter_type: str) -> int:
    last = (
        BookingLetter.query
        .filter_by(booking_id=booking_id, letter_type=letter_type)
        .order_by(BookingLetter.sequence_no.desc())
        .first()
    )
    return (last.sequence_no + 1) if last else 1


def _is_pdf_filename(name: str) -> bool:
    return name.lower().endswith(".pdf")


def booking_has_home_authority(booking: Booking) -> bool:
    cfg = AppConfig.query.order_by(AppConfig.id.desc()).first()
    if not cfg or not cfg.home_authority_id:
        return False
    return any(
        ba.authority_id == cfg.home_authority_id
        for ba in (booking.booking_authorities or [])
    )


# =============================================================================
# Fonts
# =============================================================================

def _register_verdana_fonts() -> None:
    font_dir = Path(current_app.root_path) / "static" / "fonts" / "Verdana"
    pdfmetrics.registerFont(TTFont("Verdana", str(font_dir / "Verdana.ttf")))
    pdfmetrics.registerFont(TTFont("Verdana-Bold", str(font_dir / "Verdana-Bold.ttf")))
    pdfmetrics.registerFont(TTFont("Verdana-Italic", str(font_dir / "Verdana-Italic.ttf")))
    pdfmetrics.registerFont(TTFont("Verdana-BoldItalic", str(font_dir / "Verdana-BoldItalic.ttf")))


# =============================================================================
# Trip serial (mirror bookings.py)
# =============================================================================

def compute_trip_serial(booking: Booking) -> int:
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
# Formatting + table styles
# =============================================================================

def _fmt_date_ddmmyyyy(d: date) -> str:
    return d.strftime("%d-%m-%Y")


def _build_ref_no(prefix: str, trip_serial: int) -> str:
    p = (prefix or "").strip().strip("/")
    return f"No.{p}/Transport/Placement/{trip_serial}"


def _table_base_style() -> List[Tuple]:
    # Verdana 11; 1.15 line spacing => 12.65 leading
    return [
        ("FONTNAME", (0, 0), (-1, -1), "Verdana"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("LEADING", (0, 0), (-1, -1), 12.65),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]


def _authority_designation(ba: Optional[BookingAuthority]) -> str:
    return ba.authority.authority_title if ba and ba.authority else "-"


def _authority_address(ba: Optional[BookingAuthority]) -> str:
    if not ba or not ba.authority:
        return ""
    return (ba.authority.address or "").strip()


def _authority_block(authorities: List[BookingAuthority]) -> str:
    """
    Multi authority block within ONE CELL (two lines per authority).
    If exactly ONE authority -> no (i) prefix.
    If multiple -> (i), (ii), ... prefix.
    """
    if not authorities:
        return "-"

    if len(authorities) == 1:
        ba = authorities[0]
        desig = _authority_designation(ba)
        addr = _authority_address(ba)
        return f"{desig}<br/>&nbsp;&nbsp;&nbsp;&nbsp;{addr}" if addr else desig

    blocks: List[str] = []
    roman = ["(i)", "(ii)", "(iii)", "(iv)", "(v)", "(vi)", "(vii)", "(viii)", "(ix)", "(x)"]
    for i, ba in enumerate(authorities):
        tag = roman[i] if i < len(roman) else f"({i+1})"
        desig = _authority_designation(ba)
        addr = _authority_address(ba)
        if addr:
            blocks.append(f"{tag} {desig}<br/>&nbsp;&nbsp;&nbsp;&nbsp;{addr}")
        else:
            blocks.append(f"{tag} {desig}")
    return "<br/><br/>".join(blocks)


def _fmt_qty_unit(qty: Optional[float], unit: Optional[str]) -> str:
    if qty is None and not (unit or "").strip():
        return ""
    if qty is None:
        return (unit or "").strip()
    u = (unit or "").strip()
    return f"{qty} {u}".strip()


def _fmt_money(v: Optional[float]) -> str:
    if v is None:
        return ""
    try:
        return f"{float(v):.2f}"
    except Exception:
        return str(v)


def _clean_filename_keep_spaces(name: str, max_len: int = 160) -> str:
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


def _download_name_for_placement(snapshot: Dict[str, Any]) -> str:
    booking: Booking = snapshot["booking"]
    trip_serial: int = snapshot["trip_serial"]

    loading: List[BookingAuthority] = snapshot.get("loading") or []
    unloading: List[BookingAuthority] = snapshot.get("unloading") or []

    def _loc_label(ba: BookingAuthority) -> str:
        if ba and ba.authority and ba.authority.location:
            code = (ba.authority.location.code or "").strip()
            if code:
                return code
        return _authority_designation(ba)

    from_parts = [_loc_label(ba) for ba in loading if ba]
    to_parts = [_loc_label(ba) for ba in unloading if ba]

    from_str = " ".join([p for p in from_parts if p]) or "FROM"
    to_str = " ".join([p for p in to_parts if p]) or "TO"

    placement_dt = (
        booking.placement_date.strftime("%d-%m-%Y")
        if booking.placement_date
        else _fmt_date_ddmmyyyy(snapshot["letter_date"])
    )

    raw = f"{trip_serial} - {from_str} to {to_str} on {placement_dt}.pdf"
    return _clean_filename_keep_spaces(raw)


# =============================================================================
# Far-end authority + action (load/unload) logic
# =============================================================================

def _infer_traffic_direction_from_home_role(booking: Booking) -> Optional[str]:
    cfg = AppConfig.query.order_by(AppConfig.id.desc()).first()
    if not cfg or not cfg.home_authority_id:
        return None

    for ba in booking.booking_authorities:
        if ba.authority_id == cfg.home_authority_id:
            if (ba.role or "").upper() == "UNLOADING":
                return "INBOUND"
            if (ba.role or "").upper() == "LOADING":
                return "OUTBOUND"
    return None


def compute_far_end_authorities_and_action(booking: Booking) -> Tuple[List[BookingAuthority], str]:
    """
    Returns (far_end_authorities, action).
      - INBOUND  -> far end is LOADING authorities; action='load'
      - OUTBOUND -> far end is UNLOADING authorities; action='unload'
    """
    direction = _infer_traffic_direction_from_home_role(booking) or "INBOUND"

    loading = sorted(
        [ba for ba in booking.booking_authorities if (ba.role or "").upper() == "LOADING"],
        key=lambda x: x.sequence_index or 0,
    )
    unloading = sorted(
        [ba for ba in booking.booking_authorities if (ba.role or "").upper() == "UNLOADING"],
        key=lambda x: x.sequence_index or 0,
    )

    if direction == "INBOUND":
        return loading, "load"
    return unloading, "unload"


# =============================================================================
# Attachment merging
# =============================================================================

def merge_pdfs(base_pdf: Path, attachment_pdf: Path, out_pdf: Path) -> None:
    writer = PdfWriter()
    for p in PdfReader(str(base_pdf)).pages:
        writer.add_page(p)
    for p in PdfReader(str(attachment_pdf)).pages:
        writer.add_page(p)
    with open(out_pdf, "wb") as f:
        writer.write(f)


def booking_requires_attachment_pdf(booking: Booking) -> bool:
    return any((mt.mode or "").upper() == "ATTACHED" for mt in (booking.material_tables or []))


# =============================================================================
# Snapshot builder
# =============================================================================

def build_snapshot(booking: Booking, letter_date: date) -> Dict[str, Any]:
    ag = booking.agreement
    trip_serial = compute_trip_serial(booking)

    loading = sorted(
        [ba for ba in booking.booking_authorities if (ba.role or "").upper() == "LOADING"],
        key=lambda x: x.sequence_index or 0,
    )
    unloading = sorted(
        [ba for ba in booking.booking_authorities if (ba.role or "").upper() == "UNLOADING"],
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
    }

# =============================================================================
# Canonical snapshot + hashing (for change detection)
# =============================================================================

def _canon_authority(ba: Optional[BookingAuthority]) -> Dict[str, Any]:
    if not ba or not ba.authority:
        return {"authority_id": None, "role": None, "sequence_index": None, "title": "-", "location_code": ""}
    loc_code = ""
    if getattr(ba.authority, "location", None):
        loc_code = (ba.authority.location.code or "").strip()
    return {
        "authority_id": ba.authority_id,
        "role": (ba.role or "").upper(),
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


def build_canonical_snapshot_for_placement(booking: Booking, letter_date_val: date) -> Dict[str, Any]:
    ag = booking.agreement
    trip_serial = compute_trip_serial(booking)

    loading = sorted(
        [ba for ba in (booking.booking_authorities or []) if (ba.role or "").upper() == "LOADING"],
        key=lambda x: x.sequence_index or 0,
    )
    unloading = sorted(
        [ba for ba in (booking.booking_authorities or []) if (ba.role or "").upper() == "UNLOADING"],
        key=lambda x: x.sequence_index or 0,
    )

    mts = sorted((booking.material_tables or []), key=lambda m: ((m.sequence_index or 0), (m.id or 0)))

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


def _hash_canonical_snapshot(payload: Dict[str, Any]) -> str:
    # IMPORTANT: letter_date is NOT part of "booking changed?" detection.
    # It is only the issue date of the document.
    clean = dict(payload or {})
    clean.pop("letter_date", None)

    s = json.dumps(clean, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# =============================================================================
# Materials table rendering (alignment via Paragraph styles)
# =============================================================================

def _materials_col_widths_item(doc_width: float) -> List[float]:
    w_sl = 16 * mm
    w_qty = 28 * mm
    w_rate = 32 * mm
    w_amt = 32 * mm
    w_desc = doc_width - (w_sl + w_qty + w_rate + w_amt)
    return [w_sl, w_desc, w_qty, w_rate, w_amt]


def _materials_col_widths_lumpsum(doc_width: float) -> List[float]:
    w_sl = 16 * mm
    w_qty = 28 * mm
    w_amt = 35 * mm
    w_desc = doc_width - (w_sl + w_qty + w_amt)
    return [w_sl, w_desc, w_qty, w_amt]


def _materials_col_widths_attached(doc_width: float) -> List[float]:
    w_sl = 16 * mm
    w_amt = 35 * mm
    w_desc = doc_width - (w_sl + w_amt)
    return [w_sl, w_desc, w_amt]


def _material_table_style_common(grid: bool = True) -> List[Tuple]:
    cmds = _table_base_style()
    if grid:
        cmds += [("GRID", (0, 0), (-1, -1), 0.6, colors.black)]

    cmds += [
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("FONTNAME", (0, 0), (-1, 0), "Verdana-Bold"),

        # Header centered
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),

        # Sl no centered
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("VALIGN", (0, 1), (0, -1), "MIDDLE"),

        # Description left
        ("ALIGN", (1, 1), (1, -1), "LEFT"),
        ("VALIGN", (1, 1), (1, -1), "TOP"),

        # Qty column centered (body)
        ("ALIGN", (2, 1), (2, -1), "CENTER"),

        # Right align last numeric columns generally (safe for item/lumpsum/attached)
        ("ALIGN", (-1, 1), (-1, -1), "RIGHT"),
    ]
    return cmds


def _render_material_table_item(
    mt: BookingMaterial,
    doc_width: float,
    normal: ParagraphStyle,
    bold: ParagraphStyle,
    center: ParagraphStyle,
    money_right: ParagraphStyle,
    money_right_bold: ParagraphStyle,
) -> Table:
    cols = _materials_col_widths_item(doc_width)

    header = ["Sl no", "Description", "Qty/Unit", "Value of each item (Rs.)", "Total value (Rs.)"]
    rows: List[List[Any]] = []
    rows.append([Paragraph(h, bold) for h in header])

    total_amt = 0.0
    lines = sorted(mt.lines or [], key=lambda x: x.sequence_index or 0)

    if not lines:
        rows.append([
            "1",
            Paragraph("-", normal),
            Paragraph("", center),
            Paragraph("", money_right),
            Paragraph("", money_right),
        ])
    else:
        for i, ln in enumerate(lines, start=1):
            if ln.amount is not None:
                try:
                    total_amt += float(ln.amount)
                except Exception:
                    pass
            rows.append([
                str(i),
                Paragraph((ln.description or "").replace("\n", "<br/>"), normal),
                Paragraph(_fmt_qty_unit(ln.quantity, ln.unit), center),
                Paragraph(_fmt_money(ln.rate), money_right),
                Paragraph(_fmt_money(ln.amount), money_right),
            ])

    rows.append([
        "",
        Paragraph("Total", bold),
        Paragraph("", center),
        Paragraph("", money_right),
        Paragraph(_fmt_money(total_amt), money_right_bold),
    ])

    tbl = Table(rows, colWidths=cols, repeatRows=1)
    tbl.setStyle(TableStyle(_material_table_style_common()))
    return tbl


def _render_material_table_lumpsum(
    mt: BookingMaterial,
    doc_width: float,
    normal: ParagraphStyle,
    bold: ParagraphStyle,
    center: ParagraphStyle,
    money_right: ParagraphStyle,
    money_right_bold: ParagraphStyle,
) -> Table:
    cols = _materials_col_widths_lumpsum(doc_width)
    header = ["Sl no", "Description", "Qty/Unit", "Amount (Rs.)"]

    rows: List[List[Any]] = []
    rows.append([Paragraph(h, bold) for h in header])

    lines = sorted(mt.lines or [], key=lambda x: x.sequence_index or 0)
    any_line_qty = any((ln.quantity is not None) for ln in lines)

    # If no lines at all, still show total qty + amount
    if not lines:
        qty_cell = _fmt_qty_unit(mt.total_quantity, mt.total_quantity_unit) if not any_line_qty else ""
        rows.append([
            "1",
            Paragraph("-", normal),
            Paragraph(qty_cell, center),
            Paragraph(_fmt_money(mt.total_amount), money_right),
        ])
        tbl = Table(rows, colWidths=cols, repeatRows=1)
        tbl.setStyle(TableStyle(_material_table_style_common()))
        return tbl

    # IMPORTANT: If header total qty is used (no per-line qty),
    # put the qty text into the first body row NOW (before Table is created),
    # so merged cell shows it.
    header_qty_text = _fmt_qty_unit(mt.total_quantity, mt.total_quantity_unit) if not any_line_qty else ""

    for i, ln in enumerate(lines, start=1):
        qty_cell = _fmt_qty_unit(ln.quantity, ln.unit) if any_line_qty else (header_qty_text if i == 1 else "")
        amt_cell = _fmt_money(mt.total_amount) if i == 1 else ""  # merged Amount cell anchored at first row

        rows.append([
            str(i),
            Paragraph((ln.description or "").replace("\n", "<br/>"), normal),
            Paragraph(qty_cell, center),
            Paragraph(amt_cell, money_right),
        ])

    body_start = 1
    body_end = body_start + len(lines) - 1

    tbl = Table(rows, colWidths=cols, repeatRows=1)

    style_cmds = _material_table_style_common()

    # Merge Amount always if >1 row
    if len(lines) > 1:
        style_cmds.append(("SPAN", (3, body_start), (3, body_end)))
        style_cmds.append(("VALIGN", (3, body_start), (3, body_end), "MIDDLE"))

    # Merge Qty column if header total qty is used (no per-line qty)
    if not any_line_qty and len(lines) > 1:
        style_cmds.append(("SPAN", (2, body_start), (2, body_end)))
        style_cmds.append(("VALIGN", (2, body_start), (2, body_end), "MIDDLE"))

    tbl.setStyle(TableStyle(style_cmds))
    return tbl


def _render_material_table_attached(
    mt: BookingMaterial,
    doc_width: float,
    normal: ParagraphStyle,
    bold: ParagraphStyle,
    money_right: ParagraphStyle,
) -> Table:
    cols = _materials_col_widths_attached(doc_width)
    header = ["Sl no", "Description", "Amount (Rs.)"]

    rows: List[List[Any]] = []
    rows.append([Paragraph(h, bold) for h in header])
    rows.append([
        "1",
        Paragraph("As per list attached", normal),
        Paragraph(_fmt_money(mt.total_amount), money_right),
    ])

    tbl = Table(rows, colWidths=cols, repeatRows=1)
    tbl.setStyle(TableStyle(_material_table_style_common()))
    return tbl


def _render_material_table(
    mt: BookingMaterial,
    doc_width: float,
    normal: ParagraphStyle,
    bold: ParagraphStyle,
    center: ParagraphStyle,
    money_right: ParagraphStyle,
    money_right_bold: ParagraphStyle,
) -> Table:
    mode = (mt.mode or "").upper().strip() or "ITEM"
    if mode == "ITEM":
        return _render_material_table_item(mt, doc_width, normal, bold, center, money_right, money_right_bold)
    if mode == "LUMPSUM":
        return _render_material_table_lumpsum(mt, doc_width, normal, bold, center, money_right, money_right_bold)
    return _render_material_table_attached(mt, doc_width, normal, bold, money_right)


# =============================================================================
# PDF generator
# =============================================================================

def generate_placement_advice_pdf(snapshot: Dict[str, Any], out_path: Path) -> None:
    _register_verdana_fonts()

    styles = getSampleStyleSheet()
    normal = ParagraphStyle(
        "normal",
        parent=styles["Normal"],
        fontName="Verdana",
        fontSize=11,
        leading=12.65,
    )
    bold = ParagraphStyle("bold", parent=normal, fontName="Verdana-Bold")
    right = ParagraphStyle("right", parent=normal, alignment=TA_RIGHT)
    right_bold = ParagraphStyle("right_bold", parent=bold, alignment=TA_RIGHT)

    # For materials alignment
    center = ParagraphStyle("center", parent=normal, alignment=TA_CENTER)
    money_right = ParagraphStyle("money_right", parent=normal, alignment=TA_RIGHT)
    money_right_bold = ParagraphStyle("money_right_bold", parent=bold, alignment=TA_RIGHT)

    booking: Booking = snapshot["booking"]
    ag = snapshot["agreement"]
    trip_serial: int = snapshot["trip_serial"]
    letter_date: date = snapshot["letter_date"]
    letter_no = _build_ref_no(ag.placement_ref_prefix, trip_serial)

    # --- Page X of Y footer canvas ---
    class FooterCanvas(pdfcanvas.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._saved_page_states = []

        def showPage(self):
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total_pages = len(self._saved_page_states)
            for state in self._saved_page_states:
                self.__dict__.update(state)
                self._draw_footer(total_pages)
                super().showPage()
            super().save()

        def _draw_footer(self, total_pages: int):
            self.saveState()
            self.setFont("Verdana", 9)
            y = 10 * mm
            self.drawString(doc.leftMargin, y, letter_no)
            self.drawRightString(
                doc.pagesize[0] - doc.rightMargin,
                y,
                f"Page {self.getPageNumber()} of {total_pages}",
            )
            self.restoreState()

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=12 * mm,
        bottomMargin=16 * mm,
    )

    story: List[Any] = []

    # Letterhead image
    lh = Path(current_app.root_path) / "static" / "letterhead" / "placement_advice_header.png"
    if not lh.exists():
        raise FileNotFoundError(f"Letterhead image not found: {lh}")
    img = Image(str(lh))
    scale = doc.width / img.imageWidth
    img.drawWidth = doc.width
    img.drawHeight = img.imageHeight * scale
    story.append(img)
    story.append(Spacer(1, 6))

    # No / Date line
    no_cell = letter_no
    date_cell = f"Date: {_fmt_date_ddmmyyyy(letter_date)}"
    no_date_tbl = Table([[no_cell, date_cell]], colWidths=[doc.width * 0.65, doc.width * 0.35])
    no_date_tbl.setStyle(TableStyle(_table_base_style() + [
        ("ALIGN", (0, 0), (0, 0), "LEFT"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(no_date_tbl)
    story.append(Spacer(1, 10))

    # Company block
    story.append(Paragraph(f"M/s. {booking.company.name}", bold))
    story.append(Paragraph(f"{booking.company.address}", bold))
    story.append(Spacer(1, 10))

    # Sub/Ref table (WRAPPING FIX)
    sub_ref_rows = [
        [Paragraph("Sub", bold), Paragraph(":", bold), Paragraph("Placement of Lorry for transportation of material – reg.", bold)],
        [Paragraph("Ref", bold), Paragraph(":", bold), Paragraph(f"LOA No. {ag.loa_number}", normal)],
    ]
    sub_ref_tbl = Table(
        sub_ref_rows,
        colWidths=[22 * mm, 8 * mm, doc.width - (22 * mm + 8 * mm)],
    )
    sub_ref_tbl.setStyle(TableStyle(_table_base_style() + [
        ("ALIGN", (0, 0), (0, -1), "RIGHT"),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("WORDWRAP", (2, 0), (2, -1), "CJK"),
    ]))
    story.append(sub_ref_tbl)
    story.append(Spacer(1, 10))

    # Instruction
    story.append(Paragraph("Please arrange to place lorry as per details given below:", normal))
    story.append(Spacer(1, 8))

    # Details table
    loading: List[BookingAuthority] = snapshot["loading"]
    unloading: List[BookingAuthority] = snapshot["unloading"]

    placement_date_value = booking.placement_date.strftime("%d-%m-%Y") if booking.placement_date else ""

    details = [
        ("Tonnage / Capacity", Paragraph(str(booking.lorry.capacity or ""), normal)),
        ("Carrier Size", Paragraph(booking.lorry.carrier_size or "", normal)),
        ("Placement Date", Paragraph(placement_date_value, bold)),  # VALUE BOLD
        ("Placement at", Paragraph(_authority_block(loading), normal)),
        ("Deliver to", Paragraph(_authority_block(unloading), normal)),
        ("Route Length as per Agmt.", Paragraph(f"{booking.route.total_km} Km" if booking.route else "", normal)),
    ]

    details_rows: List[List[Any]] = []
    for label, value_para in details:
        details_rows.append([Paragraph(label, bold), value_para])

    details_tbl = Table(details_rows, colWidths=[60 * mm, doc.width - 60 * mm])
    details_tbl.setStyle(TableStyle(_table_base_style() + [
        ("GRID", (0, 0), (-1, -1), 0.6, colors.black),
    ]))
    story.append(details_tbl)
    story.append(Spacer(1, 10))

    # Materials intro
    story.append(Paragraph("The material to be loaded are listed below:", normal))
    story.append(Spacer(1, 8))

    # Materials tables
    mts = sorted((booking.material_tables or []), key=lambda m: ((m.sequence_index or 0), (m.id or 0)))

    if not mts:
        story.append(Paragraph("-", normal))
        story.append(Spacer(1, 10))
    else:
        for mt in mts:
            tbl = _render_material_table(mt, doc.width, normal, bold, center, money_right, money_right_bold)
            story.append(tbl)
            story.append(Spacer(1, 6))

            from_ba = mt.booking_authority
            meet_desig = _authority_designation(from_ba) if from_ba else "-"
            # only designation should appear, and be bold
            story.append(Paragraph(f"Authority to meet for collection : {meet_desig}", bold))
            story.append(Spacer(1, 12))

    # Signature block bold
    story.append(Spacer(1, 10))
    story.append(Paragraph("(R. Prashaanth)", right_bold))
    story.append(Paragraph("DEE/RS/ED", right_bold))
    story.append(Paragraph("For Sr.DEE/RS/ED", right_bold))
    story.append(Spacer(1, 12))

    # C/- block
    story.append(Paragraph("C/-", bold))
    story.append(Spacer(1, 4))

    cc_rows: List[List[Any]] = []

    if booking_has_home_authority(booking):
        # Per far-end authority key/value pair
        far_end_bas: List[BookingAuthority] = snapshot.get("far_end_bas") or []
        far_action: str = snapshot.get("far_end_action") or "load"

        if far_end_bas:
            for ba in far_end_bas:
                desig = _authority_designation(ba) or "Far End Authority"
                cc_rows.append([
                    Paragraph(f"{desig} :", bold),
                    Paragraph(
                        f"For kind information & requested to arrange to {far_action} the materials "
                        f"in the Lorry placed by the above-mentioned contractor.",
                        normal,
                    ),
                ])
        else:
            cc_rows.append([
                Paragraph("Far End Authority :", bold),
                Paragraph(
                    f"For kind information & requested to arrange to {far_action} the materials "
                    f"in the Lorry placed by the above-mentioned contractor.",
                    normal,
                ),
            ])

    else:
        # No home authority: separate rows for LOADING and UNLOADING (generic wording)
        loading_bas: List[BookingAuthority] = snapshot.get("loading") or []
        unloading_bas: List[BookingAuthority] = snapshot.get("unloading") or []

        if loading_bas:
            for ba in loading_bas:
                desig = _authority_designation(ba) or "Loading Authority"
                cc_rows.append([
                    Paragraph(f"{desig} :", bold),
                    Paragraph(
                        "For kind information & requested to arrange to load the materials in the Lorry placed "
                        "by the above-mentioned contractor.",
                        normal,
                    ),
                ])
        else:
            cc_rows.append([
                Paragraph("Loading Authority :", bold),
                Paragraph(
                    "For kind information & requested to arrange to load the materials in the Lorry placed "
                    "by the above-mentioned contractor.",
                    normal,
                ),
            ])

        if unloading_bas:
            for ba in unloading_bas:
                desig = _authority_designation(ba) or "Unloading Authority"
                cc_rows.append([
                    Paragraph(f"{desig} :", bold),
                    Paragraph(
                        "For kind information & requested to arrange to unload the materials in the Lorry placed "
                        "by the above-mentioned contractor.",
                        normal,
                    ),
                ])
        else:
            cc_rows.append([
                Paragraph("Unloading Authority :", bold),
                Paragraph(
                    "For kind information & requested to arrange to unload the materials in the Lorry placed "
                    "by the above-mentioned contractor.",
                    normal,
                ),
            ])

    # Static rows
    cc_rows += [
        [Paragraph("SSE/G/ELS/ED :", bold), Paragraph("For necessary follow up action please.", normal)],
        [Paragraph("SSE/Stores/ELS/ED :", bold), Paragraph("For information please.", normal)],
    ]

    cc_tbl = Table(cc_rows, colWidths=[55 * mm, doc.width - 55 * mm])
    cc_tbl.setStyle(TableStyle(_table_base_style() + [
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("WORDWRAP", (1, 0), (1, -1), "CJK"),
    ]))
    story.append(cc_tbl)

    doc.build(story, canvasmaker=FooterCanvas)


def _build_mod_ref_no(prefix: str, trip_serial: int, mod_seq: int) -> str:
    p = (prefix or "").strip().strip("/")
    return f"No.{p}/Transport/Placement/Mod/{trip_serial}/{mod_seq}"


def _safe_text(v: Any) -> str:
    if v is None:
        return "-"
    if isinstance(v, (int, float)):
        return str(v)
    return str(v).strip() or "-"


def _summarize_authority_list(canon_list: List[Dict[str, Any]]) -> str:
    if not canon_list:
        return "-"
    parts = []
    for a in canon_list:
        code = (a.get("location_code") or "").strip()
        title = (a.get("title") or "-").strip()
        parts.append(code or title)
    return ", ".join(parts) if parts else "-"


def _summarize_materials(canon_mts: List[Dict[str, Any]]) -> str:
    if not canon_mts:
        return "-"
    chunks = []
    for mt in canon_mts:
        mode = mt.get("mode") or "ITEM"
        amt = mt.get("total_amount")
        qty = mt.get("total_quantity")
        qu = (mt.get("total_quantity_unit") or "").strip()
        qty_txt = _fmt_qty_unit(qty, qu)
        chunks.append(f"{mode} | Qty: {qty_txt or '-'} | Amt: {_safe_text(amt)}")
    return " ; ".join(chunks)


def _compute_mod_diff(baseline: Dict[str, Any], current: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    # Focus on the fields that matter operationally
    diffs: List[Tuple[str, str, str]] = []

    def ch(label: str, old: Any, new: Any):
        if old != new:
            diffs.append((label, _safe_text(old), _safe_text(new)))

    ch("Placement Date", baseline.get("placement_date"), current.get("placement_date"))
    ch("Loading Authorities", _summarize_authority_list(baseline.get("loading") or []), _summarize_authority_list(current.get("loading") or []))
    ch("Unloading Authorities", _summarize_authority_list(baseline.get("unloading") or []), _summarize_authority_list(current.get("unloading") or []))
    ch("Materials Summary", _summarize_materials(baseline.get("materials") or []), _summarize_materials(current.get("materials") or []))
    ch("Route (Km)", baseline.get("route_total_km"), current.get("route_total_km"))
    ch("Lorry Capacity", baseline.get("lorry_capacity"), current.get("lorry_capacity"))
    ch("Carrier Size", baseline.get("lorry_carrier_size"), current.get("lorry_carrier_size"))

    return diffs

def generate_modification_advice_pdf(
    snapshot: Dict[str, Any],
    base_letter_no: str,
    base_letter_date: date,
    mod_letter_no: str,
    diffs: List[Tuple[str, str, str]],
    out_path: Path,
) -> None:
    _register_verdana_fonts()

    styles = getSampleStyleSheet()
    normal = ParagraphStyle(
        "normal",
        parent=styles["Normal"],
        fontName="Verdana",
        fontSize=11,
        leading=12.65,
    )
    bold = ParagraphStyle("bold", parent=normal, fontName="Verdana-Bold")
    right = ParagraphStyle("right", parent=normal, alignment=TA_RIGHT)
    center = ParagraphStyle("center", parent=normal, alignment=TA_CENTER)

    # For materials alignment (same as Placement Advice)
    money_right = ParagraphStyle("money_right", parent=normal, alignment=TA_RIGHT)
    money_right_bold = ParagraphStyle("money_right_bold", parent=bold, alignment=TA_RIGHT)

    booking: Booking = snapshot["booking"]
    ag = snapshot["agreement"]
    letter_date: date = snapshot["letter_date"]
    trip_serial: int = snapshot["trip_serial"]

    # ---- Letter No ----
    prefix = (ag.placement_ref_prefix or "").strip().strip("/")
    letter_no = f"{prefix} / Transport / Modification / {trip_serial}"

    # Detect if materials changed (so we print full material table(s))
    materials_changed = any(
        (label or "").strip().lower() == "materials summary"
        for (label, _old, _new) in (diffs or [])
    )

    class FooterCanvas(pdfcanvas.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._saved_page_states = []

        def showPage(self):
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total_pages = len(self._saved_page_states)
            for state in self._saved_page_states:
                self.__dict__.update(state)
                self._draw_footer(total_pages)
                super().showPage()
            super().save()

        def _draw_footer(self, total_pages: int):
            self.saveState()
            self.setFont("Verdana", 9)
            y = 10 * mm
            self.drawString(doc.leftMargin, y, letter_no)
            self.drawRightString(
                doc.pagesize[0] - doc.rightMargin,
                y,
                f"Page {self.getPageNumber()} of {total_pages}",
            )
            self.restoreState()

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=12 * mm,
        bottomMargin=16 * mm,
    )

    story: List[Any] = []

    # ---- Letterhead ----
    lh = Path(current_app.root_path) / "static" / "letterhead" / "placement_advice_header.png"
    if lh.exists():
        img = Image(str(lh))
        scale = doc.width / img.imageWidth
        img.drawWidth = doc.width
        img.drawHeight = img.imageHeight * scale
        story.append(img)
        story.append(Spacer(1, 6))

    # ---- No / Date line ----
    no_date_tbl = Table(
        [[letter_no, f"Date : {_fmt_date_ddmmyyyy(letter_date)}"]],
        colWidths=[doc.width * 0.65, doc.width * 0.35],
    )
    no_date_tbl.setStyle(TableStyle(_table_base_style() + [
        ("ALIGN", (0, 0), (0, 0), "LEFT"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(no_date_tbl)
    story.append(Spacer(1, 10))

    # ---- Firm block ----
    story.append(Paragraph(f"M/s. {booking.company.name}", bold))
    story.append(Paragraph(f"{booking.company.address}", bold))
    story.append(Spacer(1, 12))

    # ---- Sub / Ref ----
    ref_rows = [
        [Paragraph("Sub", bold), Paragraph(":", bold), Paragraph("Modification Advice", bold)],
        [Paragraph("Ref", bold), Paragraph(":", bold),
         Paragraph(f"1. LOA No. {ag.loa_number}", normal)],
        ["", "", Paragraph(
            f"2. Placement Advice No. {base_letter_no}, Dated {_fmt_date_ddmmyyyy(base_letter_date)}",
            normal
        )],
    ]

    ref_tbl = Table(
        ref_rows,
        colWidths=[20 * mm, 8 * mm, doc.width - (28 * mm)],
    )
    ref_tbl.setStyle(TableStyle(_table_base_style() + [
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("WORDWRAP", (2, 0), (2, -1), "CJK"),
    ]))
    story.append(ref_tbl)
    story.append(Spacer(1, 10))

    # ---- Divider ----
    story.append(Paragraph("*****", center))
    story.append(Spacer(1, 10))

    # ---- Body ----
    story.append(
        Paragraph(
            "With reference to the above, the details of placement advised has been modified as follows.",
            normal,
        )
    )
    story.append(Spacer(1, 8))

    # ---- Revised values list (NEW VALUES ONLY) ----
    printed_any = False
    if diffs:
        idx = 1
        for (label, _old, new) in diffs:
            # If materials changed, don't print "Materials Summary" line item;
            # instead we will print the full materials table(s) below.
            if (label or "").strip().lower() == "materials summary":
                continue

            story.append(Paragraph(f"{idx}. {label} : {new}", normal))
            story.append(Spacer(1, 4))
            printed_any = True
            idx += 1

    if not printed_any and not materials_changed:
        story.append(Paragraph("No material changes recorded.", normal))

    # ---- If materials changed, print FULL material table(s) like Placement Advice ----
    if materials_changed:
        story.append(Spacer(1, 8))
        story.append(Paragraph("Revised material details are as follows:", normal))
        story.append(Spacer(1, 8))

        mts = sorted((booking.material_tables or []), key=lambda m: ((m.sequence_index or 0), (m.id or 0)))

        if not mts:
            story.append(Paragraph("-", normal))
            story.append(Spacer(1, 6))
        else:
            for mt in mts:
                tbl = _render_material_table(mt, doc.width, normal, bold, center, money_right, money_right_bold)
                story.append(tbl)
                story.append(Spacer(1, 6))

                from_ba = mt.booking_authority
                meet_desig = _authority_designation(from_ba) if from_ba else "-"
                story.append(Paragraph(f"Authority to meet for collection : {meet_desig}", bold))
                story.append(Spacer(1, 12))

    # ---- Signature ----
    story.append(Spacer(1, 18))
    story.append(Paragraph("(R. Prashaanth)", right))
    story.append(Paragraph("DEE/RS/ED", right))
    story.append(Paragraph("For Sr.DEE/RS/ED", right))

    doc.build(story, canvasmaker=FooterCanvas)

# =============================================================================
# Routes
# =============================================================================

@admin_bp.route("/letters/placement/<int:booking_id>", methods=["GET", "POST"])
def generate_placement_advice(booking_id: int):
    booking = Booking.query.get_or_404(booking_id)

    letter_type_base = "PLACEMENT"

    baseline_letter = (
        BookingLetter.query
        .filter_by(booking_id=booking.id, letter_type=letter_type_base)
        .order_by(BookingLetter.sequence_no.asc())
        .first()
    )

    if request.method == "GET":
        letter_type_base = "PLACEMENT"
        baseline_letter = (
            BookingLetter.query
            .filter_by(booking_id=booking.id, letter_type=letter_type_base)
            .order_by(BookingLetter.sequence_no.asc())
            .first()
        )

        # ✅ If asked, download the already-issued baseline Placement Advice PDF
        if request.args.get("download") == "1":
            if not baseline_letter or not baseline_letter.pdf_path:
                flash("No issued Placement Advice PDF found for this booking.", "error")
                return redirect(url_for("admin.generate_placement_advice", booking_id=booking.id))

            pdf_path = Path(baseline_letter.pdf_path)
            if not pdf_path.exists():
                flash("Issued Placement Advice PDF is missing from storage.", "error")
                return redirect(url_for("admin.generate_placement_advice", booking_id=booking.id))

            return send_file(
                str(pdf_path),
                as_attachment=True,
                download_name=_clean_filename_keep_spaces(pdf_path.name),
                mimetype="application/pdf",
            )

    if booking.is_cancelled:
        flash("Cannot generate Placement Advice for a CANCELLED booking.", "error")
        return redirect(url_for("admin.booking_detail", booking_id=booking.id))

    requires_attachment = booking_requires_attachment_pdf(booking)

    if request.method == "GET":
        letter_type_base = "PLACEMENT"
        baseline_letter = (
            BookingLetter.query
            .filter_by(booking_id=booking.id, letter_type=letter_type_base)
            .order_by(BookingLetter.sequence_no.asc())
            .first()
        )

        baseline_has_snapshot = False
        changes_detected = False

        if baseline_letter and baseline_letter.snapshot_json:
            base_canon = baseline_letter.snapshot_json.get("canonical")
            base_hash_stored = baseline_letter.snapshot_json.get("content_hash")

            baseline_has_snapshot = bool(base_canon and base_hash_stored)

            if baseline_has_snapshot:
                # ✅ Recompute baseline hash using current hash rules (letter_date excluded)
                base_hash = _hash_canonical_snapshot(base_canon)

                # ✅ Compute current hash from current booking state
                current_canon = build_canonical_snapshot_for_placement(booking, date.today())
                current_hash = _hash_canonical_snapshot(current_canon)

                changes_detected = (current_hash != base_hash)

        return render_template(
            "admin/letters/placement_advice.html",
            booking=booking,
            requires_attachment=(requires_attachment and baseline_letter is None),
            default_letter_date=date.today().isoformat(),
            baseline_letter=baseline_letter,
            baseline_has_snapshot=baseline_has_snapshot,
            changes_detected=changes_detected,
        )


    letter_date_str = (request.form.get("letter_date") or "").strip()
    try:
        letter_date_val = date.fromisoformat(letter_date_str) if letter_date_str else date.today()
    except ValueError:
        flash("Invalid letter date.", "error")
        return redirect(url_for("admin.generate_placement_advice", booking_id=booking.id))

    uploaded_path: Optional[Path] = None
    original_name: Optional[str] = None

    # Attachment is required ONLY when issuing the first (baseline) Placement Advice.
    if requires_attachment and baseline_letter is None:
        f = request.files.get("attachment_pdf")
        if not f or not f.filename:
            flash("Attachment PDF is required because materials are in ATTACHED mode.", "error")
            return redirect(url_for("admin.generate_placement_advice", booking_id=booking.id))
        if not _is_pdf_filename(f.filename):
            flash("Attachment must be a PDF file.", "error")
            return redirect(url_for("admin.generate_placement_advice", booking_id=booking.id))


    snapshot = build_snapshot(booking, letter_date_val)
    current_canon = build_canonical_snapshot_for_placement(booking, letter_date_val)
    current_hash = _hash_canonical_snapshot(current_canon)

    # -------------------------------------------------------------------------
    # Enforce: Placement Advice is FINAL.
    # If baseline exists:
    #   - if unchanged -> serve stored baseline PDF
    #   - if changed   -> issue Modification Advice (do NOT regenerate baseline)
    # -------------------------------------------------------------------------

    if baseline_letter is not None:
        base_snapshot = (baseline_letter.snapshot_json or {})
        base_canon = base_snapshot.get("canonical")
        base_hash = base_snapshot.get("content_hash")

        # Backward compatible: recompute baseline hash from canonical using current rules
        # (letter_date excluded from hash).
        if base_canon:
            base_hash = _hash_canonical_snapshot(base_canon)

        # If we don't have canonical+hash stored for the baseline (older records),
        # we cannot auto-detect changes reliably. Default to serving baseline.
        if not base_canon or not base_hash:
            flash("Baseline Placement Advice exists. Snapshot not stored for auto-change detection; serving issued letter.", "info")
            return send_file(
                str(baseline_letter.pdf_path),
                as_attachment=True,
                download_name=_clean_filename_keep_spaces(Path(baseline_letter.pdf_path).name),
                mimetype="application/pdf",
            )

        if base_hash == current_hash:
            # No changes -> serve baseline PDF (no regeneration)
            return send_file(
                str(baseline_letter.pdf_path),
                as_attachment=True,
                download_name=_clean_filename_keep_spaces(Path(baseline_letter.pdf_path).name),
                mimetype="application/pdf",
            )

        # Changes exist -> issue Modification Advice
        letter_type_mod = "PLACEMENT_MOD"
        mod_seq = _next_letter_sequence(booking.id, letter_type_mod)
        out_dir = _booking_letters_dir(booking.id)

        mod_pdf = out_dir / f"placement_mod_v{mod_seq:03d}.pdf"

        ag = booking.agreement
        trip_serial = snapshot["trip_serial"]
        base_letter_no = _build_ref_no(ag.placement_ref_prefix, trip_serial)
        base_letter_date = baseline_letter.letter_date or letter_date_val

        mod_letter_no = _build_mod_ref_no(ag.placement_ref_prefix, trip_serial, mod_seq)

        diffs = _compute_mod_diff(base_canon, current_canon)

        generate_modification_advice_pdf(
            snapshot=snapshot,
            base_letter_no=base_letter_no,
            base_letter_date=base_letter_date,
            mod_letter_no=mod_letter_no,
            diffs=diffs,
            out_path=mod_pdf,
        )

        mod_letter = BookingLetter(
            booking_id=booking.id,
            letter_type=letter_type_mod,
            sequence_no=mod_seq,
            letter_date=letter_date_val,
            snapshot_json={
                "base_letter_id": baseline_letter.id,
                "base_letter_type": letter_type_base,
                "base_content_hash": base_hash,
                "content_hash": current_hash,
                "canonical": current_canon,
                "diffs": [{"field": f, "old": o, "new": n} for (f, o, n) in diffs],
            },
            pdf_path=str(mod_pdf),
        )
        db.session.add(mod_letter)
        db.session.commit()

        download_name = _clean_filename_keep_spaces(f"MOD - {Path(mod_pdf).name}")
        return send_file(
            str(mod_pdf),
            as_attachment=True,
            download_name=download_name,
            mimetype="application/pdf",
        )

    letter_type = "PLACEMENT"
    seq = _next_letter_sequence(booking.id, letter_type)
    out_dir = _booking_letters_dir(booking.id)

    base_pdf = out_dir / f"placement_advice_v{seq:03d}.pdf"
    merged_pdf = out_dir / f"placement_advice_v{seq:03d}_merged.pdf"

    generate_placement_advice_pdf(snapshot, base_pdf)

    if requires_attachment:
        f = request.files.get("attachment_pdf")
        assert f is not None
        original_name = f.filename
        safe_name = secure_filename(original_name)
        uploaded_path = out_dir / f"placement_attachment_v{seq:03d}_{safe_name}"
        f.save(str(uploaded_path))

        merge_pdfs(base_pdf, uploaded_path, merged_pdf)
        final_path = merged_pdf
    else:
        final_path = base_pdf

    letter = BookingLetter(
        booking_id=booking.id,
        letter_type=letter_type,
        sequence_no=seq,
        letter_date=letter_date_val,
        snapshot_json={
            "booking_id": booking.id,
            "trip_serial": snapshot["trip_serial"],
            "letter_date": snapshot["letter_date"].isoformat(),
            "content_hash": current_hash,
            "canonical": current_canon,
        },
        pdf_path=str(final_path),
    )
    db.session.add(letter)
    db.session.flush()

    if uploaded_path and original_name:
        att = BookingLetterAttachment(
            booking_letter_id=letter.id,
            stored_path=str(uploaded_path),
            original_filename=original_name,
        )
        db.session.add(att)

    db.session.commit()

    download_name = _download_name_for_placement(snapshot)

    return send_file(
        str(final_path),
        as_attachment=True,
        download_name=download_name,
        mimetype="application/pdf",
    )
