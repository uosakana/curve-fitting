from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


EPSILON_0_F_PER_M = 8.8541878128e-12


@dataclass
class CapacitanceVoltageSummary:
    path: Path
    point_count: int
    voltage_min_v: float
    voltage_max_v: float
    raw_capacitance_range_f: tuple[float, float]
    smooth_capacitance_range_f: tuple[float, float] | None
    reverse_mid_median_f: float
    near_zero_median_f: float
    forward_mid_median_f: float
    estimated_epsilon_r_reverse_mid: float | None
    capacitance_quality: str
    epsilon_status: str
    field_width_status: str
    notes: list[str]

    def as_metadata(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "frequency_Hz": 1000.0,
            "voltage_column": 1,
            "raw_capacitance_column": 2,
            "smooth_capacitance_column": 3 if self.smooth_capacitance_range_f is not None else None,
            "smooth_method": "30-point Savitzky-Golay" if self.smooth_capacitance_range_f is not None else None,
            "capacitance_unit": "F",
            "point_count": self.point_count,
            "voltage_range_V": [self.voltage_min_v, self.voltage_max_v],
            "raw_capacitance_range_F": list(self.raw_capacitance_range_f),
            "smooth_capacitance_range_F": (
                None if self.smooth_capacitance_range_f is None else list(self.smooth_capacitance_range_f)
            ),
            "reverse_mid_median_F": self.reverse_mid_median_f,
            "near_zero_median_F": self.near_zero_median_f,
            "forward_mid_median_F": self.forward_mid_median_f,
            "estimated_epsilon_r_reverse_mid": self.estimated_epsilon_r_reverse_mid,
            "capacitance_quality": self.capacitance_quality,
            "epsilon_from_cv": self.epsilon_status,
            "field_width_from_cv": self.field_width_status,
            "usable_for_gate": ["cv_available", "diagnostic_shape_only"],
            "notes": list(self.notes),
        }


def _as_float(value: float) -> float:
    return float(np.asarray(value, dtype=float))


def _median_in_window(voltage: np.ndarray, values: np.ndarray, low: float, high: float) -> float:
    mask = (voltage >= low) & (voltage <= high) & np.isfinite(values)
    if not np.any(mask):
        return float("nan")
    return float(np.median(values[mask]))


def _epsilon_r(capacitance_f: float, thickness_nm: float | None, area_cm2: float | None) -> float | None:
    if thickness_nm is None or area_cm2 is None:
        return None
    if thickness_nm <= 0.0 or area_cm2 <= 0.0 or capacitance_f <= 0.0:
        return None
    thickness_m = float(thickness_nm) * 1e-9
    area_m2 = float(area_cm2) * 1e-4
    return float(capacitance_f * thickness_m / (EPSILON_0_F_PER_M * area_m2))


def summarize_cv_file(
    path: str | Path,
    *,
    thickness_nm: float | None = 300.0,
    area_cm2: float | None = 0.045,
) -> CapacitanceVoltageSummary:
    cv_path = Path(path)
    data = np.loadtxt(cv_path)
    if data.ndim != 2 or data.shape[1] < 2:
        raise ValueError("C-V file must contain at least voltage and capacitance columns.")

    voltage = np.asarray(data[:, 0], dtype=float)
    raw_capacitance = np.asarray(data[:, 1], dtype=float)
    smooth_capacitance = np.asarray(data[:, 2], dtype=float) if data.shape[1] >= 3 else None
    selected = smooth_capacitance if smooth_capacitance is not None else raw_capacitance

    reverse_mid = _median_in_window(voltage, selected, -0.4, -0.1)
    near_zero = _median_in_window(voltage, selected, -0.05, 0.05)
    forward_mid = _median_in_window(voltage, selected, 0.1, 0.3)
    epsilon_estimate = _epsilon_r(reverse_mid, thickness_nm, area_cm2)

    notes: list[str] = [
        "Column 2 is treated as raw capacitance in F.",
        "Column 3 is treated as 30-point Savitzky-Golay smoothed capacitance in F.",
    ]
    capacitance_quality = "diagnostic_shape_only"
    epsilon_status = "rejected_for_now"
    field_width_status = "rejected_for_now"
    if epsilon_estimate is None:
        notes.append("Missing thickness or area prevents an epsilon_r consistency check.")
    elif epsilon_estimate < 1.0 or epsilon_estimate > 100.0:
        notes.append(
            "Geometric epsilon_r inferred from the F-scale capacitance is outside a practical range; "
            "do not use this C-V file as a hard permittivity or field-width prior."
        )
    else:
        capacitance_quality = "geometric_capacitance_plausible"
        epsilon_status = "candidate"
        field_width_status = "candidate"
        notes.append("Geometric epsilon_r is in a plausible range; still check LCR loss mode before hard gating.")

    return CapacitanceVoltageSummary(
        path=cv_path,
        point_count=int(voltage.size),
        voltage_min_v=_as_float(np.min(voltage)),
        voltage_max_v=_as_float(np.max(voltage)),
        raw_capacitance_range_f=(_as_float(np.min(raw_capacitance)), _as_float(np.max(raw_capacitance))),
        smooth_capacitance_range_f=None
        if smooth_capacitance is None
        else (_as_float(np.min(smooth_capacitance)), _as_float(np.max(smooth_capacitance))),
        reverse_mid_median_f=float(reverse_mid),
        near_zero_median_f=float(near_zero),
        forward_mid_median_f=float(forward_mid),
        estimated_epsilon_r_reverse_mid=epsilon_estimate,
        capacitance_quality=capacitance_quality,
        epsilon_status=epsilon_status,
        field_width_status=field_width_status,
        notes=notes,
    )
