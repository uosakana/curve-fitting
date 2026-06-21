from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy.io import loadmat

from config import load_config
from data_io import DataSelection, load_dataset, validate_input_data
from fit.model import error_statistics
from fit.parameter_schema import DEFAULT_M_VALUES, DEFAULT_N_VALUES, params_meta_from_values
from fit.workflow import AnalysisOptions, AnalysisResult, run_analysis
from result.plot_results import plot_results
from result.save_results import save_results


ROOT = Path(__file__).resolve().parent


def _load_demo_data() -> tuple[np.ndarray, np.ndarray]:
    """Load the legacy sample data without importing the stdlib io module by accident."""
    path = ROOT / "io" / "load_data.py"
    spec = importlib.util.spec_from_file_location("iv_load_data", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load demo data helper from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.sample_data()


def _params_from_history(path: Path) -> dict[str, np.ndarray]:
    suffix = path.suffix.lower()
    if suffix == ".npz":
        with np.load(path) as data:
            values = np.asarray(data["params"], dtype=float).reshape(-1)
    elif suffix == ".mat":
        data = loadmat(path)
        if "params" not in data:
            raise ValueError(f"MAT file does not contain 'params': {path}")
        values = np.asarray(data["params"], dtype=float).reshape(-1)
    elif suffix == ".txt":
        parsed: list[float] = []
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "=" in line:
                parsed.append(float(line.split("=", 1)[1].split()[0]))
        values = np.asarray(parsed, dtype=float)
    else:
        raise ValueError(f"Unsupported history file type: {path.suffix}")
    return params_meta_from_values(values)


def _load_cli_data(args: argparse.Namespace) -> tuple[np.ndarray, np.ndarray]:
    if args.demo_data:
        return _load_demo_data()

    dataset = load_dataset(
        DataSelection(
            path=args.data,
            sheet_name=args.sheet_name,
            cell_range=args.cell_range,
            voltage_range=args.voltage_range,
            current_range=args.current_range,
            voltage_start=args.voltage_start,
            voltage_end=args.voltage_end,
            voltage_step=args.voltage_step,
        )
    )
    print(f"Loaded {dataset.source['points']} data points from {dataset.source['path']}.")
    print(f"Data load mode: {dataset.source['mode']}.")
    return dataset.data_v, dataset.data_jd


def _initial_params(args: argparse.Namespace) -> dict[str, np.ndarray] | None:
    if args.params is not None and args.history is not None:
        raise ValueError("Use either --params or --history, not both.")
    if args.params is not None:
        return params_meta_from_values(np.asarray(args.params, dtype=float))
    if args.history is not None:
        print(f"Loading initial parameters from: {args.history}")
        return _params_from_history(args.history)
    return None


def _print_m_scan(results) -> None:
    if not results:
        return

    print("\nM-exponent scan:")
    for rank, result in enumerate(results, start=1):
        print(
            f"{rank}. m={result.m:.3g}, "
            f"mean={result.stats['mean']:.2f}%, "
            f"max={result.stats['max']:.2f}%, "
            f"J0={result.params[0]:.3e}, "
            f"Rs={result.params[1]:.3e}, "
            f"Rsh={result.params[2]:.3e}, "
            f"k={result.params[3]:.3e}"
        )


def _print_model_comparison(results) -> None:
    if not results:
        return

    print("\nLeakage model comparison:")
    for rank, result in enumerate(results, start=1):
        print(
            f"{rank}. {result.spec.name}: "
            f"BIC={result.bic:.2f}, "
            f"AIC={result.aic:.2f}, "
            f"mean={result.stats['mean']:.2f}%, "
            f"max={result.stats['max']:.2f}%, "
            f"free_params={result.free_parameter_count}"
        )
    best = results[0]
    print(f"Best model by BIC: {best.spec.name} ({best.spec.description}).")


def _print_notes(analysis: AnalysisResult) -> None:
    if not analysis.notes:
        return

    print("\nMechanism notes:")
    for note in analysis.notes:
        print(f"- {note}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Batch CLI for JV/I-V fitting. Use desktop_app.py or "
            "python -m uvicorn app.fastapi_server:app for the interactive app."
        )
    )
    input_group = parser.add_argument_group("input")
    input_group.add_argument("--data", type=Path, help="xlsx/xls/csv file containing JV/I-V data.")
    input_group.add_argument("--demo-data", action="store_true", help="Use the built-in sample dataset.")
    input_group.add_argument("--sheet", dest="sheet_name", help="Excel sheet name or index. Ignored for CSV files.")
    input_group.add_argument("--range", dest="cell_range", help="Excel-style two-column or current-only range, for example A1:B81.")
    input_group.add_argument("--voltage-range", help="Excel-style voltage range, for example A1:A81.")
    input_group.add_argument("--current-range", help="Excel-style current-density range, for example B1:B81.")
    input_group.add_argument("--voltage-start", type=float, default=-1.0, help="Generated voltage start when only current range is provided.")
    input_group.add_argument("--voltage-end", type=float, default=1.0, help="Generated voltage end when only current range is provided.")
    input_group.add_argument("--voltage-step", type=float, default=0.01, help="Generated voltage step when only current range is provided.")

    fit_group = parser.add_argument_group("fit")
    fit_group.add_argument("--fit-strategy", default="quick_global", help="Fit strategy name passed to fit.strategy.")
    fit_group.add_argument("--sweep-strategies", action="store_true", help="Run the configured strategy sweep.")
    fit_group.add_argument("--reverse-weight", type=float, default=1.5)
    fit_group.add_argument("--near-zero-weight", type=float, default=0.5)
    fit_group.add_argument("--forward-weight", type=float, default=1.0)
    fit_group.add_argument("--high-forward-weight", type=float, default=1.5)
    fit_group.add_argument("--params", nargs=4, type=float, metavar=("J0", "RS", "RSH", "K"), help="Initial parameters.")
    fit_group.add_argument("--history", type=Path, help="Initial parameter file (.npz, .mat, or .txt).")

    analysis_group = parser.add_argument_group("analysis")
    analysis_group.add_argument("--analyze", action="store_true", help="Run exponent scans and model comparison.")
    analysis_group.add_argument("--scan-m", action="store_true", help="Scan non-ohmic exponent m.")
    analysis_group.add_argument("--scan-n", action="store_true", help="Scan diode ideality factor n.")
    analysis_group.add_argument("--m-values", nargs="+", type=float, default=list(DEFAULT_M_VALUES))
    analysis_group.add_argument("--n-values", nargs="+", type=float, default=list(DEFAULT_N_VALUES))
    analysis_group.add_argument("--compare-models", action="store_true", help="Compare simplified leakage models.")
    analysis_group.add_argument("--post-fit-models", action="store_true", help="Run post-fit model diagnostics.")

    output_group = parser.add_argument_group("output")
    output_group.add_argument("--save", action="store_true", help="Save result files under --output-dir.")
    output_group.add_argument("--output-dir", type=Path, default=ROOT / "outputs")
    output_group.add_argument("--show", action="store_true", help="Show matplotlib result windows.")
    output_group.add_argument("--verbose", action="store_true", help="Print verbose fit and analysis logs.")

    # Kept only so old one-off commands fail gracefully less often. The CLI is now always non-interactive.
    parser.add_argument("--no-prompt", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--no-show", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--interactive", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--ask-history", action="store_true", help=argparse.SUPPRESS)
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.demo_data and args.data is not None:
        parser.error("Use either --data PATH or --demo-data, not both.")
    if not args.demo_data and args.data is None:
        parser.error("No data file provided. Use --data PATH or --demo-data.")
    if args.interactive or args.ask_history:
        parser.error("--interactive and --ask-history were removed from main.py. Use the Web app for manual workflows.")

    try:
        data_v, data_jd = _load_cli_data(args)
        validate_input_data(data_v, data_jd)
        params_meta = _initial_params(args)
    except Exception as exc:
        parser.error(str(exc))

    run_scan_m = args.analyze or args.scan_m
    run_scan_n = args.analyze or args.scan_n
    run_compare = args.analyze or args.compare_models
    options = AnalysisOptions(
        run_fit=True,
        fit_strategy=args.fit_strategy,
        sweep_strategies=args.sweep_strategies,
        reverse_weight=args.reverse_weight,
        near_zero_weight=args.near_zero_weight,
        forward_weight=args.forward_weight,
        high_forward_weight=args.high_forward_weight,
        scan_m=run_scan_m,
        scan_n=run_scan_n,
        use_best_m_after_scan=True,
        compare_models=run_compare,
        post_fit_models=args.analyze or args.post_fit_models,
        m_values=tuple(args.m_values),
        n_values=tuple(args.n_values),
        quick_m_scan=True,
        warm_start_m_scan=True,
        fit_verbose=args.verbose,
        analysis_verbose=args.verbose,
    )

    config = load_config()
    analysis = run_analysis(data_v, data_jd, options, config=config, params_meta=params_meta)
    if analysis.fit is None:
        raise RuntimeError("Fitting did not run.")

    fit = analysis.fit
    stats = error_statistics(
        data_v,
        data_jd,
        fit.fit_results["JD"],
        voltage_zero_atol=fit.config.fitting.voltage_zero_atol,
        current_noise_floor=fit.config.fitting.current_noise_floor,
    )
    strategy = fit.diagnostics.get("strategy", args.fit_strategy)

    print("\nFinal summary:")
    print(f"Strategy: {strategy}")
    print(f"J0={fit.params[0]:.6e}, Rs={fit.params[1]:.6e}, Rsh={fit.params[2]:.6e}, k={fit.params[3]:.6e}")
    print(f"Mean relative error: {stats['mean']:.2f}%")
    print(f"Max relative error: {stats['max']:.2f}%")

    _print_m_scan(analysis.m_scan)
    _print_model_comparison(analysis.model_comparison)
    if run_scan_m or run_scan_n or run_compare or args.post_fit_models:
        _print_notes(analysis)

    show = bool(args.show and not args.no_show)
    figures = None
    if args.save or show:
        figures = plot_results(data_v, data_jd, fit.fit_results, fit.currents, show=False)
    if args.save:
        save_results(data_v, data_jd, fit.params, fit.fit_results, fit.currents, figures, output_dir=args.output_dir)
    if show:
        plt.show()
    else:
        plt.close("all")


if __name__ == "__main__":
    main()
