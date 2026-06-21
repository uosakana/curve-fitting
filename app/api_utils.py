from __future__ import annotations

import json
import hashlib
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

import numpy as np

from ml.record_schema import component_series_is_complete, normalize_record_payload
from fit.advice import build_fit_advice
from fit.parameter_schema import (
    DEFAULT_M,
    DEFAULT_M_VALUES,
    DEFAULT_N,
    DEFAULT_N_VALUES,
    POST_FIT_EVALUATOR_KIND,
    fit_contract_payload,
    manual_capability_payload,
    model_context_payload,
    parameter_schema_payload,
    params_meta_from_values,
)


if getattr(sys, "frozen", False):
    RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    RUNTIME_ROOT = Path(sys.executable).resolve().parent
else:
    RESOURCE_ROOT = Path(__file__).resolve().parents[1]
    RUNTIME_ROOT = RESOURCE_ROOT

ROOT = RUNTIME_ROOT
STATIC_DIR = RESOURCE_ROOT / "app" / "static"
UPLOAD_DIR = RUNTIME_ROOT / "app_data" / "uploads"
RECORD_DIR = RUNTIME_ROOT / "app_data" / "records"
UPLOADS: dict[str, Path] = {}


class FitResultPayload(TypedDict, total=False):
    schema_version: int
    dataset: dict[str, Any]
    fit: dict[str, Any] | None
    series: dict[str, Any]
    diagnostics: dict[str, Any]
    model_context: dict[str, Any]
    parameter_schema: dict[str, Any]
    manual_capability: dict[str, Any]
    evaluator_kind: str
    candidates: list[dict[str, Any]]
    product_fit_mode: str
    run_snapshot: dict[str, Any]


def safe_name(name: str | None) -> str:
    base = Path(name or "upload").name
    safe = re.sub(r"[^A-Za-z0-9_.\-\u4e00-\u9fff]+", "_", base).strip("._")
    return safe or "upload"


def save_upload(filename: str | None, content: bytes) -> tuple[str, Path]:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    upload_id = uuid.uuid4().hex
    file_path = UPLOAD_DIR / f"{upload_id}_{safe_name(filename)}"
    file_path.write_bytes(content)
    UPLOADS[upload_id] = file_path
    return upload_id, file_path


def cleanup_uploads(
    *,
    upload_dir: str | Path | None = None,
    upload_map: dict[str, Path] | None = None,
    all_files: bool = False,
) -> dict[str, Any]:
    directory = Path(upload_dir) if upload_dir is not None else UPLOAD_DIR
    directory = directory.resolve()
    uploads = UPLOADS if upload_map is None else upload_map
    targets: set[Path] = set()

    if all_files and directory.exists():
        targets.update(path for path in directory.rglob("*") if path.is_file())
    else:
        targets.update(Path(path) for path in uploads.values())

    deleted_files = 0
    deleted_bytes = 0
    errors: list[str] = []
    deleted_paths: set[Path] = set()

    for target in sorted(targets):
        path = target.resolve()
        if directory not in path.parents:
            errors.append(f"Skipped path outside upload dir: {path}")
            continue
        if not path.exists():
            deleted_paths.add(path)
            continue
        if not path.is_file():
            continue
        try:
            size = path.stat().st_size
            path.unlink()
            deleted_files += 1
            deleted_bytes += size
            deleted_paths.add(path)
        except OSError as exc:
            errors.append(f"{path}: {exc}")

    if all_files:
        uploads.clear()
    else:
        for upload_id, path in list(uploads.items()):
            if Path(path).resolve() in deleted_paths:
                uploads.pop(upload_id, None)

    if directory.exists():
        for child in sorted((path for path in directory.rglob("*") if path.is_dir()), reverse=True):
            try:
                child.rmdir()
            except OSError:
                pass

    return {
        "deleted_files": deleted_files,
        "deleted_bytes": deleted_bytes,
        "errors": errors,
    }


