from types import SimpleNamespace

from storage_tagger.evaluation import evaluate_golden_rows


class FakeTagger:
    def tag(self, query):
        labels = {
            "shoe rack": "storage_related",
            "tag only row": "not_storage",
        }
        return SimpleNamespace(domain_label=labels[query], tag_ids=[])


def test_domain_accuracy_ignores_rows_without_expected_domain():
    rows = [
        {"query": "shoe rack", "expected_domain_label": "storage_related"},
        {"query": "tag only row", "expected_tag_ids": "obj_shoes"},
    ]

    report = evaluate_golden_rows(rows, tagger=FakeTagger())

    assert report["domain_total"] == 1
    assert report["domain_accuracy"] == 1.0
    assert report["tag_total"] == 1
    assert report["full_label_total"] == 0
