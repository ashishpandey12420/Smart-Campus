"""CSV / XLSX / PDF rendering shared by the export endpoints."""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Sequence

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

PDF_ROW_LIMIT = 5000


def to_csv(headers: Sequence[str], rows: Sequence[Sequence]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerows([["" if v is None else v for v in row] for row in rows])
    # BOM keeps Excel happy with non-ASCII names.
    return buf.getvalue().encode("utf-8-sig")


def to_xlsx(title: str, headers: Sequence[str], rows: Sequence[Sequence]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]

    bold = Font(bold=True, color="FFFFFF", size=11)
    fill = PatternFill("solid", start_color="4F46E5")
    thin = Side(style="thin", color="E2E8F0")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    ws.append(list(headers))
    for cell in ws[1]:
        cell.font = bold
        cell.fill = fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border
    ws.row_dimensions[1].height = 22

    for row in rows:
        ws.append(["" if v is None else v for v in row])

    for idx, header in enumerate(headers, start=1):
        longest = max([len(str(header))] + [len(str(r[idx - 1] or "")) for r in rows[:200]])
        ws.column_dimensions[get_column_letter(idx)].width = min(38, max(12, longest + 3))
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    meta = wb.create_sheet("Export info")
    meta["A1"] = "Smart Campus export"
    meta["A2"] = "Generated"
    meta["B2"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    meta["A3"] = "Rows"
    meta["B3"] = len(rows)
    meta.column_dimensions["A"].width = 18
    meta.column_dimensions["B"].width = 26

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def to_pdf(title: str, headers: Sequence[str], rows: Sequence[Sequence], subtitle: str = "") -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=title,
    )
    styles = getSampleStyleSheet()
    heading = styles["Heading1"]
    heading.textColor = colors.HexColor("#312E81")
    heading.fontSize = 17
    small = styles["Normal"]
    small.fontSize = 8
    small.textColor = colors.HexColor("#475569")

    truncated = len(rows) > PDF_ROW_LIMIT
    shown = rows[:PDF_ROW_LIMIT]

    story = [Paragraph(title, heading)]
    meta_line = f"Smart Campus &nbsp;|&nbsp; generated {datetime.now().strftime('%d %b %Y, %H:%M')} &nbsp;|&nbsp; {len(rows)} record(s)"
    story.append(Paragraph(meta_line, small))
    if subtitle:
        story.append(Paragraph(subtitle, small))
    if truncated:
        story.append(Paragraph(f"Only the first {PDF_ROW_LIMIT} rows are printed — use the Excel export for the full set.", small))
    story.append(Spacer(1, 6 * mm))

    cell_style = styles["Normal"]
    cell_style.fontSize = 7.5
    cell_style.leading = 9

    data = [[Paragraph(f"<b>{h}</b>", cell_style) for h in headers]]
    for row in shown:
        data.append([Paragraph("" if v is None else str(v), cell_style) for v in row])

    table = Table(data, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4F46E5")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return buf.getvalue()
