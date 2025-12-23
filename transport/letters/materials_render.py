# transport/letters/materials_render.py
from __future__ import annotations

from typing import Any, List, Optional, Tuple

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle

from transport.models import BookingMaterial


# =============================================================================
# Formatting helpers (moved from admin/letters.py)
# =============================================================================

def fmt_qty_unit(qty: Optional[float], unit: Optional[str]) -> str:
    if qty is None and not (unit or "").strip():
        return ""
    if qty is None:
        return (unit or "").strip()
    u = (unit or "").strip()
    return f"{qty} {u}".strip()


def fmt_money(v: Optional[float]) -> str:
    if v is None:
        return ""
    try:
        return f"{float(v):.2f}"
    except Exception:
        return str(v)


# =============================================================================
# Table base + styles
# =============================================================================

def table_base_style() -> List[Tuple]:
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


def material_table_style_common(grid: bool = True) -> List[Tuple]:
    cmds = table_base_style()
    if grid:
        cmds += [("GRID", (0, 0), (-1, -1), 0.6, colors.black)]

    cmds += [
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("FONTNAME", (0, 0), (-1, 0), "Verdana-Bold"),

        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),

        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("VALIGN", (0, 1), (0, -1), "MIDDLE"),

        ("ALIGN", (1, 1), (1, -1), "LEFT"),
        ("VALIGN", (1, 1), (1, -1), "TOP"),

        ("ALIGN", (2, 1), (2, -1), "CENTER"),

        ("ALIGN", (-1, 1), (-1, -1), "RIGHT"),
    ]
    return cmds


# =============================================================================
# Column widths
# =============================================================================

def materials_col_widths_item(doc_width: float) -> List[float]:
    w_sl = 16 * mm
    w_qty = 28 * mm
    w_rate = 32 * mm
    w_amt = 32 * mm
    w_desc = doc_width - (w_sl + w_qty + w_rate + w_amt)
    return [w_sl, w_desc, w_qty, w_rate, w_amt]


def materials_col_widths_lumpsum(doc_width: float) -> List[float]:
    w_sl = 16 * mm
    w_qty = 28 * mm
    w_amt = 35 * mm
    w_desc = doc_width - (w_sl + w_qty + w_amt)
    return [w_sl, w_desc, w_qty, w_amt]


def materials_col_widths_attached(doc_width: float) -> List[float]:
    w_sl = 16 * mm
    w_amt = 35 * mm
    w_desc = doc_width - (w_sl + w_amt)
    return [w_sl, w_desc, w_amt]


# =============================================================================
# Renderers
# =============================================================================

def render_material_table_item(
    mt: BookingMaterial,
    doc_width: float,
    normal: ParagraphStyle,
    bold: ParagraphStyle,
    center: ParagraphStyle,
    money_right: ParagraphStyle,
    money_right_bold: ParagraphStyle,
) -> Table:
    cols = materials_col_widths_item(doc_width)

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
                Paragraph(fmt_qty_unit(ln.quantity, ln.unit), center),
                Paragraph(fmt_money(ln.rate), money_right),
                Paragraph(fmt_money(ln.amount), money_right),
            ])

    rows.append([
        "",
        Paragraph("Total", bold),
        Paragraph("", center),
        Paragraph("", money_right),
        Paragraph(fmt_money(total_amt), money_right_bold),
    ])

    tbl = Table(rows, colWidths=cols, repeatRows=1)
    tbl.setStyle(TableStyle(material_table_style_common()))
    return tbl


def render_material_table_lumpsum(
    mt: BookingMaterial,
    doc_width: float,
    normal: ParagraphStyle,
    bold: ParagraphStyle,
    center: ParagraphStyle,
    money_right: ParagraphStyle,
    money_right_bold: ParagraphStyle,
) -> Table:
    cols = materials_col_widths_lumpsum(doc_width)
    header = ["Sl no", "Description", "Qty/Unit", "Amount (Rs.)"]

    rows: List[List[Any]] = []
    rows.append([Paragraph(h, bold) for h in header])

    lines = sorted(mt.lines or [], key=lambda x: x.sequence_index or 0)
    any_line_qty = any((ln.quantity is not None) for ln in lines)

    if not lines:
        qty_cell = fmt_qty_unit(mt.total_quantity, mt.total_quantity_unit) if not any_line_qty else ""
        rows.append([
            "1",
            Paragraph("-", normal),
            Paragraph(qty_cell, center),
            Paragraph(fmt_money(mt.total_amount), money_right),
        ])
        tbl = Table(rows, colWidths=cols, repeatRows=1)
        tbl.setStyle(TableStyle(material_table_style_common()))
        return tbl

    header_qty_text = fmt_qty_unit(mt.total_quantity, mt.total_quantity_unit) if not any_line_qty else ""

    for i, ln in enumerate(lines, start=1):
        qty_cell = fmt_qty_unit(ln.quantity, ln.unit) if any_line_qty else (header_qty_text if i == 1 else "")
        amt_cell = fmt_money(mt.total_amount) if i == 1 else ""

        rows.append([
            str(i),
            Paragraph((ln.description or "").replace("\n", "<br/>"), normal),
            Paragraph(qty_cell, center),
            Paragraph(amt_cell, money_right),
        ])

    body_start = 1
    body_end = body_start + len(lines) - 1

    tbl = Table(rows, colWidths=cols, repeatRows=1)
    style_cmds = material_table_style_common()

    if len(lines) > 1:
        style_cmds.append(("SPAN", (3, body_start), (3, body_end)))
        style_cmds.append(("VALIGN", (3, body_start), (3, body_end), "MIDDLE"))

    if not any_line_qty and len(lines) > 1:
        style_cmds.append(("SPAN", (2, body_start), (2, body_end)))
        style_cmds.append(("VALIGN", (2, body_start), (2, body_end), "MIDDLE"))

    tbl.setStyle(TableStyle(style_cmds))
    return tbl


def render_material_table_attached(
    mt: BookingMaterial,
    doc_width: float,
    normal: ParagraphStyle,
    bold: ParagraphStyle,
    money_right: ParagraphStyle,
) -> Table:
    cols = materials_col_widths_attached(doc_width)
    header = ["Sl no", "Description", "Amount (Rs.)"]

    rows: List[List[Any]] = []
    rows.append([Paragraph(h, bold) for h in header])
    rows.append([
        "1",
        Paragraph("As per list attached", normal),
        Paragraph(fmt_money(mt.total_amount), money_right),
    ])

    tbl = Table(rows, colWidths=cols, repeatRows=1)
    tbl.setStyle(TableStyle(material_table_style_common()))
    return tbl


def render_material_table(
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
        return render_material_table_item(mt, doc_width, normal, bold, center, money_right, money_right_bold)
    if mode == "LUMPSUM":
        return render_material_table_lumpsum(mt, doc_width, normal, bold, center, money_right, money_right_bold)
    return render_material_table_attached(mt, doc_width, normal, bold, money_right)
