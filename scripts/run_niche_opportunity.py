from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from storage_taxonomy.niche_opportunity import runner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run niche opportunity v1 selected-niche workflow.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser("generate-card", help="Generate one selected niche decision card.")
    generate_parser.add_argument("--niche-id", required=True)
    generate_parser.add_argument("--niche-name", default="")
    generate_parser.add_argument("--keywords", default="")
    generate_parser.add_argument("--output-dir", default=str(runner.DEFAULT_OUTPUT_DIR))
    generate_parser.add_argument("--config", default=None)
    generate_parser.add_argument("--reviewer", default="system")

    review_parser = subparsers.add_parser("record-review", help="Append an opportunity review decision.")
    review_parser.add_argument("--niche-id", required=True)
    review_parser.add_argument("--reviewer", required=True)
    review_parser.add_argument("--final-conclusion", required=True, choices=["approve", "defer", "reject"])
    review_parser.add_argument("--rejection-type", default="")
    review_parser.add_argument("--review-comment", default="")
    review_parser.add_argument("--output-dir", default=str(runner.DEFAULT_OUTPUT_DIR))

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "generate-card":
        result = runner.generate_card(
            niche_id=args.niche_id,
            niche_name=args.niche_name,
            keywords=args.keywords,
            output_dir=Path(args.output_dir),
            config_path=args.config,
            reviewer=args.reviewer,
        )
        print(f"Wrote decision card: {result.card_path}")
        print(f"Wrote manifest: {result.manifest_path}")
        print(f"Wrote quality report: {result.quality_path}")
        print(f"Conclusion: {result.decision.conclusion}")
        return 0

    if args.command == "record-review":
        result = runner.record_review(
            niche_id=args.niche_id,
            reviewer=args.reviewer,
            final_conclusion=args.final_conclusion,
            rejection_type=args.rejection_type,
            review_comment=args.review_comment,
            output_dir=Path(args.output_dir),
        )
        print(f"Wrote review log: {result.review_path}")
        if result.calibration_backlog_path is not None:
            print(f"Wrote calibration backlog: {result.calibration_backlog_path}")
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
