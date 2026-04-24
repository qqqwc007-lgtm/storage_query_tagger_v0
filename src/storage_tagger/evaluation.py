from __future__ import annotations

from typing import Any, Dict, Iterable, Set

from .tagger import StorageQueryTagger


def parse_tag_ids(value: str | float | None) -> Set[str]:
    if value is None:
        return set()
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return set()
    return {part.strip() for part in text.replace("|", ";").split(";") if part.strip()}


def evaluate_golden_rows(rows: Iterable[Dict[str, Any]], tagger: StorageQueryTagger | None = None) -> Dict[str, Any]:
    tagger = tagger or StorageQueryTagger()
    total = 0
    domain_total = 0
    domain_correct = 0
    tag_total = 0
    full_label_total = 0
    tp = fp = fn = 0
    examples = []

    for row in rows:
        query = row.get("query", "")
        expected_domain = str(row.get("expected_domain_label", "")).strip()
        expected_tags = parse_tag_ids(row.get("expected_tag_ids", ""))

        result = tagger.tag(query)
        pred_tags = set(result.tag_ids)

        total += 1
        if expected_domain:
            domain_total += 1
            if result.domain_label == expected_domain:
                domain_correct += 1
        if expected_tags:
            tag_total += 1
        if expected_domain and expected_tags:
            full_label_total += 1

        tp += len(pred_tags & expected_tags)
        fp += len(pred_tags - expected_tags)
        fn += len(expected_tags - pred_tags)

        examples.append({
            "query": query,
            "expected_domain": expected_domain,
            "predicted_domain": result.domain_label,
            "expected_tag_ids": sorted(expected_tags),
            "predicted_tag_ids": sorted(pred_tags),
            "missing_tag_ids": sorted(expected_tags - pred_tags),
            "extra_tag_ids": sorted(pred_tags - expected_tags),
        })

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    return {
        "total": total,
        "domain_accuracy": domain_correct / domain_total if domain_total else None,
        "domain_total": domain_total,
        "tag_total": tag_total,
        "full_label_total": full_label_total,
        "tag_micro_precision": precision,
        "tag_micro_recall": recall,
        "tag_micro_f1": f1,
        "true_positive_tags": tp,
        "false_positive_tags": fp,
        "false_negative_tags": fn,
        "examples": examples,
    }
