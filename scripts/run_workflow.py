from __future__ import annotations

import argparse

from storage_taxonomy.workflow import StorageTaxonomyWorkflow


def main() -> None:
    parser = argparse.ArgumentParser(description="Run storage taxonomy workflow v1")
    parser.add_argument("--keyword-input", default="data/local/keyword_input.csv")
    parser.add_argument("--top-asin-input", default="data/local/top_asin_input.csv")
    parser.add_argument("--output-dir", default="outputs/workflow_v1")
    parser.add_argument("--config-root", default=None)
    parser.add_argument("--mode", choices=["auto", "in-memory", "chunked"], default="auto")
    parser.add_argument("--keyword-chunk-size", type=int, default=100000)
    parser.add_argument("--title-chunk-size", type=int, default=100000)
    parser.add_argument("--candidate-chunk-size", type=int, default=200000)
    parser.add_argument("--with-keyword-metrics", action="store_true", help="Fetch Sorftime keyword rank and volume history")
    parser.add_argument("--keyword-metrics-amz-site", default=None, help="Sorftime Amazon site code, for example US")
    args = parser.parse_args()

    workflow = StorageTaxonomyWorkflow(config_root=args.config_root)
    if args.mode == "chunked":
        result = workflow.run_chunked(
            args.keyword_input,
            args.top_asin_input,
            args.output_dir,
            keyword_chunk_size=args.keyword_chunk_size,
            title_chunk_size=args.title_chunk_size,
            candidate_chunk_size=args.candidate_chunk_size,
            keyword_metrics_enabled=args.with_keyword_metrics,
            keyword_metrics_amz_site=args.keyword_metrics_amz_site,
        )
    elif args.mode == "auto":
        from pathlib import Path

        keyword_size = Path(args.keyword_input).stat().st_size if Path(args.keyword_input).exists() else 0
        title_size = Path(args.top_asin_input).stat().st_size if Path(args.top_asin_input).exists() else 0
        if max(keyword_size, title_size) >= 100 * 1024 * 1024:
            result = workflow.run_chunked(
                args.keyword_input,
                args.top_asin_input,
                args.output_dir,
                keyword_chunk_size=args.keyword_chunk_size,
                title_chunk_size=args.title_chunk_size,
                candidate_chunk_size=args.candidate_chunk_size,
                keyword_metrics_enabled=args.with_keyword_metrics,
                keyword_metrics_amz_site=args.keyword_metrics_amz_site,
            )
        else:
            result = workflow.run(
                args.keyword_input,
                args.top_asin_input,
                args.output_dir,
                keyword_metrics_enabled=args.with_keyword_metrics,
                keyword_metrics_amz_site=args.keyword_metrics_amz_site,
            )
    else:
        result = workflow.run(
            args.keyword_input,
            args.top_asin_input,
            args.output_dir,
            keyword_metrics_enabled=args.with_keyword_metrics,
            keyword_metrics_amz_site=args.keyword_metrics_amz_site,
        )
    print(f"Wrote workflow outputs to {args.output_dir}")
    print(result["metrics"])
    if "keyword_metrics_path" in result:
        print(f"Wrote keyword metrics to {result['keyword_metrics_path']}")


if __name__ == "__main__":
    main()
