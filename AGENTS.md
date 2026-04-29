# Repository Guidelines

## Project Structure & Module Organization

This repo has two Python codepaths:

- `src/storage_tagger/`: v0 query tagger for single-side tagging, evaluation, and candidate discovery.
- `src/storage_taxonomy/`: v1 local workflow for `keyword_input.csv`, `top_asin_input.csv`, diffing, review queue generation, and candidate extraction.
- `src/storage_taxonomy/niche_opportunity/`: v1 downstream selected-niche workflow for confirmed boundary, decision cards, review logs, and calibration backlog.

Supporting files live in:

- `config/`: YAML/JSON rules, taxonomy values, thresholds, and workflow config.
- `scripts/`: runnable entry points such as `prepare_local_inputs.py`, `run_workflow.py`, and `run_niche_opportunity.py`.
- `tests/`: `pytest` coverage for v0 and v1.
- `data/sample/` and `data/local/`: sample fixtures and local raw inputs.
- `outputs/`: generated CSV/JSON artifacts. Treat as derived data, not source.

## Build, Test, and Development Commands

- `pip install -r requirements.txt`: install runtime and test dependencies.
- `make test`: run the full test suite.
- `make demo`: run the v0 demo on sample queries.
- `make prepare-inputs`: split one raw Amazon export in `data/local/` into `keyword_input.csv` and `top_asin_input.csv`.
- `make workflow-v1`: run the v1 workflow with default paths.
- `PYTHONPATH=src python scripts/run_workflow.py --mode chunked`: preferred for large local batches.
- `PYTHONPATH=src python scripts/run_niche_opportunity.py generate-card ...`: generate one confirmed niche decision card.
- `PYTHONPATH=src python scripts/run_niche_opportunity.py record-review ...`: append the operations review log and calibration backlog.

Use UTF-8 locale when running Python in this workspace:
`LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8`.

## Coding Style & Naming Conventions

Use Python 3.10+, 4-space indentation, type hints, and small single-purpose modules. Follow existing naming:

- modules/functions/variables: `snake_case`
- classes/dataclasses: `PascalCase`
- tests: `test_*.py`

Keep business rules in `config/`, not hard-coded in scripts. Preserve ASCII unless the file already needs Chinese field names or labels.

## Testing Guidelines

Tests use `pytest`. Add or update tests whenever you change extraction logic, diff behavior, or input parsing. Prefer realistic fixtures over mocks for CSV workflows. Run `PYTHONPATH=src pytest -q` before finishing work.

## Commit & Pull Request Guidelines

This workspace does not include `.git` history, so no local commit convention can be inferred from past commits. Use short conventional-style subjects instead, for example:

- `feat: add chunked workflow runner`
- `fix: tighten candidate discovery noise filter`
- `docs: update workflow v1 usage`

PRs should state the affected pipeline (`v0` or `v1`), summarize data/schema changes, list commands run, and include sample output paths when behavior changes.
