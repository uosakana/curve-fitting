from __future__ import annotations

import argparse
from pathlib import Path

from ml.baseline_training import DEFAULT_MODEL_DIR, TASK_DEFS, train_random_forest_baseline
from ml.dataset_builder import build_training_dataset
from ml.record_features import DEFAULT_DATASET_DIR, DEFAULT_RECORD_DIR


def _dataset_path(args) -> Path:
    if args.dataset is not None:
        return args.dataset
    path, _manifest_path, _manifest = build_training_dataset(
        args.records,
        args.dataset_dir,
        include_rejected=args.include_rejected,
    )
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Train first-pass Random Forest baselines from labeled fit datasets.")
    parser.add_argument("--dataset", type=Path, default=None, help="Existing fit_dataset_*.csv file.")
    parser.add_argument("--records", type=Path, default=DEFAULT_RECORD_DIR, help="Record directory used when --dataset is omitted.")
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET_DIR, help="Dataset output directory used when --dataset is omitted.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_MODEL_DIR, help="Directory for model and metrics artifacts.")
    parser.add_argument("--task", choices=[*TASK_DEFS.keys(), "all"], default="strategy")
    parser.add_argument("--include-rejected", action="store_true", help="Include poor/reject records when building a dataset.")
    parser.add_argument("--n-estimators", type=int, default=300)
    parser.add_argument("--min-samples-leaf", type=int, default=2)
    args = parser.parse_args()

    dataset = _dataset_path(args)
    tasks = list(TASK_DEFS) if args.task == "all" else [args.task]
    for task in tasks:
        model_path, metrics_path, metrics = train_random_forest_baseline(
            dataset,
            task,
            args.output_dir,
            n_estimators=args.n_estimators,
            min_samples_leaf=args.min_samples_leaf,
        )
        print(f"[{task}] accuracy={metrics['accuracy']:.3f}, balanced_accuracy={metrics['balanced_accuracy']:.3f}")
        print(f"[{task}] model: {model_path}")
        print(f"[{task}] metrics: {metrics_path}")


if __name__ == "__main__":
    main()