def save_record(payload: dict[str, Any]) -> Path:
    RECORD_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    record_id = uuid.uuid4().hex[:8]
    saved_at = datetime.now().isoformat(timespec="seconds")
    record = json_compatible(
        normalize_record_payload(payload, record_id=record_id, saved_at=saved_at)
    )
    if not component_series_is_complete(record.get("component_series")):
        raise ValueError("Training record must include voltage, measured, fitted, diode, ohmic, and non-ohmic series.")
    path = RECORD_DIR / f"fit_record_{timestamp}_{record_id}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def none_if_blank(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def parse_m_values(raw: str | None) -> tuple[float, ...]:
    values = [part.strip() for part in re.split(r"[,;\s]+", raw or "") if part.strip()]
    if not values:
        return DEFAULT_M_VALUES
    parsed = tuple(float(value) for value in values)
    if any(value <= 0.0 for value in parsed):
        raise ValueError("m_values must be positive.")
    return parsed


def parse_n_values(raw: str | None) -> tuple[float, ...]:
    values = [part.strip() for part in re.split(r"[,;\s]+", raw or "") if part.strip()]
    if not values:
        return DEFAULT_N_VALUES
    parsed = tuple(float(value) for value in values)
    if any(value <= 0.0 for value in parsed):
        raise ValueError("n_values must be positive.")
    return parsed


def optional_float(raw: str | float | None) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, float):
        return raw
    value = str(raw).strip()
    if not value:
        return None
    return float(value)


def parse_params(j0: str, rs: str, rsh: str, k: str) -> np.ndarray:
    values = np.array([float(j0), float(rs), float(rsh), float(k)], dtype=float)
    if values.size != 4 or not np.all(np.isfinite(values)):
        raise ValueError("Parameters must be finite numeric values.")
    if np.any(values <= 0.0):
        raise ValueError("J0, Rs, Rsh, and k must all be positive.")
    return values


