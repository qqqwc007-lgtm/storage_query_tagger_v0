.PHONY: demo eval discover test prepare-inputs prepare-inputs-top200k reduce-inputs-storage workflow-v1 keyword-metrics review-candidates-go taxonomy-loop

demo:
	PYTHONPATH=src python scripts/run_tagging_demo.py --input data/sample/sample_queries.csv --output outputs/sample_tagged_queries.csv

eval:
	PYTHONPATH=src python scripts/evaluate_golden_set.py --input data/sample/golden_set_example.csv --output outputs/golden_eval_report.json

discover:
	PYTHONPATH=src python scripts/discover_new_tags.py --input outputs/sample_tagged_queries.csv --output outputs/candidate_tag_clusters.csv

test:
	PYTHONPATH=src pytest -q

prepare-inputs:
	PYTHONPATH=src python scripts/prepare_local_inputs.py

prepare-inputs-top200k:
	PYTHONPATH=src python scripts/reduce_workflow_inputs.py --mode rank-cap --max-search-frequency-rank 200000 --output-dir data/local/reduced

reduce-inputs-storage:
	PYTHONPATH=src python scripts/reduce_workflow_inputs.py --mode storage-scope --scope recall --max-search-frequency-rank 200000 --output-dir data/local/reduced

workflow-v1:
	PYTHONPATH=src python scripts/run_workflow.py

keyword-metrics:
	PYTHONPATH=src python scripts/enrich_keyword_metrics.py

review-candidates-go:
	PYTHONPATH=src python scripts/review_candidate_values_opencode_go.py

taxonomy-loop:
	PYTHONPATH=src python scripts/run_taxonomy_loop.py
