# transport/letters/pdf_placement.py
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Dict, List

from flask import current_app
from reportlab.lib import colors
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

from transport.models import Booking, BookingAuthority

from transport.letters.materials_render import render_material_table
from transport.letters.pdf_common import (
    authority_block,
    authority_designation,
    build_ref_no,
    fmt_date_ddmmyyyy,
    format_company_contact_block,
    register_verdana_fonts,
)
from transport.letters.snapshots import booking_has_home_authority
from transport.letters.signatories import signature_lines


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


def generate_placement_advice_pdf(snapshot: Dict[str, Any], out_path: Path) -> None:
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
    right_bold = ParagraphStyle("right_bold", parent=bold, alignment=TA_RIGHT)
    center = ParagraphStyle("center", parent=normal, alignment=TA_CENTER)
    money_right = ParagraphStyle("money_right", parent=normal, alignment=TA_RIGHT)
    money_right_bold = ParagraphStyle("money_right_bold", parent=bold, alignment=TA_RIGHT)

    booking: Booking = snapshot["booking"]
    ag = snapshot["agreement"]
    trip_serial: int = snapshot["trip_serial"]
    letter_date: date = snapshot["letter_date"]
    letter_no = build_ref_no(ag.placement_ref_prefix, trip_serial)

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
    if not lh.exists():
        raise FileNotFoundError(f"Letterhead image not found: {lh}")

    img = Image(str(lh))
    scale = doc.width / img.imageWidth
    img.drawWidth = doc.width
    img.drawHeight = img.imageHeight * scale
    story.append(img)
    story.append(Spacer(1, 6))

    no_cell = letter_no
    date_cell = f"Date: {fmt_date_ddmmyyyy(letter_date)}"
    no_date_tbl = Table([[no_cell, date_cell]], colWidths=[doc.width * 0.65, doc.width * 0.35])
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
    story.append(Spacer(1, 10))

    sub_ref_rows = [
        [
            Paragraph("Sub", bold),
            Paragraph(":", bold),
            Paragraph("Placement of Lorry for transportation of material – reg.", bold),
        ],
        [
            Paragraph("Ref", bold),
            Paragraph(":", bold),
            Paragraph(f"LOA No. {ag.loa_number}", normal),
        ],
    ]
    sub_ref_tbl = Table(
        sub_ref_rows,
        colWidths=[22 * mm, 8 * mm, doc.width - (22 * mm + 8 * mm)],
    )
    sub_ref_tbl.setStyle(
        TableStyle(
            _table_base_style()
            + [
                ("ALIGN", (0, 0), (0, -1), "RIGHT"),
                ("ALIGN", (1, 0), (1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("WORDWRAP", (2, 0), (2, -1), "CJK"),
            ]
        )
    )
    story.append(sub_ref_tbl)
    story.append(Spacer(1, 10))

    story.append(Paragraph("Please arrange to place lorry as per details given below:", normal))
    story.append(Spacer(1, 8))

    loading: List[BookingAuthority] = snapshot["loading"]
    unloading: List[BookingAuthority] = snapshot["unloading"]

    placement_date_value = booking.placement_date.strftime("%d-%m-%Y") if booking.placement_date else ""
    tonnage_text = booking.lorry.display_capacity if booking.lorry else ""

    details = [
        ("Tonnage / Capacity", Paragraph(tonnage_text, normal)),
        ("Carrier Size", Paragraph(booking.lorry.carrier_size or "", normal)),
        ("Placement Date", Paragraph(placement_date_value, bold)),
        ("Placement at", Paragraph(authority_block(loading), normal)),
        ("Deliver to", Paragraph(authority_block(unloading), normal)),
        ("Route Length as per Agmt.", Paragraph(f"{booking.route.total_km} Km" if booking.route else "", normal)),
    ]

    details_rows: List[List[Any]] = []
    for label, value_para in details:
        details_rows.append([Paragraph(label, bold), value_para])

    details_tbl = Table(details_rows, colWidths=[60 * mm, doc.width - 60 * mm])
    details_tbl.setStyle(
        TableStyle(
            _table_base_style()
            + [
                ("GRID", (0, 0), (-1, -1), 0.6, colors.black),
            ]
        )
    )
    story.append(details_tbl)
    story.append(Spacer(1, 10))

    story.append(Paragraph("The material to be loaded are listed below:", normal))
    story.append(Spacer(1, 8))

    mts = sorted((booking.material_tables or []), key=lambda m: ((m.sequence_index or 0), (m.id or 0)))

    if not mts:
        story.append(Paragraph("-", normal))
        story.append(Spacer(1, 10))
    else:
        for mt in mts:
            tbl = render_material_table(mt, doc.width, normal, bold, center, money_right, money_right_bold)
            story.append(tbl)
            story.append(Spacer(1, 6))

            from_ba = mt.booking_authority
            meet_desig = authority_designation(from_ba) if from_ba else "-"
            story.append(Paragraph(f"Authority to meet for collection : {meet_desig}", bold))
            story.append(Spacer(1, 12))

    story.append(Spacer(3, 10))

    # Signature lines: compute from signed_by/signed_for as provided by snapshots.py
    signed_by = snapshot.get("signed_by")
    signed_for = snapshot.get("signed_for")
    for line in signature_lines(signed_by=signed_by, signed_for=signed_for):
        story.append(Paragraph(line, right_bold))
    story.append(Spacer(1, 12))

    story.append(Paragraph("C/-", bold))
    story.append(Spacer(1, 4))

    cc_rows: List[List[Any]] = []

    if booking_has_home_authority(booking):
        far_end_bas: List[BookingAuthority] = snapshot.get("far_end_bas") or []
        far_action: str = snapshot.get("far_end_action") or "load"

        if far_end_bas:
            for ba in far_end_bas:
                desig = authority_designation(ba) or "Far End Authority"
                cc_rows.append(
                    [
                        Paragraph(f"{desig} :", bold),
                        Paragraph(
                            f"For kind information & requested to arrange to {far_action} the materials "
                            f"in the Lorry placed by the above-mentioned contractor.",
                            normal,
                        ),
                    ]
                )
        else:
            cc_rows.append(
                [
                    Paragraph("Far End Authority :", bold),
                    Paragraph(
                        f"For kind information & requested to arrange to {far_action} the materials "
                        f"in the Lorry placed by the above-mentioned contractor.",
                        normal,
                    ),
                ]
            )
    else:
        loading_bas: List[BookingAuthority] = snapshot.get("loading") or []
        unloading_bas: List[BookingAuthority] = snapshot.get("unloading") or []

        if loading_bas:
            for ba in loading_bas:
                desig = authority_designation(ba) or "Loading Authority"
                cc_rows.append(
                    [
                        Paragraph(f"{desig} :", bold),
                        Paragraph(
                            "For kind information & requested to arrange to load the materials in the Lorry placed "
                            "by the above-mentioned contractor.",
                            normal,
                        ),
                    ]
                )
        else:
            cc_rows.append(
                [
                    Paragraph("Loading Authority :", bold),
                    Paragraph(
                        "For kind information & requested to arrange to load the materials in the Lorry placed "
                        "by the above-mentioned contractor.",
                        normal,
                    ),
                ]
            )

        if unloading_bas:
            for ba in unloading_bas:
                desig = authority_designation(ba) or "Unloading Authority"
                cc_rows.append(
                    [
                        Paragraph(f"{desig} :", bold),
                        Paragraph(
                            "For kind information & requested to arrange to unload the materials in the Lorry placed "
                            "by the above-mentioned contractor.",
                            normal,
                        ),
                    ]
                )
        else:
            cc_rows.append(
                [
                    Paragraph("Unloading Authority :", bold),
                    Paragraph(
                        "For kind information & requested to arrange to unload the materials in the Lorry placed "
                        "by the above-mentioned contractor.",
                        normal,
                    ),
                ]
            )

    cc_rows += [
        [Paragraph("SSE/G/ELS/ED :", bold), Paragraph("For necessary follow up action please.", normal)],
        [Paragraph("SSE/Stores/ELS/ED :", bold), Paragraph("For information please.", normal)],
    ]

    cc_tbl = Table(cc_rows, colWidths=[55 * mm, doc.width - 55 * mm])
    cc_tbl.setStyle(
        TableStyle(
            _table_base_style()
            + [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("WORDWRAP", (1, 0), (1, -1), "CJK"),
            ]
        )
    )
    story.append(cc_tbl)

    doc.build(story, canvasmaker=FooterCanvas)
