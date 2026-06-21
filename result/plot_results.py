from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from fit.model import Currents, error_statistics, relative_errors, valid_error_mask


COLORS = {
    "data": "#6BAED6",
    "total": "#FB6A4A",
    "ohmic": "#90BA48",
    "diode": "#136AEE",
    "nonohmic": "#DF42E3",
}


def plot_results(v: np.ndarray, measured: np.ndarray, fit_results: dict, currents: Currents, show: bool = False):
    fig_fit, ax = plt.subplots(figsize=(6, 6))
    ax.semilogy(v, np.abs(measured), "o", color=COLORS["data"], label="Measured", markersize=6)
    ax.semilogy(v, np.abs(currents.total), "o", color=COLORS["total"], label="Fitted total", markersize=6)
    ax.semilogy(v, np.abs(currents.diode), "--", color=COLORS["diode"], label="Diode", linewidth=1.5)
    ax.semilogy(v, np.abs(currents.ohmic), "--", color=COLORS["ohmic"], label="Ohmic", linewidth=1.5)
    ax.semilogy(v, np.abs(currents.nonohmic), "--", color=COLORS["nonohmic"], label="Non-ohmic", linewidth=1.5)
    ax.set_xlim(-0.5, 0.3)
    ax.set_ylim(1e-11, 1e-3)
    ax.set_box_aspect(1)
    ax.set_xlabel("Voltage (V)")
    ax.set_ylabel("Current density (A)")
    ax.set_title("Diode I-V fit and current components")
    ax.grid(True)
    ax.legend(loc="best")
    fig_fit.tight_layout()

    rel = relative_errors(currents.total, measured)
    valid = valid_error_mask(v, measured)
    if not np.any(valid):
        valid = np.isfinite(rel)
    stats = error_statistics(v, measured, currents.total)
    avg_rel = stats["mean"]
    max_rel = stats["max"]

    fig_err, (ax_err, ax_lin) = plt.subplots(2, 1, figsize=(6, 6))
    ax_err.bar(v[valid], rel[valid], color=COLORS["data"], edgecolor="none", width=0.006)
    ax_err.set_xlabel("Voltage (V)")
    ax_err.set_ylabel("Relative error (%)")
    ax_err.set_title("Relative error")
    ax_err.set_xlim(-0.5, 0.3)
    ax_err.grid(True)

    ax_lin.plot(v, measured, color=COLORS["data"], linewidth=1.5, label="Measured")
    ax_lin.plot(v, fit_results["JD"], color=COLORS["total"], linewidth=1.5, label="Fitted")
    ax_lin.set_xlabel("Voltage (V)")
    ax_lin.set_ylabel("Current density (A)")
    ax_lin.set_title("I-V curve (linear scale)")
    ax_lin.grid(True)
    ax_lin.legend(loc="best")
    fig_err.suptitle(f"Fit analysis: max error {max_rel:.2f}%, mean error {avg_rel:.2f}%")
    fig_err.tight_layout()

    nz_total = currents.total != 0.0
    if np.any(nz_total):
        diode_ratio = np.mean(np.abs(currents.diode[nz_total] / currents.total[nz_total])) * 100.0
        ohmic_ratio = np.mean(np.abs(currents.ohmic[nz_total] / currents.total[nz_total])) * 100.0
        nonohm_ratio = np.mean(np.abs(currents.nonohmic[nz_total] / currents.total[nz_total])) * 100.0
        print(f"Diode current ratio: {diode_ratio:.2f}%")
        print(f"Ohmic current ratio: {ohmic_ratio:.2f}%")
        print(f"Non-ohmic current ratio: {nonohm_ratio:.2f}%")

    if show:
        plt.show()
    return fig_fit, fig_err


def save_figures(figures, output_dir: str | Path, timestamp: str) -> list[Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    names = ["fit_plot", "fit_error"]
    paths: list[Path] = []
    for fig, name in zip(figures, names):
        path = output / f"{name}_{timestamp}.png"
        fig.savefig(path, dpi=200)
        paths.append(path)
    return paths
