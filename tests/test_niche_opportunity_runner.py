from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zipfile import ZipFile

import pytest

from storage_taxonomy.niche_opportunity import runner
from storage_taxonomy.niche_opportunity.boundary import BOUNDARY_COLUMNS
from storage_taxonomy.niche_opportunity.loaders import (
    KEYWORD_ASIN_FACT_COLUMNS,
    SEARCH_VOLUME_HISTORY_COLUMNS,
)


def test_generate_card_seeds_boundary_and_writes_outputs(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_keyword_asin_facts(
        tmp_path,
        [
            _keyword_asin_row("under bed shoe storage", "B0A", rank=1, is_new=True, units=100, gmv=2999.0),
            _keyword_asin_row("under bed shoe storage", "B0B", rank=2, is_new=False, units=80, gmv=2000.0),
        ],
    )
    _write_search_history(tmp_path, "under bed shoe storage")
    _write_raw_detail(tmp_path, "B0A", material="Oxford Fabric + PVC")
    _write_raw_detail(tmp_path, "B0B", material="Oxford Fabric")

    result = runner.generate_card(
        niche_id="under_bed_shoe_storage",
        niche_name="under bed shoe storage",
        keywords="under bed shoe storage, under bed shoe storage",
        output_dir=tmp_path / "out",
        config_path=config_path,
    )

    assert result.seeded_boundary is True
    card_text = result.card_path.read_text(encoding="utf-8")
    assert card_text.startswith("# Niche Decision Card: under bed shoe storage")
    assert "## Signal Evidence" in card_text
    assert "- VOC: missing/not enabled in v1" in card_text
    assert result.manifest_path.name == "decision_card_manifest_v1.json"
    assert result.quality_path.name == "niche_opportunity_quality_v1.json"
    assert result.workbook_path.name == "under_bed_shoe_storage_opportunity_delivery_v1.xlsx"
    assert result.workbook_path.exists()
    with ZipFile(result.workbook_path) as archive:
        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
        decision_sheet_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert "立项卡片" in workbook_xml
    assert "信号证据" in workbook_xml
    assert "采购成本" in workbook_xml
    assert "Top ASIN" in workbook_xml
    assert "推荐立项" in decision_sheet_xml
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest[0]["niche_id"] == "under_bed_shoe_storage"
    assert manifest[0]["delivery_workbook_path"].endswith(
        "under_bed_shoe_storage_opportunity_delivery_v1.xlsx"
    )

    boundary_rows = _read_csv(result.boundary_path)
    assert [row["boundary_item_value"] for row in boundary_rows] == ["under bed shoe storage"]
    assert boundary_rows[0]["inclusion_status"] == "included"

    quality = json.loads(result.quality_path.read_text(encoding="utf-8"))
    row = quality["rows"][0]
    assert row["niche_id"] == "under_bed_shoe_storage"
    assert row["included_keyword_count"] == 1
    assert row["selected_product_asin_count"] == 2
    assert row["product_fact_count"] == 2


def test_generate_card_respects_existing_boundary_invalid_asin(
    tmp_path: Path,
) -> None:
    config_path = _write_config(tmp_path)
    _write_keyword_asin_facts(
        tmp_path,
        [
            _keyword_asin_row("under bed shoe storage", "B0A", rank=1, is_new=True, units=100, gmv=2999.0),
            _keyword_asin_row("under bed shoe storage", "B0B", rank=2, is_new=True, units=50, gmv=1499.5),
            _keyword_asin_row("shoe rack", "B0C", rank=1, is_new=True, units=200, gmv=3998.0),
        ],
    )
    _write_search_history(tmp_path, "under bed shoe storage")
    _write_search_history(tmp_path, "shoe rack")
    _write_raw_detail(tmp_path, "B0A", material="Oxford Fabric + PVC")
    _write_raw_detail(tmp_path, "B0C", material="Steel")
    _write_existing_boundary(tmp_path / "out" / runner.BOUNDARY_FILENAME)

    result = runner.generate_card(
        niche_id="under_bed_shoe_storage",
        niche_name="under bed shoe storage",
        keywords="this should not be seeded",
        output_dir=tmp_path / "out",
        config_path=config_path,
    )

    assert result.seeded_boundary is False
    assert result.boundary.included_keywords == ("under bed shoe storage",)
    assert result.boundary.excluded_keywords == ("shoe rack",)
    assert result.boundary.invalid_asins == ("B0B",)
    assert result.boundary.product_asins == ("B0A",)
    assert [fact.asin for fact in result.product_facts] == ["B0A"]

    quality = json.loads(result.quality_path.read_text(encoding="utf-8"))
    row = quality["rows"][0]
    assert row["invalid_asin_count"] == 1
    assert row["selected_product_asin_count"] == 1
    assert row["product_fact_count"] == 1


def test_record_review_validates_reason_and_writes_calibration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, list[dict[str, Any]]] = {"review": [], "backlog": []}

    def fake_review(path_or_dir: str | Path, row: dict[str, Any]) -> Path:
        calls["review"].append(row)
        return Path(path_or_dir) / "opportunity_review_v1.csv"

    def fake_backlog(path_or_dir: str | Path, row: dict[str, Any]) -> Path:
        calls["backlog"].append(row)
        return Path(path_or_dir) / "calibration_backlog_v1.csv"

    monkeypatch.setattr(runner, "append_opportunity_review", fake_review)
    monkeypatch.setattr(runner, "append_calibration_backlog", fake_backlog)

    with pytest.raises(ValueError, match="defer/reject"):
        runner.record_review(
            niche_id="under_bed_shoe_storage",
            reviewer="operations",
            final_conclusion="defer",
            output_dir=tmp_path,
        )

    result = runner.record_review(
        niche_id="under_bed_shoe_storage",
        reviewer="operations",
        final_conclusion="reject",
        rejection_type="logic_issue",
        review_comment="ASIN boundary is too broad",
        output_dir=tmp_path,
        reviewed_at="2026-04-29T00:00:00+00:00",
    )

    assert result.review_path.name == "opportunity_review_v1.csv"
    assert result.calibration_backlog_path is not None
    assert calls["review"][0]["review_outcome"] == "reject"
    assert calls["review"][0]["decision_card_path"].endswith("under_bed_shoe_storage_decision_card.md")
    assert calls["backlog"][0]["review_outcome"] == "reject"
    assert calls["backlog"][0]["rejection_type"] == "logic_issue"

    approve_result = runner.record_review(
        niche_id="under_bed_shoe_storage",
        reviewer="operations",
        final_conclusion="approve",
        output_dir=tmp_path,
    )

    assert approve_result.calibration_backlog_path is None
    assert len(calls["review"]) == 2
    assert len(calls["backlog"]) == 1


