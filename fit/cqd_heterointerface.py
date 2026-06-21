from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import numpy as np
from scipy.optimize import brentq


Q = 1.602176634e-19
KB = 1.380649e-23
HBAR = 1.054571817e-34
M0 = 9.1093837015e-31


@dataclass(frozen=True)
class CQDHeterointerfaceConstants:
    temperature_k: float = 300.0
    electron_effective_mass_rel: float = 0.17
    qd_center_distance_nm: float = 4.0


@dataclass(frozen=True)
class CQDDerivedValues:
    equilibrium_field_v_cm: float
    tunneling_b_v_cm: float
    richardson_velocity_cm_s: float
    zero_bias_drift_velocity_cm_s: float
    diffusion_cm2_s: float
    band_bending_width_nm: float
    beta_cm_inv: float


def _as_vector(values: Any) -> np.ndarray:
    return np.asarray(values, dtype=float).reshape(-1)


def _safe_exp(values: np.ndarray | float) -> np.ndarray | float:
    return np.exp(np.clip(values, -700.0, 700.0))


def richardson_velocity_cm_s(constants: CQDHeterointerfaceConstants) -> float:
    mass = constants.electron_effective_mass_rel * M0
    velocity_m_s = np.sqrt(KB * constants.temperature_k / (2.0 * np.pi * mass))
    return float(velocity_m_s * 100.0)


def tunneling_b_v_cm(phi_v: float, constants: CQDHeterointerfaceConstants) -> float:
    """Fowler-Nordheim-like B from Arya SI Eq. S7/S9, returned in V/cm."""
    mass = constants.electron_effective_mass_rel * M0
    b_v_m = 4.0 * np.sqrt(2.0 * Q * mass) * float(phi_v) ** 1.5 / (3.0 * HBAR)
    return float(b_v_m / 100.0)


def equilibrium_field_v_cm(phi_v: float, constants: CQDHeterointerfaceConstants) -> float:
    """Solve Arya SI Eq. S10 and return the lower physical root in V/cm."""
    phi_v = float(phi_v)
    if phi_v <= 0.0:
        raise ValueError("phi_v must be positive.")

    mass = constants.electron_effective_mass_rel * M0
    d_m = constants.qd_center_distance_nm * 1e-9
    thermal = KB * constants.temperature_k

    def residual(field_v_m: float) -> float:
        return (
            Q * phi_v / thermal
            - 4.0 * np.sqrt(2.0 * Q * mass) * phi_v**1.5 / (3.0 * HBAR * field_v_m)
            - np.log(Q * field_v_m * d_m / thermal)
        )

    grid = np.logspace(4.0, 10.0, 300)
    previous_field = float(grid[0])
    previous_value = residual(previous_field)
    for field in grid[1:]:
        field = float(field)
        value = residual(field)
        if np.isfinite(previous_value) and np.isfinite(value) and previous_value * value <= 0.0:
            root = brentq(residual, previous_field, field, xtol=1e-7, rtol=1e-12, maxiter=100)
            return float(root / 100.0)
        previous_field = field
        previous_value = value
    raise RuntimeError(f"Could not solve equilibrium field for phi={phi_v:.6g} V.")


@lru_cache(maxsize=4096)
def _derived_values_cached(
    phi_v: float,
    vbi_v: float,
    temperature_k: float,
    electron_effective_mass_rel: float,
    qd_center_distance_nm: float,
) -> CQDDerivedValues:
    constants = CQDHeterointerfaceConstants(
        temperature_k=temperature_k,
        electron_effective_mass_rel=electron_effective_mass_rel,
        qd_center_distance_nm=qd_center_distance_nm,
    )
    field = equilibrium_field_v_cm(phi_v, constants)
    b_value = tunneling_b_v_cm(phi_v, constants)
    v_r = richardson_velocity_cm_s(constants)
    v_d0 = v_r * float(_safe_exp(-b_value / field))
    d_cm = constants.qd_center_distance_nm * 1e-7
    diffusion = v_r * d_cm * float(_safe_exp(-Q * float(phi_v) / (KB * constants.temperature_k)))
    beta = Q * field / (KB * constants.temperature_k)
    width_nm = float(vbi_v) / (field * 100.0) * 1e9
    return CQDDerivedValues(
        equilibrium_field_v_cm=float(field),
        tunneling_b_v_cm=float(b_value),
        richardson_velocity_cm_s=float(v_r),
        zero_bias_drift_velocity_cm_s=float(v_d0),
        diffusion_cm2_s=float(diffusion),
        band_bending_width_nm=float(width_nm),
        beta_cm_inv=float(beta),
    )


def derived_values(
    phi_v: float,
    vbi_v: float,
    constants: CQDHeterointerfaceConstants | None = None,
) -> CQDDerivedValues:
    constants = constants or CQDHeterointerfaceConstants()
    return _derived_values_cached(
        float(phi_v),
        float(vbi_v),
        float(constants.temperature_k),
        float(constants.electron_effective_mass_rel),
        float(constants.qd_center_distance_nm),
    )


