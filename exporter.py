"""
Export helpers — openpyxl (.xlsx) and csv (.csv).
"""
from __future__ import annotations

import csv
import io
from datetime import datetime

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side


# ── Column definitions ─────────────────────────────────────────────────────────

HEADERS = ["Name", "Address", "Phone", "Website", "Rating", "Reviews"]
FIELDS  = ["name", "address", "phone", "website", "rating", "reviews"]

# Column widths (characters)
COL_WIDTHS = [32, 42, 18, 38, 10, 12]

# ARGB colours (openpyxl format: AA RR GG BB)
_GREEN      = "FF16A34A"   # brand accent
_GREEN_LIGHT = "FFF0FDF4"  # accent-light
_WHITE      = "FFFFFFFF"
_ALT_ROW    = "FFF7FBF7"   # very light green tint for even rows
_GREY_TEXT  = "FF555555"

_THIN = Side(border_style="thin", color="FFE5E7EB")
_CELL_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


# ── Public API ─────────────────────────────────────────────────────────────────

def to_xlsx(results: list[dict], query: str) -> bytes:
    """Return an openpyxl workbook as bytes with styled headers and auto-sized columns."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Leads"

    _write_title_row(ws, query, len(results))
    _write_header_row(ws)
    _write_data_rows(ws, results)
    _apply_column_widths(ws)
    ws.freeze_panes = "A4"  # freeze title + header

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def to_csv(results: list[dict]) -> bytes:
    """Return CSV bytes (UTF-8 with BOM so Excel opens it correctly)."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(HEADERS)   # capitalized header row
    for row in results:
        writer.writerow([str(row.get(f, "") or "") for f in FIELDS])
    # UTF-8 BOM (EF BB BF) makes Excel auto-detect the encoding on open
    return buf.getvalue().encode("utf-8-sig")


# ── XLSX internals ─────────────────────────────────────────────────────────────

def _write_title_row(ws, query: str, count: int) -> None:
    ws.merge_cells("A1:F1")
    c = ws["A1"]
    c.value = f"Google Maps Leads — {query}"
    c.font      = Font(name="Calibri", bold=True, size=13, color=_WHITE)
    c.fill      = PatternFill("solid", fgColor=_GREEN)
    c.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[1].height = 28

    ws.merge_cells("A2:F2")
    c = ws["A2"]
    c.value = (
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        f"  |  Total results: {count}"
    )
    c.font      = Font(name="Calibri", size=10, color=_GREY_TEXT)
    c.fill      = PatternFill("solid", fgColor=_GREEN_LIGHT)
    c.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[2].height = 18


def _write_header_row(ws) -> None:
    h_font  = Font(name="Calibri", bold=True, size=11, color=_WHITE)
    h_fill  = PatternFill("solid", fgColor=_GREEN)
    h_align = Alignment(horizontal="center", vertical="center")
    for col, header in enumerate(HEADERS, start=1):
        c = ws.cell(row=3, column=col, value=header)
        c.font      = h_font
        c.fill      = h_fill
        c.alignment = h_align
        c.border    = _CELL_BORDER
    ws.row_dimensions[3].height = 22


def _write_data_rows(ws, results: list[dict]) -> None:
    d_font        = Font(name="Calibri", size=11)
    align_left    = Alignment(horizontal="left",   vertical="center")
    align_center  = Alignment(horizontal="center", vertical="center")
    alt_fill      = PatternFill("solid", fgColor=_ALT_ROW)

    for r_idx, row in enumerate(results, start=4):
        fill = alt_fill if r_idx % 2 == 1 else None
        for c_idx, field in enumerate(FIELDS, start=1):
            val = str(row.get(field, "") or "")
            c = ws.cell(row=r_idx, column=c_idx, value=val)
            c.font      = d_font
            c.border    = _CELL_BORDER
            c.alignment = align_center if field in ("rating", "reviews") else align_left
            if fill:
                c.fill = fill
        ws.row_dimensions[r_idx].height = 18


def _apply_column_widths(ws) -> None:
    for col_letter, width in zip("ABCDEF", COL_WIDTHS):
        ws.column_dimensions[col_letter].width = width
