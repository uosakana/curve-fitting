from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.optimize import least_squares
from scipy.special import lambertw

from fit.model import diode_model, relative_errors, valid_error_mask
from fit.parameter_schema import PARAM_LB, PARAM_NAMES, PARAM_SCALE, PARAM_UB


def _as_vector(values) -> np.ndarray:
    return np.asarray(values, dtype=float).reshape(-1)


def _collapse_duplicate_voltage(voltage: np.ndarray, current: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    voltage = _as_vector(voltage)
    current = _as_vector(current)
    if voltage.size <= 1:
        return voltage, current

    order = np.argsort(voltage, kind="mergesort")
    voltage = voltage[order]
    current = current[order]
    unique_voltage, inverse = np.unique(voltage, return_inverse=True)
    if unique_voltage.size == voltage.size:
        return voltage, current

    reduced_current = np.zeros_like(unique_voltage, dtype=float)
    for idx in range(unique_voltage.size):
        reduced_current[idx] = float(np.median(current[inverse == idx]))
    return unique_voltage, reduced_current


def _smooth(values: np.ndarray, window: int = 5) -> np.ndarray:
    series = _as_vector(values)
    if series.size < 3:
        return series.copy()

    window = max(3, min(int(window), int(series.size)))
    if window % 2 == 0:
        window -= 1
    if window <= 1:
        return series.copy()

    pad = window // 2
    kernel = np.ones(window, dtype=float) / float(window)
    padded = np.pad(series, pad, mode="edge")
    return np.convolve(padded, kernel, mode="valid")


def _current_with_lambert_w(v: float, j0: float, rs: float, rsh: float, n: float, v_th: float) -> float:
    exponent = (rsh * (rs * j0 + v)) / (n * v_th * (rs + rsh))
    factor = (rs * rsh * j0) / (n * v_th * (rs + rsh))
    x = factor * np.exp(np.clip(exponent, -700.0, 700.0))
    w = lambertw(x).real
    return float((n * v_th / rs) * w - (rsh * j0 - v) / (rs + rsh))


def _solve_j0_for_point(v: float, current: float, rs: float, rsh: float, n: float, v_th: float) -> float:
    def residual(arr: np.ndarray) -> np.ndarray:
        j0 = float(arr[0])
        return np.array([_current_with_lambert_w(v, j0, rs, rsh, n, v_th) - current])

    starts = np.array([1e-9, 1e-12, 1e-6], dtype=float)
    best_x = starts[0]
    best_cost = np.inf
    for start in starts:
        result = least_squares(
            residual,
            x0=np.array([start]),
            bounds=(np.array([PARAM_LB[0]]), np.array([PARAM_UB[0]])),
            method="trf",
            ftol=1e-12,
            xtol=1e-12,
            gtol=1e-12,
            max_nfev=500,
        )
        cost = 2.0 * result.cost
        if result.success and cost < best_cost:
            best_cost = cost
            best_x = float(result.x[0])
    return float(best_x)


def _initial_score(data_v: np.ndarray, data_jd: np.ndarray, params: np.ndarray, config) -> float:
    try:
        predicted = diode_model(data_v, params, config)
    except Exception:
        return float("inf")

    rel = relative_errors(predicted, data_jd)
    valid = valid_error_mask(
        data_v,
        data_jd,
        voltage_zero_atol=config.fitting.voltage_zero_atol,
        current_noise_floor=config.fitting.current_noise_floor,
    )
    if not np.any(valid):
        valid = np.isfinite(rel)
    if not np.any(valid):
        return float("inf")
    return float(np.mean(rel[valid]) + 0.10 * np.max(rel[valid]))


def _estimate_rs_from_didv(voltage: np.ndarray, current: np.ndarray, config) -> float:
    noise = float(config.fitting.current_noise_floor)
    mask = (voltage > max(0.15, config.fitting.pos_voltage_threshold)) & (current > noise)
    if int(np.sum(mask)) < 3:
        mask = (voltage > 0.05) & (current > noise)
    x, y = _collapse_duplicate_voltage(voltage[mask], current[mask])
    if x.size < 3:
        return 1e3

    smooth_current = _smooth(y, window=5)
    didv = np.gradient(smooth_current, x)
    dynamic_r = 1.0 / np.maximum(didv, np.finfo(float).eps)
    dynamic_r = dynamic_r[np.isfinite(dynamic_r) & (dynamic_r > 0.0)]
    if dynamic_r.size == 0:
        return 1e3

    tail = dynamic_r[-max(3, dynamic_r.size // 3) :]
    return float(np.clip(np.median(tail), PARAM_LB[1], PARAM_UB[1]))


def _estimate_rsh_from_didv(voltage: np.ndarray, current: np.ndarray, config) -> float:
    neg_window = max(0.05, abs(float(config.fitting.neg_voltage_threshold)))
    mask = (voltage < -neg_window) & (voltage > -0.35)
    if int(np.sum(mask)) < 3:
        mask = voltage < -0.05
    x, y = _collapse_duplicate_voltage(voltage[mask], current[mask])
    if x.size < 3:
        return 1e7

    smooth_current = _smooth(y, window=5)
    slope = np.gradient(smooth_current, x)
    slope = slope[np.isfinite(slope) & (slope > 0.0)]
    if slope.size == 0:
        return 1e7

    slope_est = max(float(np.quantile(slope, 0.25)), np.finfo(float).eps)
    return float(np.clip(1.0 / slope_est, PARAM_LB[2], PARAM_UB[2]))


def _estimate_k_from_reverse_branch(voltage: np.ndarray, current: np.ndarray, rsh: float, config) -> float:
    mask = voltage < -max(0.15, abs(float(config.fitting.neg_voltage_threshold)))
    if int(np.sum(mask)) < 3:
        mask = voltage < -0.05
    if int(np.sum(mask)) < 2:
        return 5e-7

    reverse_v = voltage[mask]
    reverse_j = current[mask]
    residual = np.abs(reverse_j - reverse_v / max(rsh, PARAM_LB[2]))
    denom = np.maximum(np.abs(reverse_v) ** max(float(config.physics.m), 1.0), np.finfo(float).eps)
    k_values = residual / denom
    k_values = k_values[np.isfinite(k_values) & (k_values > 0.0)]
    if k_values.size == 0:
        return 5e-7
    return float(np.clip(np.median(k_values), PARAM_LB[3], PARAM_UB[3]))


def _estimate_j0_from_forward_branch(
    voltage: np.ndarray,
    current: np.ndarray,
    rs: float,
    rsh: float,
    k: float,
    config,
) -> float:
    noise = float(config.fitting.current_noise_floor)
    mask = (voltage > max(0.05, config.fitting.pos_voltage_threshold)) & (voltage < 0.35) & (current > noise)
    if int(np.sum(mask)) < 3:
        mask = (voltage > 0.02) & (current > noise)
    if int(np.sum(mask)) < 2:
        return 1e-9

    j0_values: list[float] = []
    for v_value, j_value in zip(voltage[mask], current[mask], strict=False):
        v_drop = float(v_value - j_value * rs)
        leakage = v_drop / max(rsh, PARAM_LB[2]) + k * abs(v_drop) ** config.physics.m * math.copysign(1.0, v_drop)
        diode_current = float(j_value - leakage)
        if diode_current <= 0.0:
            continue
        exponent = config.physics.A * v_drop / config.physics.n
        denom = math.expm1(float(np.clip(exponent, -60.0, 60.0)))
        if denom <= 0.0:
            continue
        j0_est = diode_current / denom
        if math.isfinite(j0_est) and j0_est > 0.0:
            j0_values.append(j0_est)
    if not j0_values:
        return 1e-9
    return float(np.clip(np.median(j0_values), PARAM_LB[0], PARAM_UB[0]))


def _lambert_w_candidate(data_v: np.ndarray, data_jd: np.ndarray, config) -> dict:
    pos_idx = np.where(data_v > 0.2)[0]
    if pos_idx.size >= 2:
        max_idx = int(np.argmax(data_v))
        if max_idx > 0 and data_jd[max_idx] != data_jd[max_idx - 1]:
            rs_est = abs((data_v[max_idx] - data_v[max_idx - 1]) / (data_jd[max_idx] - data_jd[max_idx - 1]))
        else:
            rs_est = 1e3
    else:
        rs_est = 1e3

    neg_idx = np.where(data_v < -0.2)[0]
    if neg_idx.size >= 2:
        slope, _ = np.polyfit(data_v[neg_idx], data_jd[neg_idx], 1)
        rsh_est = abs(1.0 / slope) if slope != 0 else 1e7
    else:
        rsh_est = 1e7

    n = config.physics.n
    v_th = config.physics.v_th
    j0_values: list[float] = []
    mid_pos_idx = np.where((data_v > 0.1) & (data_v < 0.25))[0]
    for idx in mid_pos_idx:
        j0_values.append(_solve_j0_for_point(float(data_v[idx]), float(data_jd[idx]), rs_est, rsh_est, n, v_th))

    x0 = np.clip(np.array([float(np.median(j0_values)) if j0_values else 1e-9, rs_est, rsh_est, 5e-7], dtype=float), PARAM_LB, PARAM_UB)
    return {
        "name": "lambert_w",
        "x0": x0,
        "details": {
            "rs_dynamic_estimate": float(x0[1]),
            "rsh_reverse_slope_estimate": float(x0[2]),
            "j0_points_used": int(len(j0_values)),
        },
    }


def _didv_candidate(data_v: np.ndarray, data_jd: np.ndarray, config) -> dict:
    voltage, current = _collapse_duplicate_voltage(data_v, data_jd)
    rs_est = _estimate_rs_from_didv(voltage, current, config)
    rsh_est = _estimate_rsh_from_didv(voltage, current, config)
    k_est = _estimate_k_from_reverse_branch(voltage, current, rsh_est, config)
    j0_est = _estimate_j0_from_forward_branch(voltage, current, rs_est, rsh_est, k_est, config)
    x0 = np.clip(np.array([j0_est, rs_est, rsh_est, k_est], dtype=float), PARAM_LB, PARAM_UB)
    return {
        "name": "didv_assisted",
        "x0": x0,
        "details": {
            "rs_dynamic_estimate": float(rs_est),
            "rsh_low_reverse_didv": float(rsh_est),
            "k_reverse_residual_estimate": float(k_est),
            "j0_forward_corrected_estimate": float(j0_est),
        },
    }


def _select_candidate(candidates: list[dict], requested_method: str) -> dict:
    method = (requested_method or "hybrid").strip().lower()
    by_name = {candidate["name"]: candidate for candidate in candidates}
    if method in by_name:
        return by_name[method]
    finite_candidates = [candidate for candidate in candidates if np.isfinite(candidate["score"])]
    if not finite_candidates:
        return by_name.get("lambert_w", candidates[0])
    return min(finite_candidates, key=lambda item: item["score"])


def initialize_parameters(data_v: np.ndarray, data_jd: np.ndarray, config) -> dict[str, Any]:
    data_v = _as_vector(data_v)
    data_jd = _as_vector(data_jd)
    print("Estimating initial parameters with Lambert W and dI/dV heuristics...")

    candidates = [_lambert_w_candidate(data_v, data_jd, config), _didv_candidate(data_v, data_jd, config)]
    for candidate in candidates:
        candidate["score"] = _initial_score(data_v, data_jd, candidate["x0"], config)

    requested_method = getattr(config.optimization, "initialization_method", "hybrid")
    selected = _select_candidate(candidates, requested_method)
    x0 = np.clip(_as_vector(selected["x0"]), PARAM_LB, PARAM_UB)

    for candidate in candidates:
        score_label = "inf" if not np.isfinite(candidate["score"]) else f"{candidate['score']:.2f}"
        print(
            f"{candidate['name']} candidate: "
            f"score={score_label}, "
            f"J0={candidate['x0'][0]:.6e} A, "
            f"Rs={candidate['x0'][1]:.6e} Ohm, "
            f"Rsh={candidate['x0'][2]:.6e} Ohm, "
            f"k={candidate['x0'][3]:.6e}"
        )

    print(f"Selected initialization: {selected['name']} (requested: {requested_method})")
    print(f"J0 = {x0[0]:.6e} A")
    print(f"Rs = {x0[1]:.6e} Ohm")
    print(f"Rsh = {x0[2]:.6e} Ohm")
    print(f"k = {x0[3]:.6e}")

    return {
        "x0": x0,
        "lb": PARAM_LB.copy(),
        "ub": PARAM_UB.copy(),
        "scale_factors": PARAM_SCALE.copy(),
        "param_names": PARAM_NAMES,
        "initialization": {
            "requested_method": str(requested_method),
            "selected": selected["name"],
            "selected_score": float(selected["score"]) if np.isfinite(selected["score"]) else None,
            "candidates": [
                {
                    "name": candidate["name"],
                    "score": float(candidate["score"]) if np.isfinite(candidate["score"]) else None,
                    "x0": candidate["x0"].copy(),
                    "details": candidate.get("details", {}),
                }
                for candidate in candidates
            ],
        },
    }
