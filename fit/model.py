from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import brentq


EPS = np.finfo(float).eps


@dataclass
class Currents:
    total: np.ndarray
    diode: np.ndarray
    ohmic: np.ndarray
    nonohmic: np.ndarray
    summed: np.ndarray


def _as_vector(values: Any) -> np.ndarray:
    return np.asarray(values, dtype=float).reshape(-1)


def _params_from_optimizer(x: np.ndarray, params_meta: dict[str, Any]) -> np.ndarray:
    if params_meta.get("space") == "log10":
        return np.power(10.0, _as_vector(x))
    return _as_vector(x) * params_meta["scale_factors"]


def _safe_exp(x: np.ndarray | float) -> np.ndarray | float:
    return np.exp(np.clip(x, -700.0, 700.0))


def _branch_current(v_drop: np.ndarray, params: np.ndarray, config: Any) -> np.ndarray:
    j0, _, rsh, k = params
    physics = config.physics
    diode = j0 * (_safe_exp(physics.A * v_drop / physics.n) - 1.0)
    ohmic = v_drop / rsh
    nonohmic = k * np.abs(v_drop) ** physics.m * np.sign(v_drop)
    return diode + ohmic + nonohmic


def _branch_derivative(v_drop: np.ndarray, params: np.ndarray, config: Any) -> np.ndarray:
    j0, _, rsh, k = params
    physics = config.physics
    exp_term = _safe_exp(physics.A * v_drop / physics.n)
    nonohmic_deriv = k * physics.m * np.abs(v_drop) ** (physics.m - 1.0)
    return j0 * (physics.A / physics.n) * exp_term + 1.0 / rsh + nonohmic_deriv


def _scalar_vdrop_root(v: float, params: np.ndarray, config: Any) -> float:
    rs = params[1]

    def residual(u: float) -> float:
        return float(_branch_current(np.array([u]), params, config)[0] - (v - u) / rs)

    width = max(1.0, abs(v))
    lo = -width
    hi = width
    f_lo = residual(lo)
    f_hi = residual(hi)
    for _ in range(80):
        if np.isfinite(f_lo) and np.isfinite(f_hi) and f_lo <= 0.0 <= f_hi:
            return brentq(residual, lo, hi, xtol=1e-13, rtol=1e-13, maxiter=100)
        width *= 2.0
        lo = -width
        hi = width
        f_lo = residual(lo)
        f_hi = residual(hi)
    raise RuntimeError(f"Could not bracket diode-model root at V={v:.6g}")


def solve_v_drop(v: np.ndarray, params: np.ndarray, config: Any) -> np.ndarray:
    """Solve V_drop = V - J*Rs for each voltage point.

    The MATLAB code solves the implicit current equation with fsolve. Here the
    same equation is rewritten as a monotone scalar root in V_drop and solved
    with vector Newton iterations plus a brentq fallback for robustness.
    """
    voltage = _as_vector(v)
    params = _as_vector(params)
    rs = params[1]
    if rs <= 0:
        raise ValueError(f"Physical parameter error: Rs must be positive, got {rs:.6e}")

    u = voltage.copy()
    converged = np.zeros_like(u, dtype=bool)
    for _ in range(60):
        f = _branch_current(u, params, config) - (voltage - u) / rs
        df = _branch_derivative(u, params, config) + 1.0 / rs
        step = f / np.maximum(df, 1e-300)
        step = np.clip(step, -1.0, 1.0)
        next_u = u - step
        good = np.isfinite(next_u) & (np.abs(step) <= 1e-12 * (1.0 + np.abs(next_u)))
        converged |= good
        u = np.where(np.isfinite(next_u), next_u, u)
        if bool(np.all(converged)):
            break

    residual = _branch_current(u, params, config) - (voltage - u) / rs
    ok = np.isfinite(residual) & (np.abs(residual) <= 1e-10 * (1.0 + np.abs(voltage / rs)))
    if not bool(np.all(ok)):
        for idx in np.where(~ok)[0]:
            u[idx] = _scalar_vdrop_root(float(voltage[idx]), params, config)
    return u


def diode_model(v: np.ndarray, params: np.ndarray, config: Any) -> np.ndarray:
    voltage = _as_vector(v)
    params = _as_vector(params)
    v_drop = solve_v_drop(voltage, params, config)
    return (voltage - v_drop) / params[1]


def calculate_currents(v: np.ndarray, params: np.ndarray, config: Any) -> Currents:
    voltage = _as_vector(v)
    params = _as_vector(params)
    total = diode_model(voltage, params, config)
    v_drop = voltage - total * params[1]
    diode = params[0] * (_safe_exp(config.physics.A * v_drop / config.physics.n) - 1.0)
    ohmic = v_drop / params[2]
    nonohmic = params[3] * np.abs(v_drop) ** config.physics.m * np.sign(v_drop)
    return Currents(total=total, diode=diode, ohmic=ohmic, nonohmic=nonohmic, summed=diode + ohmic + nonohmic)


