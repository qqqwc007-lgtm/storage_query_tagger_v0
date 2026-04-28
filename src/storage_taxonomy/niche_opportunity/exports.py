from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping
from xml.sax.saxutils import escape as escape_xml
from zipfile import ZIP_DEFLATED, ZipFile


DECISION_CARD_MANIFEST_FILENAME = "decision_card_manifest_v1.json"
OPPORTUNITY_REVIEW_FILENAME = "opportunity_review_v1.csv"
CALIBRATION_BACKLOG_FILENAME = "calibration_backlog_v1.csv"
BUSINESS_DELIVERY_WORKBOOK_SUFFIX = "_opportunity_delivery_v1.xlsx"

REVIEW_OUTCOMES = frozenset({"approve", "defer", "reject"})
CALIBRATION_OUTCOMES = frozenset({"defer", "reject"})

OPPORTUNITY_REVIEW_FIELDS = (
    "reviewed_at",
    "reviewer",
    "niche_id",
    "review_outcome",
    "system_conclusion",
    "system_reason",
    "rejection_type",
    "review_comment",
    "decision_card_path",
)

CALIBRATION_BACKLOG_FIELDS = (
    "created_at",
    "reviewer",
    "niche_id",
    "review_outcome",
    "rejection_type",
    "review_comment",
    "system_conclusion",
    "decision_card_path",
    "calibration_status",
)

_FORMULA_PREFIXES = ("=", "+", "-", "@")
_INVALID_XML_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


@dataclass(frozen=True)
class XlsxSheet:
    name: str
    headers: tuple[str, ...]
    rows: tuple[tuple[object, ...], ...]


def escape_spreadsheet_formula(value: object) -> object:
    if isinstance(value, str) and value.lstrip().startswith(_FORMULA_PREFIXES):
        return f"'{value}"
    return value


def write_decision_card_manifest(path_or_dir: str | Path, row: Mapping[str, object]) -> Path:
    path = _resolve_output_path(
        path_or_dir,
        DECISION_CARD_MANIFEST_FILENAME,
        ".json",
    )
    new_row = _json_row(row)
    niche_id = _required_text(new_row, "niche_id")

    existing_rows = _read_manifest_rows(path)
    rows: list[dict[str, Any]] = []
    updated = False
    for existing_row in existing_rows:
        existing_niche_id = _clean_text(existing_row.get("niche_id"))
        if existing_niche_id == niche_id:
            if not updated:
                rows.append(new_row)
                updated = True
            continue
        rows.append(existing_row)
    if not updated:
        rows.append(new_row)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def write_xlsx_workbook(path: str | Path, sheets: Iterable[XlsxSheet]) -> Path:
    workbook_path = Path(path)
    if workbook_path.suffix.lower() != ".xlsx":
        raise ValueError("XLSX workbook path must end with .xlsx")
    normalized_sheets = tuple(_normalize_xlsx_sheets(sheets))
    if not normalized_sheets:
        raise ValueError("XLSX workbook requires at least one sheet")

    workbook_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(workbook_path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _xlsx_content_types(len(normalized_sheets)))
        archive.writestr("_rels/.rels", _xlsx_root_rels())
        archive.writestr("xl/workbook.xml", _xlsx_workbook_xml(normalized_sheets))
        archive.writestr("xl/_rels/workbook.xml.rels", _xlsx_workbook_rels(len(normalized_sheets)))
        for index, sheet in enumerate(normalized_sheets, start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _xlsx_sheet_xml(sheet))
    return workbook_path


def append_opportunity_review(path_or_dir: str | Path, row: Mapping[str, object]) -> Path:
    path = _resolve_output_path(
        path_or_dir,
        OPPORTUNITY_REVIEW_FILENAME,
        ".csv",
    )
    normalized = _normalize_review_row(row)
    _required_text(normalized, "niche_id")
    outcome = _required_review_outcome(normalized)
    _validate_review_reason(normalized, outcome)
    _append_csv_row(path, OPPORTUNITY_REVIEW_FIELDS, normalized)
    return path


