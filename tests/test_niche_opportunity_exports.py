from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from storage_taxonomy.niche_opportunity.exports import (
    CALIBRATION_BACKLOG_FILENAME,
    DECISION_CARD_MANIFEST_FILENAME,
    OPPORTUNITY_REVIEW_FILENAME,
    append_calibration_backlog,
    append_opportunity_review,
    escape_spreadsheet_formula,
    write_decision_card_manifest,
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_escape_spreadsheet_formula_only_changes_risky_strings() -> None:
    assert escape_spreadsheet_formula("=SUM(A1:A2)") == "'=SUM(A1:A2)"
    assert escape_spreadsheet_formula("+cmd") == "'+cmd"
    assert escape_spreadsheet_formula("-cmd") == "'-cmd"
    assert escape_spreadsheet_formula("@cmd") == "'@cmd"
    assert escape_spreadsheet_formula("  =SUM(A1:A2)") == "'  =SUM(A1:A2)"
    assert escape_spreadsheet_formula("safe text") == "safe text"
    assert escape_spreadsheet_formula(123) == 123
    assert escape_spreadsheet_formula(None) is None


def test_write_decision_card_manifest_upserts_by_niche_id(tmp_path: Path) -> None:
    path = write_decision_card_manifest(
        tmp_path,
        {
            "niche_id": "under_bed_shoe_storage",
            "card_path": tmp_path / "old.md",
            "conclusion": "建议深挖",
        },
    )

    assert path == tmp_path / DECISION_CARD_MANIFEST_FILENAME

    write_decision_card_manifest(
        path,
        {
            "niche_id": "under_bed_shoe_storage",
            "card_path": tmp_path / "new.md",
            "conclusion": "推荐立项",
            "tags": ("布艺", "塑料"),
        },
    )
    write_decision_card_manifest(
        tmp_path,
        {
            "niche_id": "drawer_divider",
            "card_path": tmp_path / "drawer.md",
            "conclusion": "暂缓观察",
        },
    )

    raw_text = path.read_text(encoding="utf-8")
    rows = json.loads(raw_text)

    assert raw_text.startswith("[\n")
    assert len(rows) == 2
    assert rows[0]["niche_id"] == "under_bed_shoe_storage"
    assert rows[0]["card_path"] == str(tmp_path / "new.md")
    assert rows[0]["conclusion"] == "推荐立项"
    assert rows[0]["tags"] == ["布艺", "塑料"]
    assert rows[1]["niche_id"] == "drawer_divider"


def test_append_opportunity_review_validates_outcome_and_reason(
    tmp_path: Path,
) -> None:
    path = append_opportunity_review(
        tmp_path,
        {
            "reviewed_at": "2026-04-29",
            "reviewer": "+ops",
            "niche_id": "under_bed_shoe_storage",
            "outcome": "approve",
            "system_conclusion": "推荐立项",
            "system_reason": "=proxy evidence cap checked",
            "review_comment": "@approved",
            "card_path": "-card.md",
        },
    )

    assert path == tmp_path / OPPORTUNITY_REVIEW_FILENAME
    rows = _read_csv(path)
    assert rows == [
        {
            "reviewed_at": "2026-04-29",
            "reviewer": "'+ops",
            "niche_id": "under_bed_shoe_storage",
            "review_outcome": "approve",
            "system_conclusion": "推荐立项",
            "system_reason": "'=proxy evidence cap checked",
            "rejection_type": "",
            "review_comment": "'@approved",
            "decision_card_path": "'-card.md",
        }
    ]

    with pytest.raises(ValueError, match="defer/reject"):
        append_opportunity_review(
            tmp_path,
            {
                "niche_id": "under_bed_shoe_storage",
                "review_outcome": "reject",
            },
        )

    with pytest.raises(ValueError, match="review_outcome"):
        append_opportunity_review(
            tmp_path,
            {
                "niche_id": "under_bed_shoe_storage",
                "review_outcome": "hold",
            },
        )


def test_append_calibration_backlog_appends_defer_or_reject_only(
    tmp_path: Path,
) -> None:
    path = append_calibration_backlog(
        tmp_path,
        {
            "reviewed_at": "2026-04-29",
            "reviewer": "-ops",
            "niche_id": "under_bed_shoe_storage",
            "outcome": "defer",
            "rejection_type": "evidence_gap",
            "comment": "@needs stronger VOC evidence",
            "system_conclusion": "=推荐立项",
            "card_path": "+card.md",
        },
    )

    assert path == tmp_path / CALIBRATION_BACKLOG_FILENAME
    rows = _read_csv(path)
    assert rows == [
        {
            "created_at": "2026-04-29",
            "reviewer": "'-ops",
            "niche_id": "under_bed_shoe_storage",
            "review_outcome": "defer",
            "rejection_type": "evidence_gap",
            "review_comment": "'@needs stronger VOC evidence",
            "system_conclusion": "'=推荐立项",
            "decision_card_path": "'+card.md",
            "calibration_status": "open",
        }
    ]

    with pytest.raises(ValueError, match="only accepts defer/reject"):
        append_calibration_backlog(
            tmp_path,
            {
                "niche_id": "under_bed_shoe_storage",
                "review_outcome": "approve",
            },
        )
