# transport/letters/pdf_modification.py
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Tuple

from flask import current_app
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from transport.models import Booking, BookingAuthority, BookingMaterial

from transport.letters.materials_render import render_material_table
from transport.letters.pdf_common import (
    authority_designation,
    fmt_date_ddmmyyyy,
    format_company_contact_block,
    register_verdana_fonts,
)
from transport.letters.snapshots import stable_json_hash
from transport.letters.signatories import signature_lines as build_signature_lines

# =============================================================================
# Styling
# =============================================================================

def _table_base_style():
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


def _safe_text(v: Any) -> str:
    if v is None:
        return "-"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v).strip()
    return s if s else "-"


def _fmt_qty_unit(qty: Any, unit: Any) -> str:
    if qty is None and not (unit or "").strip():
        return "-"
    if qty is None:
        return (unit or "").strip() or "-"
    u = (unit or "").strip()
    return f"{qty} {u}".strip()


def _summarize_authority_list(canon_list: List[Dict[str, Any]]) -> str:
    if not canon_list:
        return "-"
    parts: List[str] = []
    for a in canon_list:
        code = (a.get("location_code") or "").strip()
        title = (a.get("title") or "-").strip()
        parts.append(code or title)
    return ", ".join([p for p in parts if p]) or "-"


def _summarize_materials(canon_mts: List[Dict[str, Any]]) -> str:
    """
    Keep this as a short, stable summary line list.
    Canonical snapshot already contains per-table mode/qty/unit/amt.
    """
    if not canon_mts:
        return "-"
    chunks: List[str] = []
    for mt in canon_mts:
        mode = (mt.get("mode") or "ITEM").strip()
        amt = mt.get("total_amount")
        qty = mt.get("total_quantity")
        qu = (mt.get("total_quantity_unit") or "").strip()
        qty_txt = _fmt_qty_unit(qty, qu)
        chunks.append(f"{mode} | Qty: {qty_txt} | Amt: {_safe_text(amt)}")
    return " ; ".join(chunks) if chunks else "-"


def compute_mod_diff(
    baseline_canon: Dict[str, Any],
    current_canon: Dict[str, Any],
) -> List[Tuple[str, str, str]]:
    """
    Returns list of (label, old, new).
    Mirrors the earlier logic from letters.py, but lives here for modularity.

    IMPORTANT:
    - Materials are treated as one special diff row ("Materials Summary") if changed,
      because detailed materials will be printed as tables below when changed.
    """
    diffs: List[Tuple[str, str, str]] = []

    def _iso_to_ddmmyyyy(v: Any) -> Any:
        if not v or not isinstance(v, str):
            return v
        try:
            return date.fromisoformat(v).strftime("%d-%m-%Y")
        except Exception:
            return v

    def ch(label: str, old: Any, new: Any):
        if old != new:
            diffs.append((label, _safe_text(old), _safe_text(new)))

    ch(
        "Placement Date",
        _iso_to_ddmmyyyy(baseline_canon.get("placement_date")),
        _iso_to_ddmmyyyy(current_canon.get("placement_date")),
    )

    ch(
        "Loading Authorities",
        _summarize_authority_list(baseline_canon.get("loading") or []),
        _summarize_authority_list(current_canon.get("loading") or []),
    )
    ch(
        "Unloading Authorities",
        _summarize_authority_list(baseline_canon.get("unloading") or []),
        _summarize_authority_list(current_canon.get("unloading") or []),
    )

    base_mats = baseline_canon.get("materials") or []
    curr_mats = current_canon.get("materials") or []
    if stable_json_hash(base_mats) != stable_json_hash(curr_mats):
        diffs.append(("Materials Summary", "-", "-"))

    ch("Route (Km)", baseline_canon.get("route_total_km"), current_canon.get("route_total_km"))
    ch("Lorry Capacity", baseline_canon.get("lorry_capacity"), current_canon.get("lorry_capacity"))
    ch("Carrier Size", baseline_canon.get("lorry_carrier_size"), current_canon.get("lorry_carrier_size"))

    return diffs


# =============================================================================
# PDF generator: Modification Advice
# =============================================================================

