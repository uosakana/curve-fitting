from __future__ import annotations

from typing import Any

from ml.similar_records import find_similar_records


def recommend_from_records(payload: dict[str, Any], *, neighbor_count: int = 5) -> dict[str, Any]:
    similar = find_similar_records(payload, phase="postfit", limit=neighbor_count)
    if similar.get("status") != "ready":
        return {
            "ok": True,
            "status": similar.get("status", "insufficient_records"),
            "message": similar.get("message", "No similar records are available yet."),
            "recommendation": None,
            "strategy_scores": [],
            "neighbors": [],
            "record_count": similar.get("record_count", 0),
        }

    summary = similar.get("summary") or {}
    recommendation = {
        "product_fit_mode": summary.get("recommended_product_fit_mode"),
        "fit_strategy": summary.get("recommended_fit_strategy"),
        "m": summary.get("median_m"),
        "hypothesis": summary.get("recommended_hypothesis"),
        "expected_mean_error": summary.get("median_mean_error"),
        "risk_notes": summary.get("risk_notes") or [],
    }
    strategy_scores = [
        {"fit_strategy": key, "count": count}
        for key, count in (summary.get("fit_strategy_counts") or {}).items()
    ]
    strategy_scores.sort(key=lambda item: (-item["count"], item["fit_strategy"]))
    return {
        "ok": True,
        "status": "ready",
        "message": similar.get("message"),
        "recommendation": recommendation,
        "strategy_scores": strategy_scores,
        "neighbors": similar.get("neighbors") or [],
        "record_count": similar.get("record_count", 0),
    }