def relative_errors(predicted: np.ndarray, measured: np.ndarray) -> np.ndarray:
    predicted = _as_vector(predicted)
    measured = _as_vector(measured)
    return np.abs((predicted - measured) / (np.abs(measured) + EPS)) * 100.0


def valid_error_mask(
    v: np.ndarray,
    measured: np.ndarray,
    *,
    voltage_zero_atol: float = 1e-12,
    current_noise_floor: float = 1e-11,
) -> np.ndarray:
    voltage = _as_vector(v)
    measured = _as_vector(measured)
    finite = np.isfinite(voltage) & np.isfinite(measured)
    away_from_zero_v = np.abs(voltage) > voltage_zero_atol
    above_noise = np.abs(measured) >= current_noise_floor
    return finite & away_from_zero_v & above_noise


def error_function(
    x: np.ndarray,
    data_v: np.ndarray,
    data_jd: np.ndarray,
    params_meta: dict[str, np.ndarray],
    config: Any,
    prior: np.ndarray | None = None,
    param_mask: np.ndarray | None = None,
    x0: np.ndarray | None = None,
    prev_errors: np.ndarray | None = None,
    sign_weight: float | None = None,
    point_weights: np.ndarray | None = None,
) -> np.ndarray:
    data_v = _as_vector(data_v)
    data_jd = _as_vector(data_jd)
    x = _as_vector(x)

    if prior is None:
        prior = config.regularization.prior
    if param_mask is not None:
        x_full = _as_vector(x0).copy()
        mask = np.asarray(param_mask, dtype=bool)
        x_full[mask] = x
        if sign_weight is None:
            sign_weight = 4.0
    else:
        x_full = x
        mask = None
        if sign_weight is None:
            sign_weight = 3.0

    x_actual = _params_from_optimizer(x_full, params_meta)
    predicted = diode_model(data_v, x_actual, config)

    threshold = getattr(config.fitting, "current_noise_floor", 1e-12)
    max_val = max(1e-12, float(np.max(np.abs(data_jd))))
    actual_abs = np.abs(data_jd)
    pred_abs = np.abs(predicted)
    err = np.zeros_like(data_jd)

    mask_small = (actual_abs < threshold) | (pred_abs < threshold)
    err[mask_small] = (predicted[mask_small] - data_jd[mask_small]) / max_val

    mask_log = ~mask_small
    err[mask_log] = np.log10(pred_abs[mask_log]) - np.log10(actual_abs[mask_log])

    if mask is not None:
        sign_mismatch = np.sign(predicted) != np.sign(data_jd)
        err[sign_mismatch & mask_log] *= sign_weight
        idx = np.abs(data_v) > 0.05
        if prev_errors is not None:
            err[idx] *= 1.0 + np.abs(_as_vector(prev_errors)[idx])
        else:
            err[idx] *= 1.0 + np.abs(err[idx])
    else:
        sign_mismatch = (
            (np.sign(predicted) != np.sign(data_jd))
            & (pred_abs > threshold)
            & (actual_abs > threshold)
        )
        err[sign_mismatch] *= sign_weight
        idx = np.abs(data_v) > 0.05
        err[idx] *= 1.0 + np.abs(err[idx])

    if point_weights is not None:
        weights = np.clip(_as_vector(point_weights), 0.0, np.inf)
        if weights.size != err.size:
            raise ValueError("point_weights must have the same length as data_v/data_jd.")
        err = err * np.sqrt(weights)

    if config.regularization.lambda_ > 0.0:
        penalty = np.sqrt(config.regularization.lambda_) * (x_actual.reshape(-1) - _as_vector(prior))
        err = np.concatenate([err, penalty])
    return np.nan_to_num(err, nan=1e12, posinf=1e12, neginf=-1e12)


def error_statistics(
    v: np.ndarray,
    measured: np.ndarray,
    predicted: np.ndarray,
    *,
    voltage_zero_atol: float = 1e-12,
    current_noise_floor: float = 1e-11,
) -> dict[str, float]:
    voltage = _as_vector(v)
    measured = _as_vector(measured)
    rel = relative_errors(predicted, measured)
    valid = valid_error_mask(
        voltage,
        measured,
        voltage_zero_atol=voltage_zero_atol,
        current_noise_floor=current_noise_floor,
    )
    if not np.any(valid):
        valid = np.isfinite(rel)
    stats = {
        "mean": float(np.mean(rel[valid])),
        "max": float(np.max(rel[valid])),
        "median": float(np.median(rel[valid])),
        "raw_max": float(np.max(rel)),
        "included_points": float(np.sum(valid)),
        "excluded_points": float(rel.size - np.sum(valid)),
    }
    neg = (voltage < 0.0) & valid
    pos = (voltage > 0.0) & valid
    if np.any(neg):
        stats["negative_mean"] = float(np.mean(rel[neg]))
    if np.any(pos):
        stats["positive_mean"] = float(np.mean(rel[pos]))
    return stats
