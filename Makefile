.PHONY: demo eval discover test prepare-inputs workflow-v1 review-candidates-go taxonomy-loop

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

workflow-v1:
	PYTHONPATH=src python scripts/run_workflow.py

review-candidates-go:
	PYTHONPATH=src python scripts/review_candidate_values_opencode_go.py

taxonomy-loop:
	PYTHONPATH=src python scripts/run_taxonomy_loop.py
