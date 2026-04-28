# Niche Opportunity Phase E TODO

Current owner: main agent
Last updated: 2026-04-29

## Scope

Implement only Phase E of the locked v1 niche-opportunity workflow:

```text
confirmed niche boundary
  -> one-page Markdown decision card
  -> decision_card_manifest_v1.json
  -> opportunity_review_v1.csv
  -> calibration_backlog_v1.csv
  -> niche_opportunity_quality_v1.json
```

Do not add a web UI, bulk niche ranking, automatic VOC fetching, PRD handoff, or a database review workflow.

## Shared Interface Contract

The implementation must reuse existing Phase A-D objects:

- `ConfirmedBoundaryRow`, `NicheKeywordBridgeRow`, `NicheAsinBridgeRow`, `NicheBoundaryResult`
- `ProductAsinFactRow`
- `SalesSummaryRow`
- `NicheSignalSet`, `EvidenceSignal`
- `DecisionResult`
- `NicheCostEstimate`

Locked public functions for Phase E:

- `render_decision_card(...) -> str`
  - Pure renderer. It receives prepared evidence objects and does not recompute signals, costs, or decisions.
- `escape_spreadsheet_formula(value: object) -> object`
  - CSV/XLSX-facing strings starting with `=`, `+`, `-`, or `@` must be prefixed with `'`.
- `write_decision_card_manifest(path_or_dir, row) -> Path`
  - Writes or updates `decision_card_manifest_v1.json`.
- `append_opportunity_review(path_or_dir, row) -> Path`
  - Appends `opportunity_review_v1.csv`; `defer`/`reject` require a non-empty reason/comment.
- `append_calibration_backlog(path_or_dir, row) -> Path`
  - Appends `calibration_backlog_v1.csv` for defer/reject review outcomes.
- `generate_card(...)`
  - Loads selected niche inputs, seeds or respects `confirmed_niche_boundary_v1.csv`, parses only confirmed ASIN raw files, renders the card, writes manifest/quality outputs.
- `record_review(...)`
  - Validates approve/defer/reject review input and writes review/calibration outputs.

## File Ownership

Main agent:

- `docs/niche_opportunity_phase_e_todo.md`
- `src/storage_taxonomy/niche_opportunity/__init__.py`
- final integration fixes and verification only

Worker A:

- `src/storage_taxonomy/niche_opportunity/exports.py`
- `tests/test_niche_opportunity_exports.py`

Worker B:

- `src/storage_taxonomy/niche_opportunity/card_renderer.py`
- `tests/test_niche_opportunity_card_renderer.py`

Worker C:

- `src/storage_taxonomy/niche_opportunity/runner.py`
- `scripts/run_niche_opportunity.py`
- `tests/test_niche_opportunity_runner.py`

Workers must not edit files outside their ownership set. If a public export is needed, leave a note for main agent instead of editing `__init__.py`.

## Status

| Item | Owner | Status | Notes |
|---|---|---|---|
| Interface contract | Main | Done | Initial contract written before worker launch. |
| Exports and review/calibration logs | Worker A / Carson | Done | Implemented exports.py; local worker tests passed: 4 passed, ruff passed. |
| Markdown decision card | Worker B / Nash | Done | Implemented card_renderer.py; local worker tests passed: 4 passed, ruff passed. |
| Runner and CLI | Worker C / Lovelace | Done | Implemented runner.py and CLI; local worker tests passed: 4 passed, ruff passed. |
| Public exports | Main | Done | `__init__.py` exports updated; Phase E targeted tests passed after integration. |
| Integration verification | Main | Done | Full pytest passed: 66 passed. Ruff passed. Real-data CLI smoke generated card, manifest, review log, backlog, and quality JSON. |
| Phase F follow-up review | Main | Done | `record_review` now backfills system conclusion/reason/card path from `decision_card_manifest_v1.json`; tests and real-data smoke passed. |

## Integration Notes

- Main fixed one integration mismatch after worker return: `runner.generate_card` now calls `render_decision_card` with `keywords`, `keyword_bridge_rows`, and `asin_bridge_rows` instead of the older `boundary/signals/config` shape.
- Main fixed review export row naming: `record_review` now sends `review_outcome`, `rejection_type`, and `review_comment` to exports, matching `opportunity_review_v1.csv` and `calibration_backlog_v1.csv`.
- Main fixed review calibration context after Phase F review: `record_review` now reads the niche row from `decision_card_manifest_v1.json` when available, so review and backlog rows retain the system conclusion and reason that operations overrode.
- Real-data smoke for `under_bed_shoe_storage` produced conclusion `推荐立项`; without manual invalid-ASIN boundary edits, Top ASIN evidence still includes mixed product forms, which is expected and reinforces the confirmed-boundary review step.

## Verification Checklist

- `LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 PYTHONPATH=src pytest -q`
- `LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 PYTHONPATH=src python -m ruff check src/storage_taxonomy/niche_opportunity tests/test_niche_opportunity_*.py scripts/run_niche_opportunity.py`
- Real-data smoke for `under_bed_shoe_storage`
