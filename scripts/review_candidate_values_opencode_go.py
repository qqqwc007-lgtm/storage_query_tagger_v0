#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from storage_taxonomy.candidate_value_reviewer import CandidateReviewConfig, review_candidate_values
from storage_taxonomy.opencode_go_client import (
    DEFAULT_OPENCODE_GO_ENDPOINT,
    DEFAULT_OPENCODE_GO_MODEL,
    OpenCodeGoChatClient,
    load_opencode_go_api_key,
)
from storage_taxonomy.taxonomy_registry import TaxonomyRegistry


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Review candidate_values.csv with OpenCode Go and write decision artifacts."
    )
    parser.add_argument(
        "--candidate-values",
        default="outputs/workflow_v1_full/candidate_values.csv",
        help="Path to candidate_values.csv.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory. Defaults to the candidate CSV parent directory.",
    )
    parser.add_argument("--config-root", default=None)
    parser.add_argument("--model", default=DEFAULT_OPENCODE_GO_MODEL)
    parser.add_argument("--endpoint", default=DEFAULT_OPENCODE_GO_ENDPOINT)
    parser.add_argument("--limit", type=int, default=20, help="Number of candidates to review. Use 0 for all.")
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--confidence-gate", type=float, default=0.85)
    parser.add_argument("--max-tokens", type=int, default=4000)
    args = parser.parse_args()

    api_key = load_opencode_go_api_key()
    client = OpenCodeGoChatClient(
        api_key=api_key,
        model=args.model,
        endpoint=args.endpoint,
    )
    result = review_candidate_values(
        candidate_values_csv=args.candidate_values,
        output_dir=args.output_dir,
        client=client,
        registry=TaxonomyRegistry(config_root=args.config_root),
        limit=None if args.limit == 0 else args.limit,
        config=CandidateReviewConfig(
            batch_size=args.batch_size,
            confidence_gate=args.confidence_gate,
            max_tokens=args.max_tokens,
        ),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
