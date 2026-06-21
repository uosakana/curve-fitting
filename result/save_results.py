from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from fit.model import Currents, error_statistics, relative_errors
from result.plot_results import save_figures


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def save_results(
    data_v: np.ndarray,
    data_jd: np.ndarray,
    params: np.ndarray,
    fit_results: dict,
    currents: Currents,
    figures=None,
    output_dir: str | Path = "outputs",
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    timestamp = _timestamp()
    paths: dict[str, Path] = {}

    rel = relative_errors(fit_results["JD"], data_jd)

    npz_path = output / f"fit_results_{timestamp}.npz"
    np.savez(
        npz_path,
        data_V=data_v,
        data_JD=data_jd,
        params=params,
        fit_JD=fit_results["JD"],
        diode_current=currents.diode,
        ohmic_current=currents.ohmic,
        nonohmic_current=currents.nonohmic,
        relative_error=rel,
        resnorm=fit_results.get("resnorm", np.nan),
    )
    paths["npz"] = npz_path

    csv_path = output / f"fit_data_{timestamp}.csv"
    frame = pd.DataFrame(
        {
            "Voltage(V)": data_v,
            "Measured_Current(A)": data_jd,
            "Fitted_Current(A)": fit_results["JD"],
            "Diode_Current(A)": currents.diode,
            "Ohmic_Current(A)": currents.ohmic,
            "Nonohmic_Current(A)": currents.nonohmic,
            "Relative_Error(%)": rel,
        }
    )
    frame.to_csv(csv_path, index=False)
    paths["csv"] = csv_path

    txt_path = output / f"fit_params_{timestamp}.txt"
    stats = error_statistics(data_v, data_jd, fit_results["JD"])
    with txt_path.open("w", encoding="utf-8") as handle:
        handle.write("Fitted parameters:\n")
        handle.write(f"J0 = {params[0]:.6e} A\n")
        handle.write(f"Rs = {params[1]:.6e} Ohm\n")
        handle.write(f"Rsh = {params[2]:.6e} Ohm\n")
        handle.write(f"k = {params[3]:.6e}\n\n")
        handle.write("Fit error statistics:\n")
        handle.write(f"Mean relative error: {stats['mean']:.2f}%\n")
        handle.write(f"Max relative error: {stats['max']:.2f}%\n")
        handle.write(f"Median relative error: {stats['median']:.2f}%\n")
        handle.write(f"Effective points: {int(stats['included_points'])}\n")
        handle.write(f"Excluded near-zero/noise-floor points: {int(stats['excluded_points'])}\n")
        if "negative_mean" in stats:
            handle.write(f"Negative-voltage mean relative error: {stats['negative_mean']:.2f}%\n")
        if "positive_mean" in stats:
            handle.write(f"Positive-voltage mean relative error: {stats['positive_mean']:.2f}%\n")
    paths["txt"] = txt_path

    if figures is not None:
        figure_paths = save_figures(figures, output, timestamp)
        for idx, path in enumerate(figure_paths):
            paths[f"figure_{idx + 1}"] = path

    print(f"Saved fit results to: {npz_path}")
    print(f"Saved fit data to: {csv_path}")
    print(f"Saved fit parameters to: {txt_path}")
    return paths


def save_adjusted_parameters(params: np.ndarray, output_dir: str | Path = "outputs") -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    timestamp = _timestamp()
    npz_path = output / f"adjusted_params_{timestamp}.npz"
    txt_path = output / f"adjusted_params_{timestamp}.txt"
    np.savez(npz_path, params=params)
    with txt_path.open("w", encoding="utf-8") as handle:
        handle.write(f"J0 = {params[0]:.6e} A\n")
        handle.write(f"Rs = {params[1]:.6e} Ohm\n")
        handle.write(f"Rsh = {params[2]:.6e} Ohm\n")
        handle.write(f"k = {params[3]:.6e}\n")
    print(f"Saved adjusted parameters to: {npz_path}")
    print(f"Exported adjusted parameters to: {txt_path}")
    return {"npz": npz_path, "txt": txt_path}