def generate_modification_advice_pdf(
    snapshot: Dict[str, Any],
    base_letter_no: str,
    base_letter_date: date,
    mod_letter_no: str,
    diffs: List[Tuple[str, str, str]],
    out_path: Path,
) -> None:
    """
    Generates the Modification Advice PDF.
    - `snapshot` is the runtime snapshot from snapshots.build_snapshot(...)
    - `diffs` is produced by compute_mod_diff(baseline_canon, current_canon)
    - `mod_letter_no` is accepted as a parameter for compatibility, but the
      printed heading line follows the earlier format rule (prefix / Transport / Modification / trip_serial)
    """
    register_verdana_fonts()

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
    center_p = ParagraphStyle("center_p", parent=normal, alignment=TA_CENTER)

    center = ParagraphStyle("center", parent=normal, alignment=TA_CENTER)
    money_right = ParagraphStyle("money_right", parent=normal, alignment=TA_RIGHT)
    money_right_bold = ParagraphStyle("money_right_bold", parent=bold, alignment=TA_RIGHT)

    booking: Booking = snapshot["booking"]
    ag = snapshot["agreement"]
    letter_date: date = snapshot["letter_date"]
    trip_serial: int = snapshot["trip_serial"]

    # Keep printed letter number consistent with your earlier letters.py behavior
    prefix = (ag.placement_ref_prefix or "").strip().strip("/")
    printed_letter_no = f"{prefix} / Transport / Modification / {trip_serial}"

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
            self.drawString(doc.leftMargin, y, f"Trip No. {trip_serial}")
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

    lh = Path(current_app.root_path) / "static" / "letterhead" / "placement_advice_header.png"
    if lh.exists():
        img = Image(str(lh))
        scale = doc.width / img.imageWidth
        img.drawWidth = doc.width
        img.drawHeight = img.imageHeight * scale
        story.append(img)
        story.append(Spacer(1, 6))

    no_date_tbl = Table(
        [[printed_letter_no, f"Date : {fmt_date_ddmmyyyy(letter_date)}"]],
        colWidths=[doc.width * 0.65, doc.width * 0.35],
    )
    no_date_tbl.setStyle(
        TableStyle(
            _table_base_style()
            + [
                ("ALIGN", (0, 0), (0, 0), "LEFT"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(no_date_tbl)
    story.append(Spacer(1, 10))

    story.append(Paragraph(f"M/s. {booking.company.name}", bold))
    story.append(Paragraph(format_company_contact_block(booking.company), bold))
    story.append(Spacer(1, 12))

    ref_rows = [
        [Paragraph("Sub", bold), Paragraph(":", bold), Paragraph("Modification Advice", bold)],
        [Paragraph("Ref", bold), Paragraph(":", bold), Paragraph(f"1. LOA No. {ag.loa_number}", normal)],
        ["", "", Paragraph(f"2. Placement Advice No. {base_letter_no}, Dated {fmt_date_ddmmyyyy(base_letter_date)}", normal)],
    ]

    ref_tbl = Table(
        ref_rows,
        colWidths=[20 * mm, 8 * mm, doc.width - (28 * mm)],
    )
    ref_tbl.setStyle(
        TableStyle(
            _table_base_style()
            + [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("WORDWRAP", (2, 0), (2, -1), "CJK"),
            ]
        )
    )
    story.append(ref_tbl)
    story.append(Spacer(1, 10))

    story.append(Paragraph("*****", center_p))
    story.append(Spacer(1, 10))

    story.append(
        Paragraph(
            "With reference to the above, the details of placement advised has been modified as follows.",
            normal,
        )
    )
    story.append(Spacer(1, 8))

    printed_any = False
    if diffs:
        idx = 1
        for (label, _old, new) in diffs:
            if (label or "").strip().lower() == "materials summary":
                continue

            # Display capacity text for lorry capacity (matches earlier behavior)
            if (label or "").strip().lower() == "lorry capacity":
                new = booking.lorry.display_capacity if booking.lorry else new

            story.append(Paragraph(f"{idx}. {label} : {new}", normal))
            story.append(Spacer(1, 4))
            printed_any = True
            idx += 1

    if not printed_any and not materials_changed:
        story.append(Paragraph("No material changes recorded.", normal))

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
                tbl = render_material_table(mt, doc.width, normal, bold, center, money_right, money_right_bold)
                story.append(tbl)
                story.append(Spacer(1, 6))

                from_ba = mt.booking_authority
                meet_desig = authority_designation(from_ba) if from_ba else "-"
                story.append(Paragraph(f"Authority to meet for collection : {meet_desig}", bold))
                story.append(Spacer(1, 12))

    story.append(Spacer(2, 18))

    signed_by = snapshot.get("signed_by")
    signed_for = snapshot.get("signed_for")

    lines = build_signature_lines(signed_by=signed_by, signed_for=signed_for) or []
    lines = [(ln or "").strip() for ln in lines if (ln or "").strip()]

    # hard fallback if somehow everything is blank
    if not lines:
        lines = ["(R. Prashaanth)", "DEE/RS/ED", "For Sr.DEE/RS/ED"]

    for line in lines:
        story.append(Paragraph(line, right))

    doc.build(story, canvasmaker=FooterCanvas)

