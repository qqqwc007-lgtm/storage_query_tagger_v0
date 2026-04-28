from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Mapping


DECISION_CARD_MANIFEST_FILENAME = "decision_card_manifest_v1.json"
OPPORTUNITY_REVIEW_FILENAME = "opportunity_review_v1.csv"
CALIBRATION_BACKLOG_FILENAME = "calibration_backlog_v1.csv"

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