def test_record_review_writes_real_review_and_backlog_files(tmp_path: Path) -> None:
    (tmp_path / "decision_card_manifest_v1.json").write_text(
        json.dumps(
            [
                {
                    "niche_id": "under_bed_shoe_storage",
                    "conclusion": "=推荐立项",
                    "decision_reason": "+3 market signals",
                    "decision_card_path": str(tmp_path / "under_bed_shoe_storage_decision_card.md"),
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = runner.record_review(
        niche_id="under_bed_shoe_storage",
        reviewer="+operations",
        final_conclusion="defer",
        rejection_type="evidence_not_enough",
        review_comment="@Need supplier cost confirmation",
        output_dir=tmp_path,
        reviewed_at="2026-04-29T00:00:00+00:00",
    )

    assert result.review_path.name == "opportunity_review_v1.csv"
    assert result.calibration_backlog_path is not None
    review_rows = _read_csv(result.review_path)
    backlog_rows = _read_csv(result.calibration_backlog_path)

    assert review_rows[0]["review_outcome"] == "defer"
    assert review_rows[0]["reviewer"] == "'+operations"
    assert review_rows[0]["system_conclusion"] == "'=推荐立项"
    assert review_rows[0]["system_reason"] == "'+3 market signals"
    assert review_rows[0]["review_comment"] == "'@Need supplier cost confirmation"
    assert backlog_rows[0]["review_outcome"] == "defer"
    assert backlog_rows[0]["system_conclusion"] == "'=推荐立项"
    assert backlog_rows[0]["rejection_type"] == "evidence_not_enough"


def test_cli_args_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script = _load_cli_script()
    calls: dict[str, Any] = {}

    def fake_generate_card(**kwargs: Any) -> Any:
        calls["generate"] = kwargs
        return SimpleNamespace(
            card_path=Path(kwargs["output_dir"]) / "card.md",
            workbook_path=Path(kwargs["output_dir"]) / "delivery.xlsx",
            manifest_path=Path(kwargs["output_dir"]) / "decision_card_manifest_v1.json",
            quality_path=Path(kwargs["output_dir"]) / "niche_opportunity_quality_v1.json",
            decision=SimpleNamespace(conclusion="推荐立项"),
        )

    def fake_record_review(**kwargs: Any) -> Any:
        calls["review"] = kwargs
        return SimpleNamespace(
            review_path=Path(kwargs["output_dir"]) / "opportunity_review_v1.csv",
            calibration_backlog_path=Path(kwargs["output_dir"]) / "calibration_backlog_v1.csv",
        )

    monkeypatch.setattr(script.runner, "generate_card", fake_generate_card)
    monkeypatch.setattr(script.runner, "record_review", fake_record_review)

    assert script.main(
        [
            "generate-card",
            "--niche-id",
            "under_bed_shoe_storage",
            "--niche-name",
            "under bed shoe storage",
            "--keywords",
            "under bed shoe storage,shoe organizer under bed",
            "--output-dir",
            str(tmp_path),
            "--config",
            str(tmp_path / "config.yaml"),
        ]
    ) == 0

    assert calls["generate"]["niche_id"] == "under_bed_shoe_storage"
    assert calls["generate"]["keywords"] == "under bed shoe storage,shoe organizer under bed"
    assert calls["generate"]["config_path"] == str(tmp_path / "config.yaml")

    assert script.main(
        [
            "record-review",
            "--niche-id",
            "under_bed_shoe_storage",
            "--reviewer",
            "operations",
            "--final-conclusion",
            "defer",
            "--rejection-type",
            "evidence_not_enough",
            "--review-comment",
            "Need supplier cost confirmation",
            "--output-dir",
            str(tmp_path),
        ]
    ) == 0

    assert calls["review"]["final_conclusion"] == "defer"
    assert calls["review"]["review_comment"] == "Need supplier cost confirmation"


def _write_config(tmp_path: Path) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "niche_opportunity_v1.yaml"
    config_path.write_text(
        """
workflow_version: niche_opportunity_v1.0
cost:
  target_gross_margin_rate: 0.30
  referral_fee_rate: 0.15
  storage_return_loss_reserve_rate: 0.04
  exchange_rate: 7.20
  first_leg_rmb_per_kg: 8.0
  chargeable_weight_divisor_cm3_per_kg: 6000.0
evidence:
  max_source_age_days: 45
  max_search_history_age_months: 2
  stale_policy: warn
supply_chain:
  material_priority: [fabric, bamboo_wood, steel_frame, plastic]
  composite_material_bonus: 1.0
  lead_time_days:
    fabric: 30
    bamboo_wood: 60
    steel_frame: 60
    plastic: 60
decision_thresholds:
  recommend_market_signal_min: 2
  deep_dive_market_signal_count: 1
  big_volume_monthly_search_volume: 300000
  proxy_only_conclusion_cap: 建议深挖
  unresolved_non_fit_conclusion: 暂缓观察
source_paths:
  keyword_asin_fact: outputs/keyword_asin_fact_v1.csv
  keyword_search_volume_history: outputs/keyword_search_volume_history.csv
  product_detail_raw_dir: outputs/product_detail_raw
""",
        encoding="utf-8",
    )
    return config_path


def _write_keyword_asin_facts(tmp_path: Path, rows: list[dict[str, str]]) -> None:
    output_path = tmp_path / "outputs" / "keyword_asin_fact_v1.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=KEYWORD_ASIN_FACT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _keyword_asin_row(
    search_term: str,
    asin: str,
    *,
    rank: int,
    is_new: bool,
    units: int,
    gmv: float,
) -> dict[str, str]:
    return {
        "canonical_scenario_need": "床下收纳",
        "kw": search_term,
        "kw中文翻译": f"{search_term} zh",
        "rank": str(rank),
        "ASIN": asin,
        "标题": f"{asin} under bed shoe storage",
        "主图": f"https://example.com/{asin}.jpg",
        "品牌": "Brand",
        "卖家": "Seller",
        "价格": "29.99",
        "Units": str(units),
        "GMV": str(gmv),
        "ASIN_ASP": "29.99",
        "上架日期": "2025-10-01",
        "上架天数": "120",
        "星级": "4.6",
        "评论数量": "80",
        "2025-Q3起新品": "true" if is_new else "false",
        "product_detail_status": "cached",
        "product_detail_raw_json": f"/raw/{asin}.json",
        "keyword_top20_asin_list_json": "[]",
        "source_record_json": "{}",
    }


def _write_search_history(tmp_path: Path, search_term: str) -> None:
    output_path = tmp_path / "outputs" / "keyword_search_volume_history.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    exists = output_path.exists()
    with output_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SEARCH_VOLUME_HISTORY_COLUMNS)
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "search_term": search_term,
                "month": "2026-03",
                "search_volume": "1000",
                "search_rank": "20",
                "marketplace": "US",
            }
        )
        writer.writerow(
            {
                "search_term": search_term,
                "month": "2026-04",
                "search_volume": "1200",
                "search_rank": "18",
                "marketplace": "US",
            }
        )