def json_compatible(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return json_compatible(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_compatible(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def serialize_file_info(info) -> dict[str, Any]:
    return {
        "path": str(info.path),
        "suffix": info.suffix,
        "sheets": info.sheets,
        "selected_sheet": info.selected_sheet,
        "shape": info.shape,
        "preview": info.preview,
    }


def serialize_grid_window(window) -> dict[str, Any]:
    return {
        "path": str(window.path),
        "suffix": window.suffix,
        "sheet_name": window.sheet_name,
        "shape": window.shape,
        "row_offset": window.row_offset,
        "col_offset": window.col_offset,
        "rows": window.rows,
    }


def dataset_import_notes(source: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    voltage = source.get("voltage_inference") or {}
    if voltage.get("action") == "inferred_excel_column":
        notes.append(f"Voltage range was auto-detected as {voltage.get('voltage_range')}.")
    elif voltage.get("action") == "generated":
        notes.append("No voltage column was auto-detected; generated voltage settings were used.")

    sign = source.get("current_sign_convention") or {}
    action = sign.get("action")
    if action in {"flip_all", "reverse_magnitude_to_negative", "forward_magnitude_to_positive", "signed_by_voltage"}:
        notes.append(sign.get("message") or "Current signs were normalized to the internal signed-current convention.")
    elif action == "ambiguous":
        notes.append("Current sign pattern was ambiguous, so imported current signs were left unchanged.")
    return notes


def _numeric_range(values: Any) -> dict[str, Any] | None:
    try:
        array = np.asarray(values, dtype=float)
    except (TypeError, ValueError):
        return None
    if array.size == 0:
        return None
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return None
    minimum = float(np.min(finite))
    maximum = float(np.max(finite))
    return {
        "min": minimum,
        "max": maximum,
        "span": maximum - minimum,
    }


def _snapshot_hash(snapshot: dict[str, Any]) -> str:
    stable = json.dumps(json_compatible(snapshot), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()[:12]


def _snapshot_settings(settings: dict[str, Any] | None, product_fit_mode: str | None) -> dict[str, Any]:
    if settings is None:
        settings = {}
    keys = (
        "fit_strategy",
        "sweep_strategies",
        "scan_m",
        "scan_n",
        "use_best_m_after_scan",
        "compare_models",
        "post_fit_models",
        "ml_assist_enabled",
        "ml_assist_mode",
    )
    payload = {key: settings.get(key) for key in keys if key in settings}
    if product_fit_mode:
        payload["product_fit_mode"] = product_fit_mode
    return payload


def run_snapshot_payload(
    dataset,
    analysis,
    *,
    product_fit_mode: str | None = None,
    analysis_settings: dict[str, Any] | None = None,
    ranked_candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    source = dataset.source or {}
    source_path = source.get("path") or ""
    path = Path(source_path) if source_path else None
    fit = getattr(analysis, "fit", None)
    diagnostics = getattr(fit, "diagnostics", {}) if fit is not None else {}
    stats = getattr(fit, "stats", {}) if fit is not None else {}
    config = getattr(analysis, "config", None) or getattr(fit, "config", None)
    current_model_label = (
        diagnostics.get("candidate_label")
        or diagnostics.get("model_name")
        or diagnostics.get("model_stage")
        or diagnostics.get("display_fit_source")
        or "current_fit"
    )
    snapshot = {
        "schema_version": 1,
        "data": {
            "file_name": path.name if path is not None else source_path,
            "path": source_path,
            "suffix": source.get("suffix") or (path.suffix.lower() if path is not None else ""),
            "source_mode": source.get("mode"),
            "sheet_name": source.get("sheet_name"),
            "cell_range": source.get("cell_range"),
            "voltage_range": source.get("voltage_range"),
            "current_range": source.get("current_range"),
            "generated_voltage": {
                "start": source.get("voltage_start"),
                "end": source.get("voltage_end"),
                "step": source.get("voltage_step"),
            },
            "points": int(source.get("points") or len(dataset.data_v)),
            "voltage": _numeric_range(dataset.data_v),
            "current": _numeric_range(dataset.data_jd),
        },
        "analysis": {
            "settings": _snapshot_settings(analysis_settings, product_fit_mode),
            "candidate_counts": {
                "ranked": len(ranked_candidates or []),
                "strategy": len(getattr(analysis, "strategy_sweep", []) or []),
                "nm_profile": len(getattr(analysis, "m_scan", []) or []),
                "m_models": len(getattr(analysis, "model_comparison", []) or []),
                "post_fit": len(getattr(analysis, "post_fit_models", []) or []),
            },
            "current_model": {
                "source": diagnostics.get("display_fit_source") or "primary_fit",
                "label": current_model_label,
                "mean_error": stats.get("mean"),
                "max_error": stats.get("max"),
            },
        },
        "engine": {},
    }
    if config is not None:
        snapshot["engine"] = {
            "random_seed": getattr(getattr(config, "optimization", None), "random_seed", None),
            "multistart_points": getattr(getattr(config, "optimization", None), "multistart_points", None),
            "physics_n": getattr(getattr(config, "physics", None), "n", None),
            "physics_m": getattr(getattr(config, "physics", None), "m", None),
            "temperature_K": getattr(getattr(config, "physics", None), "T", None),
        }
    snapshot["snapshot_id"] = f"run_{_snapshot_hash(snapshot)}"
    return json_compatible(snapshot)


def serialize_model_fit(item) -> dict[str, Any]:
    diagnostics = item.diagnostics
    return {
        "name": item.spec.name,
        "stage": item.spec.stage,
        "category": item.spec.category,
        "report_role": item.spec.report_role,
        "description": item.spec.description,
        "params": item.params,
        "stats": item.stats,
        "aic": item.aic,
        "bic": item.bic,
        "free_parameter_count": item.free_parameter_count,
        "is_recommended_baseline": bool(diagnostics.get("selected_for_baseline")),
        "recommended_baseline_stage": diagnostics.get("recommended_baseline_stage"),
        "diagnostics": diagnostics,
    }


def serialize_fit(result) -> dict[str, Any]:
    fit = result.fit
    model_rows = [serialize_model_fit(item) for item in result.model_comparison]
    recommended_baseline = next((row for row in model_rows if row.get("is_recommended_baseline")), None)
    model_selection = None
    if recommended_baseline:
        model_selection = (recommended_baseline.get("diagnostics") or {}).get("model_selection")
    if model_selection is None:
        model_selection = next(
            (
                (row.get("diagnostics") or {}).get("model_selection")
                for row in model_rows
                if isinstance((row.get("diagnostics") or {}).get("model_selection"), dict)
            ),
            None,
        )
    diagnostic_ablations = [
        row for row in model_rows if row.get("category") == "diagnostic_ablation"
    ]
    payload: dict[str, Any] = {
        "notes": result.notes,
        "advice": build_fit_advice(result.fit, result.model_comparison, result.m_scan) if result.fit is not None else [],
        "strategy_sweep": [
            {
                "preset": item.diagnostics.get("strategy_preset") or item.diagnostics.get("strategy"),
                "strategy": item.diagnostics.get("strategy"),
                "score": item.diagnostics.get("composite_score"),
                "score_terms": item.diagnostics.get("score_terms", {}),
                "m": item.m,
                "params": item.params,
                "stats": item.stats,
                "region_stats": item.diagnostics.get("region_stats", {}),
                "boundary_hit_count": len(item.diagnostics.get("boundary_hits") or []),
                "warning_count": len(item.diagnostics.get("warnings") or []),
            }
            for item in getattr(result, "strategy_sweep", [])
        ],
        "m_scan": [
            {
                "n": item.n,
                "m": item.m,
                "params": item.params,
                "stats": item.stats,
                "diagnostics": item.diagnostics,
            }
            for item in result.m_scan
        ],
        "model_comparison": model_rows,
        "model_selection": model_selection,
        "recommended_baseline_model": recommended_baseline,
        "diagnostic_ablation_models": diagnostic_ablations,
        "post_fit_models": getattr(result, "post_fit_models", []),
    }
    if fit is None:
        payload["fit"] = None
        return payload

    payload["fit"] = {
        "n": fit.n,
        "m": fit.m,
        "params": fit.params,
        "stats": fit.stats,
        "diagnostics": fit.diagnostics,
        "series": {},
    }
    return payload


def _fit_series(dataset, fit) -> dict[str, Any]:
    series = {
        "voltage": dataset.data_v,
        "measured": dataset.data_jd,
        "fitted": fit.fit_results["JD"],
        "diode": fit.currents.diode,
        "ohmic": fit.currents.ohmic,
        "nonohmic": fit.currents.nonohmic,
        "relative_error": fit.fit_results["relative_errors"],
    }
    for key in (
        "recombination",
        "diffusion",
        "empirical_nonohmic",
        "extra_current",
        "extended_nonohmic_total",
        "v_drop",
    ):
        values = fit.fit_results.get(key)
        if values is not None:
            series[key] = values
    return series


def _fit_candidate_payload(
    dataset,
    fit,
    *,
    source: str,
    label: str,
    reason: str,
    is_primary: bool = False,
    diagnostic_only: bool = False,
) -> dict[str, Any]:
    manual_capability = manual_capability_payload(fit)
    series = _fit_series(dataset, fit)
    return {
        "source": source,
        "label": label,
        "reason": reason,
        "is_primary": is_primary,
        "diagnostic_only": diagnostic_only,
        "promotable": not diagnostic_only,
        "n": fit.n,
        "m": fit.m,
        "params": fit.params,
        "stats": fit.stats,
        "model_context": model_context_payload(fit),
        "parameter_schema": parameter_schema_payload(fit),
        "manual_capability": manual_capability,
        "evaluator_kind": manual_capability["evaluator_kind"],
        "fit": {
            "n": fit.n,
            "m": fit.m,
            "params": fit.params,
            "stats": fit.stats,
            "diagnostics": fit.diagnostics,
            "series": series,
        },
        "series": series,
    }


def _model_candidate_payload(row: dict[str, Any]) -> dict[str, Any]:
    category = row.get("category")
    diagnostic_only = category == "diagnostic_ablation"
    label = row.get("display_name") or f"{row.get('stage') or 'M?'}: {row.get('name') or 'model'}"
    return {
        "source": "diagnostic_ablation" if diagnostic_only else "baseline_family",
        "label": label,
        "reason": "Baseline family comparison candidate.",
        "is_primary": False,
        "diagnostic_only": diagnostic_only,
        "promotable": False,
        "n": None,
        "m": None,
        "params": row.get("params"),
        "stats": row.get("stats") or {},
        "model_context": {"model_stage": row.get("stage"), "model_name": row.get("name")},
        "manual_capability": {
            "can_evaluate": False,
            "evaluator_kind": "baseline_family_summary",
            "reason": "This candidate is a serialized model comparison row; promotion will be handled by the candidate switch flow.",
        },
        "evaluator_kind": "baseline_family_summary",
        "fit": None,
    }


def _post_fit_parameter_schema(row: dict[str, Any], diagnostics: dict[str, Any]) -> dict[str, Any]:
    raw_params = row.get("params")
    raw_names = row.get("param_names")
    params = list(raw_params) if raw_params is not None else []
    names = list(raw_names) if raw_names is not None else []
    if not names:
        names = [f"p{index + 1}" for index in range(len(params))]
    parameters: list[dict[str, Any]] = []
    for index, name in enumerate(names):
        item: dict[str, Any] = {"name": str(name)}
        if index < len(params):
            try:
                item["value"] = float(params[index])
            except (TypeError, ValueError):
                item["value"] = params[index]
        parameters.append(item)
    fixed_ideality = diagnostics.get("fixed_ideality") or {}
    return {
        "kind": POST_FIT_EVALUATOR_KIND,
        "parameters": parameters,
        "exponents": {
            "n": float(row.get("n") or fixed_ideality.get("recombination") or DEFAULT_N),
            "m": float(row.get("m") or fixed_ideality.get("diffusion") or DEFAULT_M),
        },
        "optimizer_space": None,
    }


def _post_fit_candidate_payload(row: dict[str, Any]) -> dict[str, Any]:
    diagnostics = row.get("diagnostics") or {}
    return {
        "source": "post_fit_diagnostic",
        "label": row.get("name") or diagnostics.get("model_stage") or "Post-fit diagnostic",
        "reason": diagnostics.get("selection_reason") or "Physical diagnostic candidate.",
        "is_primary": False,
        "diagnostic_only": not bool(diagnostics.get("selected_for_replacement")),
        "promotable": bool(diagnostics.get("selected_for_replacement")),
        "n": row.get("n"),
        "m": row.get("m"),
        "params": row.get("params"),
        "stats": row.get("stats") or {},
        "diagnostics": diagnostics,
        "model_context": {"model_stage": diagnostics.get("model_stage"), "model_name": row.get("name")},
        "parameter_schema": _post_fit_parameter_schema(row, diagnostics),
        "manual_capability": {
            "can_evaluate": False,
            "evaluator_kind": POST_FIT_EVALUATOR_KIND,
            "reason": "Post-fit candidates are not reproducible by the base manual evaluator.",
        },
        "evaluator_kind": POST_FIT_EVALUATOR_KIND,
        "fit": None,
        "series": row.get("series"),
    }


def _candidate_sort_key(candidate: dict[str, Any]) -> tuple[float, float, int]:
    stats = candidate.get("stats") or {}
    mean = stats.get("mean")
    max_error = stats.get("max")
    try:
        mean_value = float(mean)
    except (TypeError, ValueError):
        mean_value = float("inf")
    try:
        max_value = float(max_error)
    except (TypeError, ValueError):
        max_value = float("inf")
    priority = 0 if candidate.get("is_primary") else 1
    return (mean_value, max_value, priority)


def analysis_candidates_payload(dataset, analysis, model_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if analysis.fit is not None:
        source = analysis.fit.diagnostics.get("display_fit_source") or "primary_fit"
        candidates.append(_fit_candidate_payload(
            dataset,
            analysis.fit,
            source=source,
            label="Primary fit",
            reason="Current displayed fit.",
            is_primary=True,
            diagnostic_only=False,
        ))
    for item in getattr(analysis, "strategy_sweep", []) or []:
        label = item.diagnostics.get("strategy_preset") or item.diagnostics.get("strategy") or "Strategy candidate"
        candidates.append(_fit_candidate_payload(
            dataset,
            item,
            source="strategy_sweep",
            label=str(label),
            reason="Strategy sweep candidate.",
        ))
    for item in getattr(analysis, "m_scan", []) or []:
        candidates.append(_fit_candidate_payload(
            dataset,
            item,
            source="nm_profile",
            label=f"Effective n/m profile n={float(item.n):.3g}, m={float(item.m):.3g}",
            reason="Effective exponent profile candidate.",
        ))
    candidates.extend(_model_candidate_payload(row) for row in model_rows)
    candidates.extend(_post_fit_candidate_payload(row) for row in getattr(analysis, "post_fit_models", []) or [])

    ranked = sorted(candidates, key=_candidate_sort_key)[:3]
    for index, candidate in enumerate(ranked, start=1):
        candidate["rank"] = index
    return ranked


def _attach_fit_result_contract(payload: dict[str, Any], dataset, fit, series: dict[str, Any]) -> FitResultPayload:
    manual_capability = manual_capability_payload(fit)
    payload["schema_version"] = 1
    payload["dataset"] = dataset.source
    payload["series"] = series
    payload["diagnostics"] = fit.diagnostics
    payload["model_context"] = model_context_payload(fit)
    payload["parameter_schema"] = parameter_schema_payload(fit)
    payload["manual_capability"] = manual_capability
    payload["evaluator_kind"] = manual_capability["evaluator_kind"]
    if payload.get("fit") is not None:
        payload["fit"]["diagnostics"] = fit.diagnostics
        payload["fit"]["series"] = series
    return payload


def fit_payload(dataset, fit, *, notes: list[str] | None = None) -> FitResultPayload:
    import_notes = dataset_import_notes(dataset.source)
    series = _fit_series(dataset, fit)
    payload: dict[str, Any] = {
        "dataset": dataset.source,
        "notes": import_notes + (notes or []),
        "advice": build_fit_advice(fit),
        "m_scan": [],
        "model_comparison": [],
        "candidates": [],
        "fit": {
            "n": fit.n,
            "m": fit.m,
            "params": fit.params,
            "stats": fit.stats,
            "diagnostics": fit.diagnostics,
            "series": series,
        },
    }
    payload["candidates"] = [
        {
            **_fit_candidate_payload(
                dataset,
                fit,
                source=fit.diagnostics.get("display_fit_source") or "primary_fit",
                label="Primary fit",
                reason="Current displayed fit.",
                is_primary=True,
            ),
            "rank": 1,
        }
    ]
    _attach_fit_result_contract(payload, dataset, fit, series)
    return json_compatible(payload)


def analysis_payload(dataset, analysis) -> FitResultPayload:
    fit = analysis.fit
    if fit is None:
        raise RuntimeError("Analysis did not produce a fit result.")

    payload = serialize_fit(analysis)
    payload["notes"] = dataset_import_notes(dataset.source) + list(payload.get("notes") or [])
    payload["candidates"] = analysis_candidates_payload(dataset, analysis, payload.get("model_comparison", []))
    payload["run_snapshot"] = run_snapshot_payload(
        dataset,
        analysis,
        ranked_candidates=payload["candidates"],
    )
    _attach_fit_result_contract(payload, dataset, fit, _fit_series(dataset, fit))
    return json_compatible(payload)
