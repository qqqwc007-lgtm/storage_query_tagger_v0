#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from storage_taxonomy.taxonomy_loop import TaxonomyLoopConfig, run_taxonomy_loop


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the taxonomy candidate-review loop.")
    parser.add_argument("--keyword-input", default="data/local/keyword_input.csv")
    parser.add_argument("--top-asin-input", default="data/local/top_asin_input.csv")
    parser.add_argument("--source-config-root", default="config")
    parser.add_argument("--output-root", default="outputs/taxonomy_loop")
    parser.add_argument("--candidate-limit", type=int, default=50)
    parser.add_argument("--candidate-min-frequency", type=int, default=1)
    parser.add_argument("--max-iterations", type=int, default=1)
    parser.add_argument("--model", default="kimi-k2.6")
    parser.add_argument("--mode", choices=["auto", "in-memory", "chunked"], default="auto")
    parser.add_argument("--keyword-chunk-size", type=int, default=100000)
    parser.add_argument("--title-chunk-size", type=int, default=100000)
    parser.add_argument("--candidate-chunk-size", type=int, default=200000)
    parser.add_argument("--baseline-output-dir", default=None)
    args = parser.parse_args()

    result = run_taxonomy_loop(
        TaxonomyLoopConfig(
            keyword_input=Path(args.keyword_input),
            top_asin_input=Path(args.top_asin_input),
            output_root=Path(args.output_root),
            source_config_root=Path(args.source_config_root),
            candidate_limit=args.candidate_limit,
            candidate_min_frequency=args.candidate_min_frequency,
            max_iterations=args.max_iterations,
            model=args.model,
            mode=args.mode,
            keyword_chunk_size=args.keyword_chunk_size,
            title_chunk_size=args.title_chunk_size,
            candidate_chunk_size=args.candidate_chunk_size,
            baseline_output_dir=Path(args.baseline_output_dir) if args.baseline_output_dir else None,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
