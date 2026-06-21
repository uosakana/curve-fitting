from __future__ import annotations

from typing import Any


def normalize_product_fit_mode(value: str | None) -> str | None:
    normalized = str(value or "").strip().lower().replace("-", "_")
    if not normalized:
        return None
    if normalized in {"fast", "fast_fit", "quick", "quick_global", "baseline"}:
        return "fast_fit"
    if normalized in {"diagnostic", "diagnostic_fit", "auto", "analyze", "deep"}:
        return "diagnostic_fit"
    raise ValueError("product_fit_mode must be fast_fit or diagnostic_fit.")


def apply_product_fit_mode(settings: dict[str, Any], product_fit_mode: str | None) -> dict[str, Any]:
    next_settings = dict(settings)
    if product_fit_mode == "fast_fit":
        next_settings.update(
            {
                "mode": "fit",
                "fit_strategy": "quick_global",
                "sweep_strategies": False,
                "scan_m": False,
                "scan_n": False,
                "compare_models": False,
                "post_fit_models": False,
            }
        )
    elif product_fit_mode == "diagnostic_fit":
        next_settings.update(
            {
                "mode": "analyze",
                "fit_strategy": "quick_global",
                "sweep_strategies": True,
                "scan_m": True,
                "scan_n": True,
                "compare_models": True,
                "post_fit_models": True,
            }
        )
    return next_settings

