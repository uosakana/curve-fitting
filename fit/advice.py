from __future__ import annotations

from typing import Any


def _as_float(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number


def _region_mean(region_stats: dict[str, Any], name: str) -> float | None:
    row = region_stats.get(name)
    if not isinstance(row, dict):
        return None
    return _as_float(row.get("mean"))


def _strategy_settings(strategy: str, weights: dict[str, float] | None = None) -> dict[str, Any]:
    return {
        "fit_strategy": strategy,
        "region_weights": weights or {},
    }


def _advice(
    level: str,
    title: str,
    detail: str,
    action: str,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "level": level,
        "title": title,
        "detail": detail,
        "action": action,
        "settings": settings or {},
    }


def build_fit_advice(result: Any, model_comparison: list[Any] | None = None, m_scan: list[Any] | None = None) -> list[dict[str, Any]]:
    """Convert fit diagnostics into concrete next-step suggestions.

    This is intentionally rule-based. It gives the user traceable fitting actions
    before there is enough labeled data for a trained model.
    """

    fit = getattr(result, "fit", None) or result
    diagnostics = getattr(fit, "diagnostics", None) or {}
    stats = getattr(fit, "stats", None) or diagnostics.get("stats", {}) or {}
    region_stats = diagnostics.get("region_stats", {}) or {}
    warnings = diagnostics.get("warnings", []) or []
    boundary_hits = diagnostics.get("boundary_hits", []) or []
    component = diagnostics.get("component_percent", {}) or {}
    m_value = _as_float(getattr(fit, "m", None))

    mean_error = _as_float(stats.get("mean"), 0.0) or 0.0
    max_error = _as_float(stats.get("max"), 0.0) or 0.0
    worst_region = region_stats.get("worst_region") if isinstance(region_stats, dict) else None
    advice: list[dict[str, Any]] = []

    if mean_error <= 5.0 and max_error <= 25.0 and not boundary_hits:
        advice.append(
            _advice(
                "ok",
                "Fit is numerically stable",
                "Aggregate error is low and no fitted parameter is pinned to a bound.",
                "Use the physical evidence and sample context to decide whether this result is interpretable.",
            )
        )
    elif mean_error > 10.0 or max_error > 50.0:
        advice.append(
            _advice(
                "warning",
                "Fit error is still high",
                f"Mean error is {mean_error:.2f}% and max error is {max_error:.2f}%.",
                "Try Robust Global or Sweep Strategies before treating fitted leakage components as strong physical evidence.",
            )
        )

    if worst_region == "reverse":
        reverse_mean = _region_mean(region_stats, "reverse")
        advice.append(
            _advice(
                "action",
                "Reverse-bias region limits the fit",
                f"Reverse mean error is {reverse_mean:.2f}%." if reverse_mean is not None else "Reverse region has the worst mean error.",
                "Try Weighted Regions with higher reverse weight, then compare ohmic-only and non-ohmic-only leakage models.",
                _strategy_settings(
                    "weighted_regions",
                    {"reverse": 2.5, "near_zero": 0.4, "forward": 1.0, "high_forward": 1.2},
                ),
            )
        )
    elif worst_region == "near_zero":
        advice.append(
            _advice(
                "action",
                "Near-zero points dominate the residual",
                "The current around 0 V is often close to the noise floor or sign-crossing region.",
                "Downweight near-zero voltage points or narrow the selected voltage window before interpreting component fractions.",
                _strategy_settings(
                    "weighted_regions",
                    {"reverse": 1.5, "near_zero": 0.2, "forward": 1.0, "high_forward": 1.5},
                ),
            )
        )
    elif worst_region == "forward":
        advice.append(
            _advice(
                "action",
                "Forward region needs J0/Rs attention",
                "Low-to-mid forward voltage is usually sensitive to saturation current and series resistance coupling.",
                "Try Staged Physical or optimize from the current manual parameters after adjusting J0 and Rs.",
                _strategy_settings("staged_physical"),
            )
        )
    elif worst_region == "high_forward":
        advice.append(
            _advice(
                "action",
                "High-forward region needs stronger constraint",
                "High forward voltage is usually where Rs and the diode exponential compete most strongly.",
                "Try Staged Physical or increase high-forward weight; inspect whether Rs is physically reasonable.",
                _strategy_settings(
                    "weighted_regions",
                    {"reverse": 1.2, "near_zero": 0.4, "forward": 1.0, "high_forward": 2.5},
                ),
            )
        )

    for hit in boundary_hits:
        parameter = hit.get("parameter", "parameter")
        side = hit.get("side", "bound")
        advice.append(
            _advice(
                "warning",
                f"{parameter} reached the {side} bound",
                "A boundary hit usually means the selected model, voltage window, or parameter bound is controlling the answer.",
                "Treat this parameter as weakly identifiable; rerun with a narrower window or review the bound before assigning physical meaning.",
            )
        )

    leakage_ratio = _as_float(diagnostics.get("negative_leakage_nonohmic_to_ohmic"))
    if leakage_ratio is not None and leakage_ratio > 1e3:
        advice.append(
            _advice(
                "warning",
                "Ohmic and non-ohmic leakage are not well separated",
                f"The reverse-region non-ohmic/ohmic ratio is {leakage_ratio:.2e}.",
                "Interpret Rsh and k together unless model comparison and external evidence support separating them.",
            )
        )

    nonohmic_pct = _as_float(component.get("nonohmic"))
    ohmic_pct = _as_float(component.get("ohmic"))
    if nonohmic_pct is not None and ohmic_pct is not None and nonohmic_pct > 80.0 and ohmic_pct < 5.0:
        advice.append(
            _advice(
                "info",
                "Non-ohmic term dominates the fitted leakage",
                f"Mean component share is non-ohmic {nonohmic_pct:.1f}% versus ohmic {ohmic_pct:.1f}%.",
                "Check whether this agrees with morphology, interlayer, or reference-device evidence before using it as a mechanism claim.",
            )
        )

    for warning in warnings:
        if "excluded" in str(warning).lower():
            advice.append(
                _advice(
                    "info",
                    "Some points were excluded from aggregate errors",
                    str(warning),
                    "Inspect the error plot near 0 V; this is usually acceptable when currents are near the noise floor.",
                )
            )

    scans = list(m_scan or [])
    if scans:
        best_m = _as_float(getattr(scans[0], "m", None))
        best_n = _as_float(getattr(scans[0], "n", None))
        grid = [_as_float(getattr(item, "m", None)) for item in scans]
        clean_grid = [value for value in grid if value is not None]
        if best_m is not None and clean_grid and best_m in {min(clean_grid), max(clean_grid)}:
            advice.append(
                _advice(
                    "action",
                    "Best exponent is at the scan edge",
                    f"The best scanned m is {best_m:.3g}, while the current grid spans {min(clean_grid):.3g} to {max(clean_grid):.3g}.",
                    "Expand the exponent grid before deciding that the value is physically meaningful.",
                    {"scan_m": True, "m_center": best_m},
                )
            )
        elif best_m is not None and m_value is not None and abs(best_m - m_value) < 1e-9:
            advice.append(
                _advice(
                    "ok",
                    "Final fit uses the best scanned exponent profile",
                    f"The final fit and exponent profile agree at n={best_n:.3g}, m={best_m:.3g}." if best_n is not None else f"The final fit and m scan agree at m={best_m:.3g}.",
                    "Keep this profile for the current window unless external evidence suggests different exponent bounds.",
                )
            )

    models = [
        item
        for item in (model_comparison or [])
        if getattr(getattr(item, "spec", None), "category", "baseline_chain") == "baseline_chain"
    ]
    if len(models) >= 2:
        best = models[0]
        second = models[1]
        best_name = getattr(getattr(best, "spec", None), "name", None)
        second_bic = _as_float(getattr(second, "bic", None))
        best_bic = _as_float(getattr(best, "bic", None))
        if best_name and best_bic is not None and second_bic is not None:
            delta = second_bic - best_bic
            if delta > 6.0 and best_name != "full":
                advice.append(
                    _advice(
                        "action",
                        "Simpler leakage model is favored",
                        f"{best_name} wins by BIC delta {delta:.2f}.",
                        "Use the simpler model as a competing explanation; do not over-interpret unused leakage components.",
                        {"preferred_model": best_name},
                    )
                )

    if not advice:
        advice.append(
            _advice(
                "info",
                "No strong fitting issue detected",
                "Diagnostics did not trigger a specific rule.",
                "Use manual adjustment and external evidence to decide whether the current solution is physically useful.",
            )
        )

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in advice:
        key = (item["level"], item["title"])
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped
