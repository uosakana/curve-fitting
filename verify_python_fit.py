from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

from config import load_config
from fit.initialize_parameters import initialize_parameters
from fit.model import error_statistics
from fit.optimization import perform_fitting


ROOT = Path(__file__).resolve().parent


def _load_data_module():
    path = ROOT / "io" / "load_data.py"
    spec = importlib.util.spec_from_file_location("iv_load_data", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    config = load_config()
    data_module = _load_data_module()
    data_v, data_jd = data_module.sample_data()
    data_module.validate_input_data(data_v, data_jd)

    params_meta = initialize_parameters(data_v, data_jd, config)
    optimized_params, fit_results = perform_fitting(data_v, data_jd, params_meta, config)
    stats = error_statistics(data_v, data_jd, fit_results["JD"])

    print("\nVerification result with built-in sample data:")
    print(f"J0  = {optimized_params[0]:.6e} A")
    print(f"Rs  = {optimized_params[1]:.6e} Ohm")
    print(f"Rsh = {optimized_params[2]:.6e} Ohm")
    print(f"k   = {optimized_params[3]:.6e}")
    print(f"Mean relative error = {stats['mean']:.2f}%")
    print(f"Max relative error = {stats['max']:.2f}%")
    if not np.all(np.isfinite(fit_results["JD"])):
        raise RuntimeError("Non-finite fitted currents.")


if __name__ == "__main__":
    main()
