import csv
import json

import pandas as pd

from storage_taxonomy.canonical_extractor import CanonicalExtractor
from storage_taxonomy.input_parser import prepare_local_inputs
from storage_taxonomy.workflow import StorageTaxonomyWorkflow


def test_canonical_extractor_examples():
    extractor = CanonicalExtractor()

    result = extractor.extract("glass food storage containers with lids")
    assert result.mapping_status == "mapped"
    assert result.fields["产品形态关键词"] == ["storage container", "container"]
    assert result.fields["产品使用场景"] == "food storage"
    assert result.fields["存储对象"] == "food"
    assert result.fields["产品材质"] == "glass"
    assert result.fields["产品功能"] == "with lid"

    result = extractor.extract("old spice deodorant")
    assert result.mapping_status == "not_storage"
    assert result.fields["产品形态关键词"] == []

    result = extractor.extract("lego")
    assert result.mapping_status == "ambiguous"


def test_prepare_local_inputs_from_raw_export(tmp_path):
    raw_csv = tmp_path / "US_raw.csv"
    raw_csv.write_text(
        '\n'.join([
            '报告范围=["每季度"],选择年份=["2026"],选择季度=["1"]',
            '搜索频率排名,搜索词,点击量最高的商品 #1：ASIN,点击量最高的商品 #1：商品名称,点击量最高的商品 #1：点击份额,点击量最高的商品 #1：转化份额,点击量最高的商品 #2：ASIN,点击量最高的商品 #2：商品名称,点击量最高的商品 #2：点击份额,点击量最高的商品 #2：转化份额,报告日期',
            '1,shoe rack,B001,Shoe Rack Organizer,12.3,4.1,B002,Shoe Cabinet Storage,6.4,1.2,2026-03-31',
            '2,lego display shelf,B003,Lego Display Shelf,11.0,3.1,,,,,2026-03-31',
        ]),
        encoding="utf-8",
    )

    kw_output = tmp_path / "keyword_input.csv"
    st_output = tmp_path / "top_asin_input.csv"
    result = prepare_local_inputs(raw_csv, kw_output, st_output)

    assert result["keyword_rows"] == 2
    assert result["top_asin_rows"] == 3

    kw_rows = list(csv.DictReader(kw_output.open("r", encoding="utf-8")))
    st_rows = list(csv.DictReader(st_output.open("r", encoding="utf-8")))

    assert kw_rows[0]["search_term"] == "shoe rack"
    assert kw_rows[0]["search_frequency_rank"] == "1"
    assert kw_rows[0]["marketplace"] == "US"

    assert st_rows[0]["search_term"] == "shoe rack"
    assert st_rows[0]["asin"] == "B001"
    assert st_rows[0]["asin_rank"] == "1"
    assert st_rows[1]["asin"] == "B002"
    assert st_rows[2]["search_term"] == "lego display shelf"


def test_workflow_end_to_end(tmp_path):
    keyword_input = tmp_path / "keyword_input.csv"
    top_asin_input = tmp_path / "top_asin_input.csv"

    pd.DataFrame([
        {"search_term": "shoe rack", "search_frequency_rank": 1, "search_volume": "", "date": "2026-03-31", "marketplace": "US"},
        {"search_term": "over toilet storage cabinet", "search_frequency_rank": 2, "search_volume": "", "date": "2026-03-31", "marketplace": "US"},
        {"search_term": "lego", "search_frequency_rank": 3, "search_volume": "", "date": "2026-03-31", "marketplace": "US"},
    ]).to_csv(keyword_input, index=False)

    pd.DataFrame([
        {"search_term": "shoe rack", "asin": "A1", "title": "shoe storage cabinet", "asin_rank": 1, "click_share": 10.0, "conversion_share": 1.1, "date": "2026-03-31", "marketplace": "US"},
        {"search_term": "over toilet storage cabinet", "asin": "A2", "title": "bathroom storage cabinet", "asin_rank": 1, "click_share": 9.0, "conversion_share": 1.0, "date": "2026-03-31", "marketplace": "US"},
        {"search_term": "lego", "asin": "A3", "title": "lego display shelf", "asin_rank": 1, "click_share": 8.0, "conversion_share": 0.9, "date": "2026-03-31", "marketplace": "US"},
    ]).to_csv(top_asin_input, index=False)

    output_dir = tmp_path / "outputs"
    workflow = StorageTaxonomyWorkflow()
    result = workflow.run(keyword_input, top_asin_input, output_dir)

    assert (output_dir / "kw.csv").exists()
    assert (output_dir / "st.csv").exists()
    assert (output_dir / "diff.csv").exists()
    assert (output_dir / "review_queue.csv").exists()
    assert (output_dir / "candidate_values.csv").exists()

    diff_df = pd.read_csv(output_dir / "diff.csv")
    assert "true_conflict" in set(diff_df["diff_type"])
    assert "rollup_match" in set(diff_df["diff_type"])

    queue_df = pd.read_csv(output_dir / "review_queue.csv")
    assert "true_conflict" in set(queue_df["diff_type"])

    metrics = json.loads((output_dir / "metrics_summary.json").read_text(encoding="utf-8"))
    assert metrics["comparable_pair_count"] >= 2
    assert result["metrics"]["review_queue_size"] >= 1


def test_workflow_chunked_end_to_end(tmp_path):
    keyword_input = tmp_path / "keyword_input.csv"
    top_asin_input = tmp_path / "top_asin_input.csv"

    pd.DataFrame([
        {"search_term": "shoe rack", "search_frequency_rank": 1, "search_volume": "", "date": "2026-03-31", "marketplace": "US"},
        {"search_term": "under sink organizer", "search_frequency_rank": 2, "search_volume": "", "date": "2026-03-31", "marketplace": "US"},
        {"search_term": "old spice deodorant", "search_frequency_rank": 3, "search_volume": "", "date": "2026-03-31", "marketplace": "US"},
    ]).to_csv(keyword_input, index=False)

    pd.DataFrame([
        {"search_term": "shoe rack", "asin": "A1", "title": "shoe storage cabinet", "asin_rank": 1, "click_share": 10.0, "conversion_share": 1.1, "date": "2026-03-31", "marketplace": "US"},
        {"search_term": "under sink organizer", "asin": "A2", "title": "under sink storage bin", "asin_rank": 1, "click_share": 9.0, "conversion_share": 1.0, "date": "2026-03-31", "marketplace": "US"},
        {"search_term": "old spice deodorant", "asin": "A3", "title": "old spice deodorant", "asin_rank": 1, "click_share": 8.0, "conversion_share": 0.9, "date": "2026-03-31", "marketplace": "US"},
    ]).to_csv(top_asin_input, index=False)

    output_dir = tmp_path / "outputs_chunked"
    workflow = StorageTaxonomyWorkflow()
    result = workflow.run_chunked(
        keyword_input=keyword_input,
        top_asin_input=top_asin_input,
        output_dir=output_dir,
        keyword_chunk_size=2,
        title_chunk_size=2,
        candidate_chunk_size=2,
    )

    assert (output_dir / "kw.csv").exists()
    assert (output_dir / "st.csv").exists()
    assert (output_dir / "diff.csv").exists()
    assert (output_dir / "review_queue.csv").exists()
    assert (output_dir / "candidate_values.csv").exists()

    diff_df = pd.read_csv(output_dir / "diff.csv")
    assert len(diff_df) > 0

    metrics = json.loads((output_dir / "metrics_summary.json").read_text(encoding="utf-8"))
    assert metrics["comparable_pair_count"] >= 2
    assert result["metrics"]["review_queue_size"] >= 1
