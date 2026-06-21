from __future__ import annotations

import argparse
from pathlib import Path

from ml.dataset_builder import build_training_dataset
from ml.record_features import DEFAULT_DATASET_DIR, DEFAULT_RECORD_DIR


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a versioned training dataset from labeled fit records.")
    parser.add_argument("--records", type=Path, default=DEFAULT_RECORD_DIR, help="Directory containing fit_record_*.json files.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_DATASET_DIR, help="Directory where dataset files will be written.")
    parser.add_argument("--include-rejected", action="store_true", help="Include poor/reject records for risk-model datasets.")
    parser.add_argument("--train-ratio", type=float, default=0.7)
    parser.add_argument("--val-ratio", type=float, default=0.15)
    args = parser.parse_args()

    csv_path, manifest_path, manifest = build_training_dataset(
        args.records,
        args.output_dir,
        include_rejected=args.include_rejected,
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
    )
    print(f"Built {manifest['counts']['candidate_records']} candidate record(s).")
    print(f"CSV: {csv_path}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
