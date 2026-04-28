from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .candidate_discovery import discover_candidate_values, discover_candidate_values_from_files
from .canonical_extractor import CanonicalExtractor
from .diff_engine import DIFF_COLUMNS, build_diff_df
from .metrics import compute_workflow_metrics
from .review_queue import build_review_queue
from .taxonomy_registry import ALL_FIELDS, TaxonomyRegistry


class StorageTaxonomyWorkflow:
    def __init__(self, config_root: str | Path | None = None):
        self.registry = TaxonomyRegistry(config_root=config_root)
        self.extractor = CanonicalExtractor(self.registry)

    def extract_keywords(self, df: pd.DataFrame) -> pd.DataFrame:
        rows = []
        for record in df.to_dict("records"):
            search_term = str(record.get("search_term", "")).strip()
            result = self.extractor.extract(search_term)
            extra = {
                "search_term": search_term,
                "search_frequency_rank": record.get("search_frequency_rank", ""),
                "search_volume": record.get("search_volume", ""),
                "date": record.get("date", ""),
                "marketplace": record.get("marketplace", ""),
            }
            rows.append(result.to_csv_row(extra=extra))
        return pd.DataFrame(rows)

    def extract_titles(self, df: pd.DataFrame) -> pd.DataFrame:
        rows = []
        for record in df.to_dict("records"):
            title = str(record.get("title", "")).strip()
            result = self.extractor.extract(title)
            extra = {
                "search_term": str(record.get("search_term", "")).strip(),
                "asin": record.get("asin", ""),
                "title": title,
                "asin_rank": record.get("asin_rank", ""),
                "click_share": record.get("click_share", ""),
                "conversion_share": record.get("conversion_share", ""),
                "date": record.get("date", ""),
                "marketplace": record.get("marketplace", ""),
            }
            rows.append(result.to_csv_row(extra=extra))
        return pd.DataFrame(rows)

    def run(
        self,
        keyword_input: str | Path,
        top_asin_input: str | Path,
        output_dir: str | Path,
    ) -> dict[str, Any]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        kw_input_df = pd.read_csv(keyword_input)
        st_input_df = pd.read_csv(top_asin_input)
        kw_df = self.extract_keywords(kw_input_df)
        st_df = self.extract_titles(st_input_df)
        diff_df = build_diff_df(kw_df, st_df, registry=self.registry)
        review_queue_df = build_review_queue(diff_df, kw_df, registry=self.registry)

        if not diff_df.empty and not review_queue_df.empty:
            diff_df = self._annotate_diff_with_review_queue(
                diff_df=diff_df,
                review_queue_df=review_queue_df,
            )

        candidate_df = discover_candidate_values(kw_df, st_df, diff_df, registry=self.registry)
        metrics = compute_workflow_metrics(diff_df, review_queue_df)

        kw_path = output_dir / "kw.csv"
        st_path = output_dir / "st.csv"
        diff_path = output_dir / "diff.csv"
        review_queue_path = output_dir / "review_queue.csv"
        candidate_path = output_dir / "candidate_values.csv"
        metrics_path = output_dir / "metrics_summary.json"

        kw_df.to_csv(kw_path, index=False)
        st_df.to_csv(st_path, index=False)
        diff_df.to_csv(diff_path, index=False)
        review_queue_df.to_csv(review_queue_path, index=False)
        candidate_df.to_csv(candidate_path, index=False)
        metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

        return {
            "kw_path": str(kw_path),
            "st_path": str(st_path),
            "diff_path": str(diff_path),
            "review_queue_path": str(review_queue_path),
            "candidate_path": str(candidate_path),
            "metrics_path": str(metrics_path),
            "metrics": metrics,
        }

    def run_chunked(
        self,
        keyword_input: str | Path,
        top_asin_input: str | Path,
        output_dir: str | Path,
        keyword_chunk_size: int = 100_000,
        title_chunk_size: int = 100_000,
        candidate_chunk_size: int = 200_000,
    ) -> dict[str, Any]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        kw_path = output_dir / "kw.csv"
        st_path = output_dir / "st.csv"
        diff_path = output_dir / "diff.csv"
        review_queue_path = output_dir / "review_queue.csv"
        candidate_path = output_dir / "candidate_values.csv"
        metrics_path = output_dir / "metrics_summary.json"

        for path in [kw_path, st_path, diff_path, review_queue_path, candidate_path, metrics_path]:
            if path.exists():
                path.unlink()

        kw_lookup: dict[str, dict[str, Any]] = {}
        kw_header_written = False

        for kw_chunk in pd.read_csv(keyword_input, chunksize=keyword_chunk_size):
            kw_df_chunk = self.extract_keywords(kw_chunk)
            kw_df_chunk.to_csv(kw_path, mode="a", header=not kw_header_written, index=False)
            kw_header_written = True
            for row in kw_df_chunk.to_dict("records"):
                kw_lookup[str(row["search_term"])] = row

        if not kw_header_written:
            pd.DataFrame(columns=self._keyword_output_columns()).to_csv(kw_path, index=False)

        st_header_written = False
        diff_header_written = False

        for st_input_chunk in pd.read_csv(top_asin_input, chunksize=title_chunk_size):
            st_df_chunk = self.extract_titles(st_input_chunk)
            st_df_chunk.to_csv(st_path, mode="a", header=not st_header_written, index=False)
            st_header_written = True

            matched_terms = [
                term for term in st_df_chunk["search_term"].astype(str).unique().tolist() if term in kw_lookup
            ]
            if not matched_terms:
                continue

            st_compare_chunk = st_df_chunk[st_df_chunk["search_term"].isin(matched_terms)]
            kw_compare_chunk = pd.DataFrame([kw_lookup[term] for term in matched_terms])
            diff_df_chunk = build_diff_df(kw_compare_chunk, st_compare_chunk, registry=self.registry)
            if diff_df_chunk.empty:
                continue
            diff_df_chunk.to_csv(diff_path, mode="a", header=not diff_header_written, index=False)
            diff_header_written = True

        if not st_header_written:
            pd.DataFrame(columns=self._title_output_columns()).to_csv(st_path, index=False)
        if not diff_header_written:
            pd.DataFrame(columns=DIFF_COLUMNS).to_csv(diff_path, index=False)

        kw_df = pd.read_csv(kw_path)
        diff_df = pd.read_csv(diff_path)
        review_queue_df = build_review_queue(diff_df, kw_df, registry=self.registry)

        if not diff_df.empty and not review_queue_df.empty:
            diff_df = self._annotate_diff_with_review_queue(
                diff_df=diff_df,
                review_queue_df=review_queue_df,
            )
            diff_df.to_csv(diff_path, index=False)

        candidate_df = discover_candidate_values_from_files(
            kw_csv=kw_path,
            st_csv=st_path,
            diff_csv=diff_path,
            registry=self.registry,
            chunk_size=candidate_chunk_size,
        )
        review_queue_df.to_csv(review_queue_path, index=False)
        candidate_df.to_csv(candidate_path, index=False)
        metrics = compute_workflow_metrics(diff_df, review_queue_df)
        metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

        return {
            "kw_path": str(kw_path),
            "st_path": str(st_path),
            "diff_path": str(diff_path),
            "review_queue_path": str(review_queue_path),
            "candidate_path": str(candidate_path),
            "metrics_path": str(metrics_path),
            "metrics": metrics,
        }

    @staticmethod
    def _lookup_review_priority(review_queue_df: pd.DataFrame, row: pd.Series) -> int:
        matched = review_queue_df[
            (review_queue_df["queue_source"] == "diff")
            & (review_queue_df["search_term"] == row["search_term"])
            & (review_queue_df["asin"] == row["asin"])
            & (review_queue_df["field_name"] == row["field_name"])
            & (review_queue_df["diff_type"] == row["diff_type"])
        ]["review_priority"]
        if matched.empty:
            return 0
        max_value = pd.to_numeric(matched, errors="coerce").max()
        if pd.isna(max_value):
            return 0
        return int(max_value)

    @staticmethod
    def _annotate_diff_with_review_queue(
        diff_df: pd.DataFrame,
        review_queue_df: pd.DataFrame,
    ) -> pd.DataFrame:
        queue_columns = ["queue_source", "search_term", "asin", "field_name", "diff_type", "review_priority"]
        queue_df = review_queue_df.reindex(columns=queue_columns).copy()
        queue_df = queue_df[queue_df["queue_source"] == "diff"]
        if queue_df.empty:
            diff_df = diff_df.copy()
            diff_df["review_required"] = False
            diff_df["review_priority"] = 0
            return diff_df

        queue_df["review_required"] = True
        queue_df = (
            queue_df
            .sort_values("review_priority", ascending=False)
            .drop_duplicates(subset=["search_term", "asin", "field_name", "diff_type"])
            .drop(columns=["queue_source"])
        )

        merged = diff_df.merge(
            queue_df,
            how="left",
            on=["search_term", "asin", "field_name", "diff_type"],
            suffixes=("", "_queue"),
        )
        merged["review_required"] = merged["review_required"].fillna(False).astype(bool)
        queue_priority = pd.to_numeric(merged.pop("review_priority_queue"), errors="coerce").fillna(0).astype(int)
        existing_priority = pd.to_numeric(merged["review_priority"], errors="coerce").fillna(0).astype(int)
        merged["review_priority"] = queue_priority.where(queue_priority > 0, existing_priority)
        return merged

    @staticmethod
    def _keyword_output_columns() -> list[str]:
        return ["search_term", "search_frequency_rank", "search_volume", "date", "marketplace", *ALL_FIELDS, "taxonomy_version", "mapping_status", "confidence", "matched_aliases", "unmapped_phrases", "evidence"]

    @staticmethod
    def _title_output_columns() -> list[str]:
        return ["search_term", "asin", "title", "asin_rank", "click_share", "conversion_share", "date", "marketplace", *ALL_FIELDS, "taxonomy_version", "mapping_status", "confidence", "matched_aliases", "unmapped_phrases", "evidence"]