def cqd_dark_current_density_internal(
    internal_voltage_v: np.ndarray,
    params: np.ndarray,
    constants: CQDHeterointerfaceConstants | None = None,
) -> np.ndarray:
    """Dark current density from Arya SI Eq. S20.

    params = [phi_v, vbi_v, tau_s, n0_cm3, rs_area_ohm_cm2]
    The series-resistance parameter is not used in this internal branch.
    """
    constants = constants or CQDHeterointerfaceConstants()
    voltage = _as_vector(internal_voltage_v)
    phi_v, vbi_v, tau_s, n0_cm3, _ = _as_vector(params)
    if phi_v <= 0.0 or vbi_v <= 0.0 or tau_s <= 0.0 or n0_cm3 <= 0.0:
        raise ValueError("CQD heterointerface parameters must be positive.")

    derived = derived_values(phi_v, vbi_v, constants)
    field_eq = derived.equilibrium_field_v_cm
    b_value = derived.tunneling_b_v_cm
    beta = derived.beta_cm_inv
    diffusion = max(derived.diffusion_cm2_s, np.finfo(float).tiny)

    # E = (Vbi - V) / W and W = Vbi / Eeq, using V/cm.
    field = field_eq * (1.0 - voltage / vbi_v)
    field = np.maximum(field, max(1.0, field_eq * 1e-6))
    drift = derived.richardson_velocity_cm_s * _safe_exp(-b_value / field)
    gamma = drift / (2.0 * diffusion) + np.sqrt((drift / (2.0 * diffusion)) ** 2 + 1.0 / (tau_s * diffusion))

    beta_d_minus_v = beta * diffusion - drift
    numerator = Q * n0_cm3 * beta_d_minus_v * (1.0 / tau_s - beta * (gamma * diffusion - drift))
    denominator = 1.0 / tau_s - beta * beta_d_minus_v
    current = numerator / np.where(np.abs(denominator) > 1e-300, denominator, np.sign(denominator) * 1e-300)
    return np.nan_to_num(current, nan=1e300, posinf=1e300, neginf=-1e300)


def cqd_dark_current_density_simplified(
    internal_voltage_v: np.ndarray,
    params: np.ndarray,
    constants: CQDHeterointerfaceConstants | None = None,
) -> np.ndarray:
    """Shockley-like Arya SI Eq. S25, useful for diagnostics and sanity checks."""
    constants = constants or CQDHeterointerfaceConstants()
    voltage = _as_vector(internal_voltage_v)
    phi_v, vbi_v, tau_s, n0_cm3, _ = _as_vector(params)
    derived = derived_values(phi_v, vbi_v, constants)
    j0 = n0_cm3 * KB * constants.temperature_k / (tau_s * derived.equilibrium_field_v_cm)
    exponent = 2.0 * derived.tunneling_b_v_cm * voltage / (derived.equilibrium_field_v_cm * vbi_v)
    return j0 * (_safe_exp(exponent) - 1.0)


def _scalar_internal_voltage_root(
    voltage_v: float,
    params: np.ndarray,
    constants: CQDHeterointerfaceConstants,
    *,
    simplified: bool,
) -> float:
    rs_area = float(_as_vector(params)[4])
    vbi_v = float(_as_vector(params)[1])
    if rs_area <= 0.0:
        raise ValueError("Rs_area must be positive.")

    branch = cqd_dark_current_density_simplified if simplified else cqd_dark_current_density_internal

    def residual(internal_v: float) -> float:
        current = float(branch(np.array([internal_v]), params, constants)[0])
        return current - (voltage_v - internal_v) / rs_area

    lo = min(float(voltage_v) - 2.0, -2.0)
    hi = min(max(float(voltage_v) + 2.0, 0.2), vbi_v * 0.995)
    f_lo = residual(lo)
    f_hi = residual(hi)
    for _ in range(80):
        if np.isfinite(f_lo) and np.isfinite(f_hi) and f_lo <= 0.0 <= f_hi:
            return float(brentq(residual, lo, hi, xtol=1e-12, rtol=1e-12, maxiter=100))
        lo -= 2.0
        hi = min(hi + 0.2, vbi_v * 0.999)
        f_lo = residual(lo)
        f_hi = residual(hi)
    raise RuntimeError(f"Could not bracket CQD heterointerface root at V={voltage_v:.6g}.")


def cqd_heterointerface_model(
    voltage_v: np.ndarray,
    params: np.ndarray,
    constants: CQDHeterointerfaceConstants | None = None,
    *,
    simplified: bool = False,
) -> np.ndarray:
    constants = constants or CQDHeterointerfaceConstants()
    voltage = _as_vector(voltage_v)
    params = _as_vector(params)
    branch = cqd_dark_current_density_simplified if simplified else cqd_dark_current_density_internal
    rs_area = float(params[4])
    if rs_area <= 0.0:
        raise ValueError("Rs_area must be positive.")

    if rs_area < 1e-12:
        return branch(voltage, params, constants)
    internal = np.array(
        [
            _scalar_internal_voltage_root(float(value), params, constants, simplified=simplified)
            for value in voltage
        ],
        dtype=float,
    )
    return branch(internal, params, constants)
