"""
Data-dictionary generator for the database-architect agent.

Produces a Django-oriented Excel data dictionary where each attribute is ONE row.
The header is a THREE-tier banded structure that reproduces the reference layout
exactly, including:

  * merged NEW-schema columns (НАЗВАНИЕ ТАБЛИЦЫ/АТРИБУТА spans 2 cells,
    🆕 ТИП ДАННЫХ spans 3 cells),
  * TWO separate Constraints blocks — one under BACKEND and a second, distinct
    one under FRONTEND (they hold different values), and
  * a "Constraints" band merged above each constraint group.

Column order and grouping are fixed so every schema the agent designs looks the
same and diffs cleanly in review.

Usage (library):

    from data_dictionary_generator import Attribute, build_workbook
    build_workbook([Attribute(table="order", attribute="id", ...)], "out.xlsx",
                   title="Orders module")

Usage (CLI):

    python data_dictionary_generator.py rows.json out.xlsx "Orders module"

Dependencies: openpyxl.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, asdict
from typing import List

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


# --------------------------------------------------------------------------- #
# Column map — reproduces the reference header exactly.
# Each entry: (band, subband, subheader, field_key, merge_span)
#   band      -> top tier (row 1 group): "", "BACKEND", "FRONTEND", "API"
#   subband   -> middle tier (row 2): "", "Constraints", "Filter", "Frontend"
#   subheader -> bottom tier (row 3): the actual column header
#   field_key -> Attribute field this column reads
#   merge_span-> physical cells this logical column occupies (for wide merges)
# --------------------------------------------------------------------------- #
COLUMNS = [
    # ---- META ----
    ("",         "",            "doc",                                             "doc",             1),
    ("",         "",            "ПРОВЕРЕНО",                                        "checked",         1),
    ("",         "",            "СТАТУС",                                           "status",          1),
    ("",         "",            "НАИМЕНОВАНИЕ (LABEL)",                             "label",           1),
    # ---- NEW schema (merged wide) ----
    ("",         "",            "НАЗВАНИЕ ТАБЛИЦЫ/АТРИБУТА",                         "_table_attr",     2),
    ("",         "",            "🆕 ТИП ДАННЫХ",                                    "new_type",        3),
    ("",         "",            "ОПИСАНИЕ",                                         "description",     1),
    # ---- OLD legacy mapping ----
    ("",         "",            "OLD ТАБЛИЦА И АТРИБУТ",                            "old_table_attr",  1),
    ("",         "",            "OLD атрибут ОРИГ.",                               "old_attr_orig",   1),
    ("",         "",            "OLD ТИП ДАННЫХ",                                  "old_type",        1),
    # ---- BACKEND: type + Constraints block + Filter ----
    ("BACKEND",  "",            "ТИП ДАННЫХ",                                      "be_type",         1),
    ("BACKEND",  "Constraints", "auto fields (auto_now, auto_now_add, auto + comment)", "be_auto",    1),
    ("BACKEND",  "Constraints", "unique",                                          "be_unique",       1),
    ("BACKEND",  "Constraints", "choice, наименование модели и параметры",          "be_choice_model", 1),
    ("BACKEND",  "Constraints", "choice / enum parametres",                         "be_choice_enum",  1),
    ("BACKEND",  "Constraints", "nullable / null",                                  "be_nullable",     1),
    ("BACKEND",  "Constraints", "default (value)",                                  "be_default",      1),
    ("BACKEND",  "Constraints", "db_index",                                         "be_db_index",     1),
    ("BACKEND",  "Constraints", "editable",                                         "be_editable",     1),
    ("BACKEND",  "Constraints", "on_delete",                                        "be_on_delete",    1),
    ("BACKEND",  "Constraints", "other validations",                                "be_other",        1),
    ("BACKEND",  "Filter",      "filter",                                           "be_filter",       1),
    # ---- FRONTEND: second, separate Constraints block + Frontend fields ----
    ("FRONTEND", "Constraints", "unique",                                           "fe_unique",       1),
    ("FRONTEND", "Constraints", "choice, наименование модели и параметры",          "fe_choice_model", 1),
    ("FRONTEND", "Constraints", "choice / enum parametres",                         "fe_choice_enum",  1),
    ("FRONTEND", "Constraints", "nullable / null",                                  "fe_nullable",     1),
    ("FRONTEND", "Constraints", "default (value)",                                  "fe_default",      1),
    ("FRONTEND", "Constraints", "db_index",                                         "fe_db_index",     1),
    ("FRONTEND", "Constraints", "editable",                                         "fe_editable",     1),
    ("FRONTEND", "Constraints", "auto fields (auto_now, auto_now_add, auto + comment)", "fe_auto",     1),
    ("FRONTEND", "Constraints", "on_delete",                                        "fe_on_delete",    1),
    ("FRONTEND", "Constraints", "other validations",                                "fe_other",        1),
    ("FRONTEND", "Frontend",    "Table view",                                       "fe_table_view",   1),
    ("FRONTEND", "Frontend",    "input type",                                       "fe_input_type",   1),
    ("FRONTEND", "Frontend",    "required",                                         "fe_required",     1),
    ("FRONTEND", "Frontend",    "max",                                              "fe_max",          1),
    ("FRONTEND", "Frontend",    "disabled",                                         "fe_disabled",     1),
    ("FRONTEND", "Frontend",    "validations",                                      "fe_validations",  1),
    # ---- COMMENTS ----
    ("",         "",            "КОММЕНТАРИИ",                                      "comments",        1),
    ("",         "",            "ЗАДАНИЕ",                                          "task",            1),
    # ---- API ----
    ("API",      "",            "get_index",                                        "api_get_index",   1),
    ("API",      "",            "get_single",                                       "api_get_single",  1),
    ("API",      "",            "create",                                           "api_create",      1),
    ("API",      "",            "update",                                           "api_update",      1),
]

# Column widths keyed by field.
WIDTHS = {
    "doc": 8, "checked": 11, "status": 12, "label": 22,
    "_table_attr": 16, "new_type": 10, "description": 34,
    "old_table_attr": 24, "old_attr_orig": 18, "old_type": 16,
    "be_type": 18, "be_auto": 20, "be_unique": 10, "be_choice_model": 22,
    "be_choice_enum": 20, "be_nullable": 12, "be_default": 14, "be_db_index": 10,
    "be_editable": 10, "be_on_delete": 14, "be_other": 20, "be_filter": 14,
    "fe_unique": 10, "fe_choice_model": 22, "fe_choice_enum": 20, "fe_nullable": 12,
    "fe_default": 14, "fe_db_index": 10, "fe_editable": 10, "fe_auto": 20,
    "fe_on_delete": 14, "fe_other": 20,
    "fe_table_view": 11, "fe_input_type": 13, "fe_required": 10, "fe_max": 8,
    "fe_disabled": 10, "fe_validations": 18,
    "comments": 24, "task": 20,
    "api_get_index": 10, "api_get_single": 10, "api_create": 10, "api_update": 10,
}

BAND_FILL = {
    "":         "D9D9D9",
    "BACKEND":  "BDD7EE",   # blue
    "FRONTEND": "FFE699",   # yellow
    "API":      "D9E1F2",
}
SUBBAND_FILL = {
    "Constraints": "E7E6E6",
    "Filter":      "E7E6E6",
    "Frontend":    "FFF2CC",
}
# NEW-schema columns get a green tint so the "new" side stands out.
NEW_FIELDS = {"_table_attr", "new_type", "description"}
OLD_FIELDS = {"old_table_attr", "old_attr_orig", "old_type"}


@dataclass
class Attribute:
    """One attribute = one row in the data dictionary."""

    # NEW schema core
    table: str
    attribute: str
    new_type: str = ""
    description: str = ""

    # META
    doc: str = ""
    checked: str = ""
    status: str = ""
    label: str = ""

    # OLD legacy mapping
    old_table_attr: str = "🆕"
    old_attr_orig: str = ""
    old_type: str = ""

    # BACKEND type + constraints + filter
    be_type: str = ""            # Django field type; falls back to new_type
    be_auto: str = ""
    be_unique: str = ""
    be_choice_model: str = ""
    be_choice_enum: str = ""
    be_nullable: str = ""
    be_default: str = ""
    be_db_index: str = ""
    be_editable: str = ""
    be_on_delete: str = ""
    be_other: str = ""
    be_filter: str = ""

    # FRONTEND second constraints set (distinct values)
    fe_unique: str = ""
    fe_choice_model: str = ""
    fe_choice_enum: str = ""
    fe_nullable: str = ""
    fe_default: str = ""
    fe_db_index: str = ""
    fe_editable: str = ""
    fe_auto: str = ""
    fe_on_delete: str = ""
    fe_other: str = ""

    # FRONTEND fields
    fe_table_view: str = ""
    fe_input_type: str = ""
    fe_required: str = ""
    fe_max: str = ""
    fe_disabled: str = ""
    fe_validations: str = ""

    # COMMENTS
    comments: str = ""
    task: str = ""

    # API CRUD flags
    api_get_index: str = ""
    api_get_single: str = ""
    api_create: str = ""
    api_update: str = ""

    def resolve(self) -> dict:
        d = asdict(self)
        d["_table_attr"] = f"{self.table}.{self.attribute}" if self.attribute else self.table
        if not d.get("be_type"):
            d["be_type"] = self.new_type
        return d


def _physical_positions():
    """Yield (field_key, band, subband, subheader, start_col, span) with 1-based
    physical columns accounting for merge spans."""
    col = 1
    for band, subband, subheader, key, span in COLUMNS:
        yield key, band, subband, subheader, col, span
        col += span


def build_workbook(
    rows: List[Attribute],
    out_path: str,
    title: str = "Data Dictionary",
    sheet_name: str = "Data Dictionary",
    font_name: str = "Arial",
) -> str:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name[:31]

    thin = Side(style="thin", color="BFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="top", wrap_text=True)

    positions = list(_physical_positions())
    n_phys = positions[-1][4] + positions[-1][5] - 1  # last start + last span - 1

    HEADER_TITLE = 1   # row 1: title banner
    HEADER_BAND = 2    # row 2: top band (BACKEND / FRONTEND / API)
    HEADER_SUB = 3     # row 3: sub-band (Constraints / Filter / Frontend)
    HEADER_COL = 4     # row 4: actual column headers
    DATA_START = 5

    # Row 1: title
    ws.cell(row=HEADER_TITLE, column=1, value=title)
    ws.merge_cells(start_row=HEADER_TITLE, start_column=1, end_row=HEADER_TITLE, end_column=n_phys)
    t = ws.cell(row=HEADER_TITLE, column=1)
    t.font = Font(name=font_name, bold=True, size=13, color="FFFFFF")
    t.fill = PatternFill("solid", fgColor="404040")
    t.alignment = Alignment(horizontal="left", vertical="center")

    # Row 2: top band — merge contiguous physical ranges sharing a band label.
    i = 0
    while i < len(positions):
        key, band, subband, subheader, start, span = positions[i]
        # extend across following columns with same band
        end_i = i
        phys_start = start
        while end_i + 1 < len(positions) and positions[end_i + 1][1] == band:
            end_i += 1
        phys_end = positions[end_i][4] + positions[end_i][5] - 1
        if band:
            ws.merge_cells(start_row=HEADER_BAND, start_column=phys_start,
                           end_row=HEADER_BAND, end_column=phys_end)
            c = ws.cell(row=HEADER_BAND, column=phys_start, value=band)
            c.font = Font(name=font_name, bold=True, size=10)
            c.fill = PatternFill("solid", fgColor=BAND_FILL.get(band, "D9D9D9"))
            c.alignment = center
            c.border = border
        i = end_i + 1

    # Row 3: sub-band — merge contiguous ranges sharing a subband label.
    i = 0
    while i < len(positions):
        key, band, subband, subheader, start, span = positions[i]
        end_i = i
        while end_i + 1 < len(positions) and positions[end_i + 1][2] == subband and positions[end_i + 1][1] == band:
            end_i += 1
        phys_start = start
        phys_end = positions[end_i][4] + positions[end_i][5] - 1
        if subband:
            ws.merge_cells(start_row=HEADER_SUB, start_column=phys_start,
                           end_row=HEADER_SUB, end_column=phys_end)
            c = ws.cell(row=HEADER_SUB, column=phys_start, value=subband)
            c.font = Font(name=font_name, bold=True, size=9, italic=True)
            c.fill = PatternFill("solid", fgColor=SUBBAND_FILL.get(subband, "E7E6E6"))
            c.alignment = center
            c.border = border
        i = end_i + 1

    # Row 4: column headers (merge wide NEW-schema columns across their span).
    for key, band, subband, subheader, start, span in positions:
        if span > 1:
            ws.merge_cells(start_row=HEADER_COL, start_column=start,
                           end_row=HEADER_COL, end_column=start + span - 1)
        c = ws.cell(row=HEADER_COL, column=start, value=subheader)
        c.font = Font(name=font_name, bold=True, size=9)
        fill = BAND_FILL.get(band, "D9D9D9")
        if key in NEW_FIELDS:
            fill = "C6E0B4"   # green for the new schema
        elif key in OLD_FIELDS:
            fill = "F8CBAD"   # orange for legacy
        c.fill = PatternFill("solid", fgColor=fill)
        c.alignment = center
        c.border = border
        # widths
        w = WIDTHS.get(key, 12)
        per = max(6, int(w / span))
        for s in range(span):
            ws.column_dimensions[get_column_letter(start + s)].width = per

    # Data rows.
    for r_off, attr in enumerate(rows):
        r = DATA_START + r_off
        data = attr.resolve()
        for key, band, subband, subheader, start, span in positions:
            if span > 1:
                ws.merge_cells(start_row=r, start_column=start, end_row=r, end_column=start + span - 1)
            value = data.get(key, "")
            c = ws.cell(row=r, column=start, value=value)
            c.font = Font(name=font_name, size=9)
            c.alignment = center if key not in ("description", "label", "comments", "task",
                                                "be_other", "fe_other", "fe_validations") else left
            c.border = border

    # Freeze: keep title/band/sub/header rows and the first four META columns visible.
    ws.freeze_panes = "E5"

    # Auto-filter across the column-header row.
    last_col = get_column_letter(n_phys)
    ws.auto_filter.ref = f"A{HEADER_COL}:{last_col}{max(HEADER_COL, len(rows) + HEADER_COL)}"

    _add_legend_sheet(wb, font_name)
    wb.save(out_path)
    return out_path


def _add_legend_sheet(wb: Workbook, font_name: str) -> None:
    ws = wb.create_sheet("Legend")
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 84
    legend = [
        ("Block", "What it holds / how to fill it"),
        ("META", "doc, ПРОВЕРЕНО (reviewer), СТАТУС (draft/review/done), НАИМЕНОВАНИЕ (human LABEL)."),
        ("NEW (green)", "table.attribute (merged wide), 🆕 ТИП ДАННЫХ (merged wide), ОПИСАНИЕ."),
        ("OLD (orange)", "Legacy mapping. '🆕' = new attribute; else OLD table.attribute, original name, OLD type."),
        ("BACKEND", "ТИП ДАННЫХ + a Constraints block (auto fields, unique, choice model, choice/enum, "
                    "nullable, default, db_index, editable, on_delete, other validations) + Filter."),
        ("FRONTEND", "A SECOND, separate Constraints block (same columns, but frontend-side values) followed "
                     "by Frontend fields: Table view, input type, required, max, disabled, validations."),
        ("COMMENTS", "КОММЕНТАРИИ (review notes) and ЗАДАНИЕ (outstanding task)."),
        ("API", "CRUD exposure flags: get_index, get_single, create, update. Mark ✓ / — ."),
        ("", ""),
        ("Why two Constraints blocks", "The BACKEND block describes the Django model constraint; the FRONTEND "
                                        "block describes how the same attribute is constrained in the UI layer. "
                                        "They can differ (e.g. a field editable in backend but disabled on a form)."),
        ("How to use", "One row per attribute. Keep tables grouped and attribute order stable so reviews diff "
                       "cleanly. Use the AutoFilter on the header row to focus on one table or status."),
    ]
    for r, (a, b) in enumerate(legend, start=1):
        ca = ws.cell(row=r, column=1, value=a)
        cb = ws.cell(row=r, column=2, value=b)
        bold = (r == 1) or a in ("How to use", "Why two Constraints blocks")
        ca.font = Font(name=font_name, bold=bold, size=10)
        cb.font = Font(name=font_name, size=10)
        cb.alignment = Alignment(wrap_text=True, vertical="top")
        if r == 1:
            for c in (ca, cb):
                c.fill = PatternFill("solid", fgColor="404040")
                c.font = Font(name=font_name, bold=True, color="FFFFFF", size=10)


def _rows_from_json(path: str) -> List[Attribute]:
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    valid = set(Attribute.__dataclass_fields__)
    return [Attribute(**{k: v for k, v in item.items() if k in valid}) for item in raw]


# --------------------------------------------------------------------------- #
# Contract export — the SINGLE SOURCE OF TRUTH shared with downstream agents.
#
# The Excel workbook is for humans; this JSON is for machines. Both are built
# from the SAME list of Attribute rows, so they can never disagree. Backend, API,
# and test agents read this contract and must reproduce table names, attribute
# names, types, and the API CRUD flags EXACTLY. The validator in
# assets/contract_validator.py checks generated code against it.
# --------------------------------------------------------------------------- #
def _truthy(value: str) -> bool:
    return str(value).strip().lower() in {"true", "yes", "✓", "y", "1", "да"}


def build_contract(rows: List[Attribute]) -> dict:
    """Group attribute rows into a table-oriented contract dict."""
    tables: dict = {}
    for attr in rows:
        d = attr.resolve()
        t = tables.setdefault(attr.table, {"name": attr.table, "attributes": []})
        t["attributes"].append({
            "name": attr.attribute,
            "label": attr.label,
            "new_type": attr.new_type,
            "description": attr.description,
            "backend": {
                "type": d["be_type"],
                "auto": attr.be_auto,
                "unique": attr.be_unique,
                "choice_model": attr.be_choice_model,
                "choice_enum": attr.be_choice_enum,
                "nullable": attr.be_nullable,
                "default": attr.be_default,
                "db_index": attr.be_db_index,
                "editable": attr.be_editable,
                "on_delete": attr.be_on_delete,
                "other_validations": attr.be_other,
                "filter": attr.be_filter,
            },
            "frontend": {
                "unique": attr.fe_unique,
                "choice_model": attr.fe_choice_model,
                "choice_enum": attr.fe_choice_enum,
                "nullable": attr.fe_nullable,
                "default": attr.fe_default,
                "db_index": attr.fe_db_index,
                "editable": attr.fe_editable,
                "auto": attr.fe_auto,
                "on_delete": attr.fe_on_delete,
                "other_validations": attr.fe_other,
                "table_view": attr.fe_table_view,
                "input_type": attr.fe_input_type,
                "required": attr.fe_required,
                "max": attr.fe_max,
                "disabled": attr.fe_disabled,
                "validations": attr.fe_validations,
            },
            "legacy": {
                "old_table_attr": attr.old_table_attr,
                "old_attr_orig": attr.old_attr_orig,
                "old_type": attr.old_type,
                "is_new": attr.old_table_attr.strip() in ("", "🆕"),
            },
            "api": {
                "get_index": _truthy(attr.api_get_index),
                "get_single": _truthy(attr.api_get_single),
                "create": _truthy(attr.api_create),
                "update": _truthy(attr.api_update),
            },
        })
    return {"version": 1, "tables": list(tables.values())}


def write_contract(rows: List[Attribute], out_path: str) -> str:
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(build_contract(rows), fh, ensure_ascii=False, indent=2)
    return out_path


def build_all(rows: List[Attribute], xlsx_path: str, contract_path: str,
              title: str = "Data Dictionary") -> tuple:
    """Build the Excel workbook and the JSON contract from ONE row list, so the
    human table and the machine contract are guaranteed identical."""
    build_workbook(rows, xlsx_path, title=title)
    write_contract(rows, contract_path)
    return xlsx_path, contract_path


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: python data_dictionary_generator.py rows.json out.xlsx [title] [contract.json]")
        raise SystemExit(1)
    rows_path, out_path = sys.argv[1], sys.argv[2]
    title = sys.argv[3] if len(sys.argv) > 3 else "Data Dictionary"
    contract_path = sys.argv[4] if len(sys.argv) > 4 else None
    rows = _rows_from_json(rows_path)
    build_workbook(rows, out_path, title=title)
    print(f"wrote {out_path}")
    if contract_path:
        write_contract(rows, contract_path)
        print(f"wrote {contract_path}")