def _write_raw_detail(tmp_path: Path, asin: str, material: str) -> None:
    raw_dir = tmp_path / "outputs" / "product_detail_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    text = f"""
产品ASIN码：{asin}
标题：2 Pack Under Bed Shoe Storage with Adjustable Dividers and Reinforced Handles
主图：https://example.com/{asin}.jpg
价格：29.99
星级：4.7
评论数：100
品牌：Brand
卖家名称：Seller
卖家来源：CN
上架时间：2025-10-01
已上架天数：120
FBA费用：6.05
月销量：100
月销额：2999
属性：{{"Material":"{material}","Product Dimensions":"30 x 20 x 10 inches"}}
外包装尺寸（cm）：30 x 20 x 10
重量（g）：800
产品描述：Clear cover, double zippers, reinforced handles, foldable PP board support.
"""
    payload = {"messages": [{"content": [{"text": text}]}]}
    (raw_dir / f"{asin}_product_detail_raw.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def _write_existing_boundary(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "niche_id": "under_bed_shoe_storage",
            "boundary_item_type": "keyword",
            "boundary_item_value": "under bed shoe storage",
            "inclusion_status": "included",
            "system_reason": "manual",
            "override_reason": "",
            "reviewer": "wayne",
            "reviewed_at": "2026-04-29T00:00:00+00:00",
        },
        {
            "niche_id": "under_bed_shoe_storage",
            "boundary_item_type": "keyword",
            "boundary_item_value": "shoe rack",
            "inclusion_status": "excluded",
            "system_reason": "manual",
            "override_reason": "wrong niche",
            "reviewer": "wayne",
            "reviewed_at": "2026-04-29T00:00:00+00:00",
        },
        {
            "niche_id": "under_bed_shoe_storage",
            "boundary_item_type": "asin",
            "boundary_item_value": "B0B",
            "inclusion_status": "invalid",
            "system_reason": "manual",
            "override_reason": "wrong product form",
            "reviewer": "wayne",
            "reviewed_at": "2026-04-29T00:00:00+00:00",
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=BOUNDARY_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _patch_card_and_manifest(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_render_decision_card(**kwargs: Any) -> str:
        return f"# {kwargs['niche_name']}\n\n{kwargs['decision'].conclusion}\n"

    def fake_manifest(path_or_dir: str | Path, row: dict[str, Any]) -> Path:
        output_path = Path(path_or_dir)
        manifest_path = output_path / "decision_card_manifest_v1.json"
        manifest_path.write_text(
            json.dumps({"rows": [row]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return manifest_path

    monkeypatch.setattr(runner, "render_decision_card", fake_render_decision_card)
    monkeypatch.setattr(runner, "write_decision_card_manifest", fake_manifest)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _load_cli_script() -> Any:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_niche_opportunity.py"
    spec = importlib.util.spec_from_file_location("run_niche_opportunity_cli_test", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