def append_calibration_backlog(path_or_dir: str | Path, row: Mapping[str, object]) -> Path:
    path = _resolve_output_path(
        path_or_dir,
        CALIBRATION_BACKLOG_FILENAME,
        ".csv",
    )
    normalized = _normalize_review_row(row)
    _required_text(normalized, "niche_id")
    outcome = _required_review_outcome(normalized)
    if outcome not in CALIBRATION_OUTCOMES:
        raise ValueError("calibration backlog only accepts defer/reject outcomes")
    _validate_review_reason(normalized, outcome)
    normalized.setdefault("created_at", normalized.get("reviewed_at", ""))
    normalized.setdefault("calibration_status", "open")
    _append_csv_row(path, CALIBRATION_BACKLOG_FIELDS, normalized)
    return path


def _resolve_output_path(
    path_or_dir: str | Path,
    default_filename: str,
    expected_suffix: str,
) -> Path:
    path = Path(path_or_dir)
    if path.suffix.lower() == expected_suffix:
        return path
    return path / default_filename


def _read_manifest_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path}: decision card manifest must be a JSON list")

    rows: list[dict[str, Any]] = []
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"{path}: manifest row {index} must be an object")
        rows.append(dict(item))
    return rows


def _append_csv_row(
    path: Path,
    fieldnames: tuple[str, ...],
    row: Mapping[str, object],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = True
    if path.exists() and path.stat().st_size > 0:
        with path.open("r", encoding="utf-8", newline="") as handle:
            existing_header = next(csv.reader(handle), None)
        if existing_header != list(fieldnames):
            raise ValueError(f"{path}: existing CSV header does not match contract")
        write_header = False

    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        if write_header:
            writer.writeheader()
        writer.writerow(_project_csv_row(row, fieldnames))


def _project_csv_row(
    row: Mapping[str, object],
    fieldnames: tuple[str, ...],
) -> dict[str, object]:
    projected: dict[str, object] = {}
    for field in fieldnames:
        value = row.get(field, "")
        if value is None:
            value = ""
        projected[field] = escape_spreadsheet_formula(value)
    return projected


def _normalize_review_row(row: Mapping[str, object]) -> dict[str, object]:
    normalized = {str(key): value for key, value in row.items()}
    _copy_alias(normalized, "outcome", "review_outcome")
    _copy_alias(normalized, "comment", "review_comment")
    _copy_alias(normalized, "rejection_reason", "review_comment")
    _copy_alias(normalized, "card_path", "decision_card_path")

    outcome = _clean_text(normalized.get("review_outcome")).lower()
    if outcome:
        normalized["review_outcome"] = outcome
    return normalized


def _copy_alias(row: dict[str, object], source: str, target: str) -> None:
    if target not in row and _clean_text(row.get(source)):
        row[target] = row[source]


def _required_review_outcome(row: Mapping[str, object]) -> str:
    outcome = _required_text(row, "review_outcome").lower()
    if outcome not in REVIEW_OUTCOMES:
        valid = ", ".join(sorted(REVIEW_OUTCOMES))
        raise ValueError(f"review_outcome must be one of: {valid}")
    return outcome


def _validate_review_reason(row: Mapping[str, object], outcome: str) -> None:
    if outcome == "approve":
        return
    rejection_type = _clean_text(row.get("rejection_type"))
    review_comment = _clean_text(row.get("review_comment"))
    if not rejection_type and not review_comment:
        raise ValueError("defer/reject requires rejection_type or review_comment")


def _required_text(row: Mapping[str, object], field: str) -> str:
    value = _clean_text(row.get(field))
    if not value:
        raise ValueError(f"{field} is required")
    return value


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _json_row(row: Mapping[str, object]) -> dict[str, Any]:
    return {str(key): _json_safe(value) for key, value in row.items()}


def _json_safe(value: object) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _normalize_xlsx_sheets(sheets: Iterable[XlsxSheet]) -> list[XlsxSheet]:
    normalized: list[XlsxSheet] = []
    used_names: set[str] = set()
    for index, sheet in enumerate(sheets, start=1):
        name = _unique_sheet_name(_safe_sheet_name(sheet.name or f"Sheet{index}"), used_names)
        if not sheet.headers:
            raise ValueError(f"{sheet.name or f'Sheet{index}'}: sheet headers are required")
        rows: list[tuple[object, ...]] = []
        for row_index, row in enumerate(sheet.rows, start=1):
            if len(row) > len(sheet.headers):
                raise ValueError(f"{sheet.name}: row {row_index} has more values than headers")
            padded = tuple(row) + ("",) * (len(sheet.headers) - len(row))
            rows.append(padded)
        normalized.append(
            XlsxSheet(
                name=name,
                headers=tuple(sheet.headers),
                rows=tuple(rows),
            )
        )
    return normalized


def _safe_sheet_name(value: str) -> str:
    cleaned = re.sub(r"[\[\]:*?/\\]", " ", str(value)).strip()
    return (cleaned or "Sheet")[:31]


def _unique_sheet_name(value: str, used_names: set[str]) -> str:
    base = value[:31] or "Sheet"
    candidate = base
    suffix = 2
    while candidate.lower() in used_names:
        marker = f" {suffix}"
        candidate = f"{base[: 31 - len(marker)]}{marker}"
        suffix += 1
    used_names.add(candidate.lower())
    return candidate


def _xlsx_content_types(sheet_count: int) -> str:
    worksheet_overrides = "\n".join(
        (
            f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
        for index in range(1, sheet_count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
        '<Default Extension="xml" ContentType="application/xml"/>\n'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>\n'
        f"{worksheet_overrides}\n"
        "</Types>\n"
    )


def _xlsx_root_rels() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>\n'
        "</Relationships>\n"
    )


def _xlsx_workbook_xml(sheets: tuple[XlsxSheet, ...]) -> str:
    sheet_rows = "\n".join(
        (
            f'<sheet name="{_xml_text(sheet.name)}" sheetId="{index}" '
            f'r:id="rId{index}"/>'
        )
        for index, sheet in enumerate(sheets, start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">\n'
        "<sheets>\n"
        f"{sheet_rows}\n"
        "</sheets>\n"
        "</workbook>\n"
    )


def _xlsx_workbook_rels(sheet_count: int) -> str:
    rows = "\n".join(
        (
            f'<Relationship Id="rId{index}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{index}.xml"/>'
        )
        for index in range(1, sheet_count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        f"{rows}\n"
        "</Relationships>\n"
    )


def _xlsx_sheet_xml(sheet: XlsxSheet) -> str:
    rows = [sheet.headers, *sheet.rows]
    last_row = max(len(rows), 1)
    last_col = max(len(sheet.headers), 1)
    columns = "\n".join(
        f'<col min="{index}" max="{index}" width="{_column_width(sheet, index - 1)}" customWidth="1"/>'
        for index in range(1, last_col + 1)
    )
    row_xml = "\n".join(
        _xlsx_row_xml(row_index, tuple(row), last_col)
        for row_index, row in enumerate(rows, start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">\n'
        f'<dimension ref="A1:{_column_name(last_col)}{last_row}"/>\n'
        '<sheetViews><sheetView workbookViewId="0"/></sheetViews>\n'
        '<sheetFormatPr defaultRowHeight="15"/>\n'
        f"<cols>\n{columns}\n</cols>\n"
        f"<sheetData>\n{row_xml}\n</sheetData>\n"
        "</worksheet>\n"
    )


def _column_width(sheet: XlsxSheet, column_index: int) -> int:
    values = [sheet.headers[column_index]]
    values.extend(str(row[column_index]) for row in sheet.rows[:30] if column_index < len(row))
    max_len = max((len(value) for value in values), default=12)
    return min(max(max_len + 2, 12), 48)


def _xlsx_row_xml(row_index: int, row: tuple[object, ...], column_count: int) -> str:
    cells = "\n".join(
        _xlsx_cell_xml(row_index, column_index, row[column_index - 1])
        for column_index in range(1, column_count + 1)
    )
    return f'<row r="{row_index}">\n{cells}\n</row>'


def _xlsx_cell_xml(row_index: int, column_index: int, value: object) -> str:
    reference = f"{_column_name(column_index)}{row_index}"
    if _is_xlsx_number(value):
        return f'<c r="{reference}"><v>{value}</v></c>'

    text = "" if value is None else str(escape_spreadsheet_formula(value))
    text = _xml_text(_strip_invalid_xml_chars(text))
    space = ' xml:space="preserve"' if text != text.strip() else ""
    return f'<c r="{reference}" t="inlineStr"><is><t{space}>{text}</t></is></c>'


def _is_xlsx_number(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    return False


def _column_name(column_index: int) -> str:
    name = ""
    index = column_index
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _xml_text(value: str) -> str:
    return escape_xml(value, {'"': "&quot;"})


def _strip_invalid_xml_chars(value: str) -> str:
    return _INVALID_XML_CHARS.sub("", value)
