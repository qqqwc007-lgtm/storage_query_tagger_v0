from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from storage_taxonomy.dashboard import DashboardBuildConfig, build_keyword_dashboard


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_build_keyword_dashboard_outputs_contracts_and_ready_top10(tmp_path: Path) -> None:
    kw_csv = tmp_path / "kw.csv"
    _write_csv(
        kw_csv,
        [
            {
                "keyword": "under sink organizer pull out drawer",
                "rank": 1400,
                "scene": "under_sink",
                "need": "space_saving",
                "form": "pull_out_drawer",
                "object_key": "cleaning_supplies",
                "row_outcome": "mapped",
                "matched_aliases": '["under sink"]',
                "evidence": "pull-out fit for cabinet",
                "unmapped_phrases": "[]",
            },
            {
                "keyword": "under sink sliding drawer organizer",
                "rank": 2400,
                "scene": "under_sink",
                "need": "space_saving",
                "form": "pull_out_drawer",
                "object_key": "cleaning_supplies",
                "row_outcome": "mapped",
                "matched_aliases": '["sliding drawer"]',
                "evidence": "narrow cabinet fit",
                "unmapped_phrases": "[]",
            },
            {
                "keyword": "under sink caddy organizer",
                "rank": 9800,
                "scene": "under_sink",
                "need": "space_saving",
                "form": "pull_out_drawer",
                "object_key": "cleaning_supplies",
                "row_outcome": "partial",
                "matched_aliases": '["caddy"]',
                "evidence": "same use context",
                "unmapped_phrases": '["adhesive"]',
            },
            {
                "keyword": "pantry clear storage bin with lid",
                "rank": 1800,
                "scene": "pantry",
                "need": "visibility",
                "form": "bin",
                "object_key": "dry_goods",
                "row_outcome": "candidate",
                "matched_aliases": '["clear bin"]',
                "evidence": "needs manual validation",
                "unmapped_phrases": "[]",
            },
            {
                "keyword": "mystery organizer thing",
                "rank": 250000,
                "row_outcome": "ambiguous",
                "matched_aliases": "[]",
                "evidence": "",
                "unmapped_phrases": '["thing"]',
            },
        ],
    )

    output_dir = tmp_path / "dashboard"
    artifacts = build_keyword_dashboard(
        DashboardBuildConfig(
            kw_csv_path=kw_csv,
            output_dir=output_dir,
            snapshot_date="2026-04-23",
            write_workbook=False,
        )
    )

    assert artifacts["cluster_fact_v1"].exists()
    assert artifacts["cluster_keyword_bridge_v1"].exists()
    assert artifacts["metric_summary_v1"].exists()
    cluster_rows = _read_csv(artifacts["cluster_fact_v1"])
    ready_rows = [row for row in cluster_rows if row["cluster_quality"] == "ready"]
    candidate_rows = [row for row in cluster_rows if row["cluster_quality"] == "candidate"]
    assert ready_rows, "expected at least one ready cluster"
    assert candidate_rows, "expected at least one candidate cluster"
    assert any(row["include_in_top10"] == "True" for row in ready_rows)
    assert all(row["include_in_top10"] != "True" for row in candidate_rows)

    metric_rows = _read_csv(artifacts["metric_summary_v1"])
    metric_lookup = {row["metric_name"]: row["metric_value"] for row in metric_rows}
    assert metric_lookup["ready_clusters"] == "1"
    assert metric_lookup["watchlist_clusters"] == "1"


def test_build_keyword_dashboard_infers_dimensions_from_keyword_text(tmp_path: Path) -> None:
    kw_csv = tmp_path / "kw.csv"
    _write_csv(
        kw_csv,
        [
            {"keyword": "under sink organizer rack", "rank": 3200},
            {"keyword": "clear pantry bin with lid", "rank": 1100},
            {"keyword": "stackable fridge container", "rank": 5100},
        ],
    )

    artifacts = build_keyword_dashboard(
        DashboardBuildConfig(
            kw_csv_path=kw_csv,
            output_dir=tmp_path / "dashboard",
            snapshot_date="2026-04-23",
            write_workbook=False,
        )
    )

    cluster_rows = _read_csv(artifacts["cluster_fact_v1"])
    scene_keys = {row["scene_key"] for row in cluster_rows}
    form_keys = {row["form_rollup_key"] for row in cluster_rows}
    function_keys = {row["function_key"] for row in cluster_rows}

    assert "under_sink" in scene_keys
    assert "pantry" in scene_keys
    assert "bin" in form_keys or "rack" in form_keys
    assert "organization" in function_keys or "visibility" in function_keys or "stackability" in function_keys


def test_workbook_has_four_visible_sheets_and_hidden_contracts(tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    kw_csv = tmp_path / "kw.csv"
    _write_csv(
        kw_csv,
        [
            {
                "keyword": "under sink organizer pull out drawer",
                "rank": 1400,
                "scene": "under_sink",
                "need": "space_saving",
                "form": "pull_out_drawer",
                "object_key": "cleaning_supplies",
                "row_outcome": "mapped",
            }
        ],
    )

    artifacts = build_keyword_dashboard(
        DashboardBuildConfig(
            kw_csv_path=kw_csv,
            output_dir=tmp_path / "dashboard",
            snapshot_date="2026-04-23",
        )
    )

    workbook = openpyxl.load_workbook(artifacts["workbook"])
    visible_sheets = [ws.title for ws in workbook.worksheets if ws.sheet_state == "visible"]
    hidden_sheets = [ws.title for ws in workbook.worksheets if ws.sheet_state != "visible"]

    assert visible_sheets == [
        "00_Overview",
        "01_Opportunity_Cluster_Matrix",
        "02_Cluster_Drilldown",
        "03_Methodology_And_Definitions",
    ]
    assert {
        "cluster_fact_v1",
        "cluster_keyword_bridge_v1",
        "scene_map",
        "need_map",
        "form_map",
        "metric_summary_v1",
    }.issubset(set(hidden_sheets))
