from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from storage_taxonomy.niche_opportunity.boundary import NicheAsinBridgeRow
from storage_taxonomy.niche_opportunity.loaders import KeywordAsinFactRow
from storage_taxonomy.niche_opportunity.raw_detail_parser import (
    build_product_asin_facts,
    parse_product_detail_raw,
)


def _raw_payload(text: str, asin: str = "B0TEST") -> dict[str, object]:
    return {
        "asin": asin,
        "messages": [
            {
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": text,
                        }
                    ]
                }
            }
        ],
    }


def _source_row(asin: str, title: str = "Fallback Title") -> KeywordAsinFactRow:
    return KeywordAsinFactRow(
        canonical_scenario_need="床下收纳",
        search_term="under bed shoe storage",
        keyword_translation="床底鞋子收纳",
        rank=1,
        asin=asin,
        title=title,
        main_image_url="https://example.com/fallback.jpg",
        brand="FallbackBrand",
        seller_name="FallbackSeller",
        price=19.99,
        units=100,
        gmv=1999.0,
        asin_asp=19.99,
        launch_date=date(2025, 1, 1),
        days_since_launch=100,
        rating=4.1,
        review_count=20,
        is_new_asin=True,
        product_detail_status="cached",
        product_detail_raw_json="{}",
        keyword_top20_asin_list_json="[]",
        source_record_json="{}",
    )


def _bridge_row(asin: str, invalid: bool = False) -> NicheAsinBridgeRow:
    return NicheAsinBridgeRow(
        niche_id="under_bed_shoe_storage",
        search_term="under bed shoe storage",
        asin=asin,
        rank=1,
        is_new_asin=True,
        is_repeated_new_asin=False,
        title=f"{asin} Bridge Title",
        image_url=f"https://example.com/{asin}.jpg",
        price=29.99,
        units=90,
        gmv=2699.1,
        asin_asp=29.99,
        launch_date="2025-02-03",
        rating=4.6,
        review_count=15,
        product_detail_raw_json="",
        asin_validity_system="valid",
        asin_validity_override="invalid" if invalid else "",
        asin_validity_reason="wrong product form" if invalid else "",
    )


def test_parse_product_detail_raw_extracts_fields_and_strips_instruction_footer(tmp_path: Path) -> None:
    raw_path = tmp_path / "B0TEST_product_detail_raw.json"
    raw_text = "\n".join(
        [
            "产品ASIN码：B0TEST",
            "父级ASIN码：B0PARENT",
            "标题：Under Bed Shoe Storage Organizer",
            "主图：https://example.com/main.jpg",
            "价格：29.99",
            "星级：4.80",
            "评论数：510",
            "品牌：BrandA",
            "卖家名称：SellerA",
            "卖家来源：CN",
            "分类：UNDER BED STORAGE",
            '属性：{"Material":"Fabric","Product Dimensions":"30 x 24 x 5.9 inches","Item Weight":"2.3 Pounds"}；Color=Grey',
            "上架时间：2025-10-01",
            "已上架天数：210",
            "FBA费用：6.05",
            "月销量：月销量：15603",
            "月销额：月销额：155873.97",
            "产品描述：Clear PVC cover with reinforced handles.",
            '{"Easy to assemble":4.7}',
            "特征：{\"Sturdiness\":4.3}",
            "外包装尺寸（cm）：33.93*9.91*4.90",
            "重量（g）：200",
            "依据这些数据进行总结，如无明确指令不要延伸调用其他工具。",
        ]
    )
    raw_path.write_text(json.dumps(_raw_payload(raw_text), ensure_ascii=False), encoding="utf-8")

    detail = parse_product_detail_raw(raw_path)

    assert detail.parse_status == "parsed"
    assert detail.asin == "B0TEST"
    assert detail.parent_asin == "B0PARENT"
    assert detail.title == "Under Bed Shoe Storage Organizer"
    assert detail.main_image_url == "https://example.com/main.jpg"
    assert detail.price == 29.99
    assert detail.rating == 4.8
    assert detail.review_count == 510
    assert detail.brand == "BrandA"
    assert detail.seller_name == "SellerA"
    assert detail.seller_origin == "CN"
    assert detail.attributes["Material"] == "Fabric"
    assert detail.material_raw == "Fabric"
    assert detail.dimension_raw == "30 x 24 x 5.9 inches"
    assert detail.weight_raw == "2.3 Pounds"
    assert detail.launch_date == date(2025, 10, 1)
    assert detail.fba_fee == 6.05
    assert detail.monthly_units == 15603
    assert detail.monthly_gmv == 155873.97
    assert detail.package_dimensions_cm == (33.93, 9.91, 4.9)
    assert detail.weight_g == 200
    assert "延伸调用其他工具" not in detail.source_text


def test_parse_product_detail_raw_reports_parse_error_for_invalid_json(tmp_path: Path) -> None:
    raw_path = tmp_path / "B0BAD_product_detail_raw.json"
    raw_path.write_text("{not json", encoding="utf-8")

    detail = parse_product_detail_raw(raw_path)

    assert detail.asin == "B0BAD"
    assert detail.parse_status == "parse_error"
    assert detail.parse_errors[0].startswith("json_error:")


def test_build_product_asin_facts_dedupes_and_reads_only_referenced_asins(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "B0A_product_detail_raw.json").write_text(
        json.dumps(
            _raw_payload(
                "\n".join(
                    [
                        "产品ASIN码：B0A",
                        "标题：Parsed Title",
                        "主图：https://example.com/parsed.jpg",
                        "品牌：ParsedBrand",
                        "卖家名称：ParsedSeller",
                        "价格：31.99",
                        "月销量：88",
                        "月销额：2815.12",
                        "FBA费用：6.05",
                        '属性：{"Material":"Oxford Fabric"}',
                    ]
                ),
                asin="B0A",
            ),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (raw_dir / "UNRELATED_product_detail_raw.json").write_text("{not json", encoding="utf-8")

    facts = build_product_asin_facts([_source_row("B0A"), _source_row("B0A"), _source_row("B0MISSING")], raw_dir)

    assert [fact.asin for fact in facts] == ["B0A", "B0MISSING"]
    assert facts[0].title == "Parsed Title"
    assert facts[0].main_image_url == "https://example.com/parsed.jpg"
    assert facts[0].brand == "ParsedBrand"
    assert facts[0].monthly_units == 88
    assert facts[0].fba_fee == 6.05
    assert facts[0].material_raw == "Oxford Fabric"
    assert facts[0].parse_status == "parsed"
    assert facts[1].title == "Fallback Title"
    assert facts[1].parse_status == "missing_raw"


def test_build_product_asin_facts_accepts_boundary_bridge_rows_and_skips_invalid(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    facts = build_product_asin_facts([_bridge_row("B0A"), _bridge_row("B0B", invalid=True)], raw_dir)

    assert [fact.asin for fact in facts] == ["B0A"]
    assert facts[0].title == "B0A Bridge Title"
    assert facts[0].main_image_url == "https://example.com/B0A.jpg"
    assert facts[0].monthly_units == 90
    assert facts[0].launch_date == date(2025, 2, 3)
    assert facts[0].parse_status == "missing_raw"
