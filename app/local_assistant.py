from __future__ import annotations

from typing import Any


def _get(mapping: dict[str, Any], path: str, default: Any = None) -> Any:
    current: Any = mapping
    for key in path.split("."):
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def _as_float(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _fmt_pct(value: Any) -> str:
    number = _as_float(value)
    return "--" if number is None else f"{number:.2f}%"


def _fmt_value(value: Any) -> str:
    number = _as_float(value)
    return "--" if number is None else f"{number:.3g}"


def _contains(question: str, *terms: str) -> bool:
    lowered = question.lower()
    return any(term.lower() in lowered for term in terms)


def _fit_context(result: dict[str, Any]) -> dict[str, Any]:
    fit = result.get("fit") or {}
    diagnostics = fit.get("diagnostics") or {}
    post_models = result.get("post_fit_models") or []
    comparison_models = result.get("model_comparison") or []
    return {
        "fit": fit,
        "stats": fit.get("stats") or {},
        "diagnostics": diagnostics,
        "continuation": diagnostics.get("continuation") or {},
        "notes": result.get("notes") or [],
        "advice": result.get("advice") or [],
        "m_scan": result.get("m_scan") or [],
        "strategy_sweep": result.get("strategy_sweep") or [],
        "models": [*comparison_models, *post_models],
    }


def _model_mean(row: dict[str, Any]) -> float:
    value = _as_float(_get(row, "stats.mean"))
    return float("inf") if value is None else value


def _summary_answer(context: dict[str, Any]) -> str:
    stats = context["stats"]
    diagnostics = context["diagnostics"]
    weak = diagnostics.get("identifiability", {}).get("weak_parameters") or []
    worst_region = _get(diagnostics, "region_stats.worst_region", "--")
    weak_text = ", ".join(weak) if weak else "no obvious weak parameters"
    return (
        f"Current fit: mean error {_fmt_pct(stats.get('mean'))}, max error {_fmt_pct(stats.get('max'))}. "
        f"The worst region is {worst_region}. Strategy is {diagnostics.get('strategy', '--')}. "
        f"Identifiability: {weak_text}."
    )


def _region_answer(context: dict[str, Any]) -> str:
    region_stats = context["diagnostics"].get("region_stats") or {}
    parts = []
    for key in ("reverse", "near_zero", "forward", "high_forward"):
        row = region_stats.get(key) or {}
        parts.append(f"{key}: mean {_fmt_pct(row.get('mean'))}, max {_fmt_pct(row.get('max'))}")
    return "Region breakdown: " + "; ".join(parts) + "."


def _continuation_answer(context: dict[str, Any]) -> str:
    continuation = context["continuation"]
    stages = continuation.get("stages") or []
    core = continuation.get("core_window") or {}
    if not stages:
        return "This result does not contain a recorded continuation path. It likely used direct global fitting or fell back after a failed staged expansion."
    return (
        f"Continuation used {len(stages)} expansion stages from "
        f"{_fmt_value(core.get('low'))} V to {_fmt_value(core.get('high'))} V. "
        "If the error rises outside the core window, the current model is probably missing an outer-voltage mechanism rather than just needing more iterations."
    )


def _m_answer(context: dict[str, Any]) -> str:
    fit = context["fit"]
    scans = context["m_scan"]
    current_m = _as_float(fit.get("m"))
    if not scans:
        return f"Current m is {_fmt_value(current_m)}. No m scan table was recorded for this fit."
    best = scans[0]
    values = [_as_float(item.get("m")) for item in scans]
    values = [value for value in values if value is not None]
    best_m = _as_float(best.get("m"))
    edge = best_m in {min(values), max(values)} if values and best_m is not None else False
    edge_text = "The best m is on the scan boundary, so the range may still be too narrow." if edge else "The best m is inside the scanned range."
    return (
        f"Current m is {_fmt_value(current_m)}. Best scanned m is {_fmt_value(best_m)} "
        f"with mean error {_fmt_pct(_get(best, 'stats.mean'))}. {edge_text}"
    )


def _strategy_answer(context: dict[str, Any]) -> str:
    sweep = context["strategy_sweep"]
    strategy = context["diagnostics"].get("strategy", "--")
    if not sweep:
        return f"Current strategy is {strategy}. No strategy sweep was recorded."
    best = sweep[0]
    return (
        f"Final strategy is {strategy}. The sweep leader is "
        f"{best.get('preset') or best.get('strategy') or '--'} with mean error "
        f"{_fmt_pct(_get(best, 'stats.mean'))} and score {best.get('score', '--')}."
    )


def _model_answer(context: dict[str, Any]) -> str:
    models = [row for row in context["models"] if isinstance(row, dict)]
    if not models:
        return "No model diagnostics were recorded for this result."
    best = sorted(models, key=_model_mean)[0]
    confidence = _get(best, "diagnostics.physical_confidence", _get(best, "diagnostics.publication_confidence", "--"))
    decision = "selected for replacement" if _get(best, "diagnostics.selected_for_replacement") else "diagnostic only"
    return (
        f"Best diagnostic model by mean error is {best.get('name', '--')} "
        f"with mean {_fmt_pct(_get(best, 'stats.mean'))} and max {_fmt_pct(_get(best, 'stats.max'))}. "
        f"Physical confidence: {confidence}. Decision: {decision}."
    )


def _parameter_answer(context: dict[str, Any]) -> str:
    fit = context["fit"]
    params = fit.get("params") or []
    weak = context["diagnostics"].get("identifiability", {}).get("weak_parameters") or []
    weak_text = ", ".join(weak) if weak else "none flagged"
    if len(params) < 4:
        return "The current result does not contain a complete parameter vector."
    return (
        f"Parameters: J0={params[0]:.3e}, Rs={params[1]:.3e}, Rsh={params[2]:.3e}, "
        f"k={params[3]:.3e}, m={_fmt_value(fit.get('m'))}. Weak parameters: {weak_text}."
    )


def _next_step_answer(context: dict[str, Any]) -> str:
    advice = context["advice"]
    if not advice:
        return "No structured next-step advice was generated for this result."
    first = advice[0]
    detail = " ".join(part for part in [first.get("detail"), first.get("action")] if part)
    return f"Top next step: {first.get('title', 'Next step')}. {detail}"


def answer_local_assistant(
    question: str,
    result: dict[str, Any],
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    context = _fit_context(result)
    prompt = (question or "").strip()
    history = history or []

    if not prompt:
        answer = _summary_answer(context)
    elif _contains(prompt, "collapse", "window", "continuation", "range", "expand"):
        answer = _continuation_answer(context)
    elif _contains(prompt, "m ", " m", "scan m", "best m", "power"):
        answer = _m_answer(context)
    elif _contains(prompt, "strategy", "algorithm", "fit mode", "sweep"):
        answer = _strategy_answer(context)
    elif _contains(prompt, "model", "leakage", "diode", "srh", "interface", "heterointerface"):
        answer = _model_answer(context)
    elif _contains(prompt, "error", "region", "reverse", "forward", "where", "worst"):
        answer = _region_answer(context)
    elif _contains(prompt, "parameter", "j0", "rs", "rsh", "k", "identifiability"):
        answer = _parameter_answer(context)
    elif _contains(prompt, "next", "advice", "suggest", "try"):
        answer = _next_step_answer(context)
    else:
        answer = _summary_answer(context) + " Ask about error regions, m scan, model diagnostics, strategy, or a specific parameter for a narrower answer."

    return {
        "status": "ready",
        "answer": answer,
        "history_count": len(history),
        "suggestions": [
            "Which voltage region limits this fit?",
            "Is m still identifiable?",
            "Which candidate model is closest?",
        ],
    }
