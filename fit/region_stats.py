from __future__ import annotations

from typing import Any

import numpy as np

from fit.model import relative_errors, valid_error_mask


DEFAULT_NEAR_ZERO_WIDTH = 0.05
DEFAULT_HIGH_FORWARD_THRESHOLD = 0.3


def _as_vector(values: Any) -> np.ndarray:
    return np.asarray(values, dtype=float).reshape(-1)


def region_masks(
    voltage: np.ndarray,
    *,
    near_zero_width: float = DEFAULT_NEAR_ZERO_WIDTH,
    high_forward_threshold: float = DEFAULT_HIGH_FORWARD_THRESHOLD,
) -> dict[str, np.ndarray]:
    v = _as_vector(voltage)
    zero = abs(float(near_zero_width))
    high = float(high_forward_threshold)
    return {
        "reverse": v < -zero,
        "near_zero": np.abs(v) <= zero,
        "forward": (v > zero) & (v <= high),
        "high_forward": v > high,
    }


def region_error_stats(
    voltage: np.ndarray,
    measured: np.ndarray,
    predicted: np.ndarray,
    config: Any,
    *,
    near_zero_width: float = DEFAULT_NEAR_ZERO_WIDTH,
    high_forward_threshold: float = DEFAULT_HIGH_FORWARD_THRESHOLD,
) -> dict[str, dict[str, float | None] | str | None]:
    v = _as_vector(voltage)
    current = _as_vector(measured)
    rel = relative_errors(predicted, current)
    valid = valid_error_mask(
        v,
        current,
        voltage_zero_atol=config.fitting.voltage_zero_atol,
        current_noise_floor=config.fitting.current_noise_floor,
    )
    masks = region_masks(
        v,
        near_zero_width=near_zero_width,
        high_forward_threshold=high_forward_threshold,
    )
    stats: dict[str, dict[str, float | None] | str | None] = {}
    worst_region: str | None = None
    worst_mean = -np.inf
    for name, mask in masks.items():
        selected = mask & valid & np.isfinite(rel)
        if not np.any(selected):
            stats[name] = {"mean": None, "max": None, "count": 0.0}
            continue
        mean = float(np.mean(rel[selected]))
        max_value = float(np.max(rel[selected]))
        stats[name] = {"mean": mean, "max": max_value, "count": float(np.sum(selected))}
        if mean > worst_mean:
            worst_mean = mean
            worst_region = name
    stats["worst_region"] = worst_region
    return stats
