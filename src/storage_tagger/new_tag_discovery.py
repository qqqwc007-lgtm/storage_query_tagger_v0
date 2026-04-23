from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd


def discover_candidate_clusters(
    df: pd.DataFrame,
    query_col: str = "query",
    status_col: str = "coverage_status",
    max_clusters: int = 8,
    min_cluster_size: int = 2,
) -> pd.DataFrame:
    """Simple v0 candidate discovery using TF-IDF + KMeans.

    Production can replace this with query embeddings + click behavior + HDBSCAN/BERTopic.
    """
    candidate_df = df.copy()
    if status_col in candidate_df.columns:
        review_mask = candidate_df[status_col].isin(["ambiguous", "partial", "needs_review"])
        if "needs_review" in candidate_df.columns:
            review_mask = review_mask | (candidate_df["needs_review"].astype(str).str.lower() == "true")
        candidate_df = candidate_df[review_mask]

    candidate_df = candidate_df.dropna(subset=[query_col])
    queries = candidate_df[query_col].astype(str).tolist()

    columns = [
        "cluster_id",
        "cluster_size",
        "candidate_tag_name",
        "dimension",
        "top_terms",
        "top_queries",
        "recommended_action",
        "review_status",
    ]
    if not queries:
        return pd.DataFrame(columns=columns)

    try:
        from sklearn.cluster import KMeans
        from sklearn.feature_extraction.text import TfidfVectorizer
    except ImportError as exc:
        raise ImportError("Install scikit-learn to run candidate discovery.") from exc

    n_clusters = min(max_clusters, max(1, len(queries) // min_cluster_size))
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1, stop_words="english")
    X = vectorizer.fit_transform(queries)

    if len(queries) == 1:
        labels = [0]
    else:
        model = KMeans(n_clusters=n_clusters, random_state=42, n_init="auto")
        labels = model.fit_predict(X)

    feature_names = vectorizer.get_feature_names_out()
    temp = pd.DataFrame({"query": queries, "cluster_id": labels})
    rows: List[Dict[str, Any]] = []

    for cluster_id, group in temp.groupby("cluster_id"):
        idx = group.index.tolist()
        cluster_X = X[idx]
        mean_scores = cluster_X.mean(axis=0).A1
        top_idx = mean_scores.argsort()[::-1][:10]
        top_terms = [feature_names[i] for i in top_idx if mean_scores[i] > 0]
        top_queries = group["query"].head(10).tolist()
        rows.append({
            "cluster_id": int(cluster_id),
            "cluster_size": int(len(group)),
            "candidate_tag_name": "_".join(top_terms[:3]) if top_terms else f"cluster_{cluster_id}",
            "dimension": "unknown_pending_review",
            "top_terms": ";".join(top_terms),
            "top_queries": " | ".join(top_queries),
            "recommended_action": "needs_human_review" if len(group) >= min_cluster_size else "keep_as_noise_or_review_later",
            "review_status": "pending",
        })

    return pd.DataFrame(rows, columns=columns).sort_values(["cluster_size", "cluster_id"], ascending=[False, True])
