from __future__ import annotations

import argparse
from pathlib import Path

from ml.record_features import DEFAULT_DATASET_DIR, DEFAULT_RECORD_DIR, export_records_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Export labeled fit records to a machine-learning CSV dataset.")
    parser.add_argument("--records", type=Path, default=DEFAULT_RECORD_DIR, help="Directory containing fit_record_*.json files.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_DATASET_DIR, help="Directory where the CSV dataset will be written.")
    args = parser.parse_args()

    path, count = export_records_dataset(args.records, args.output_dir)
    print(f"Exported {count} record(s) to {path}")


if __name__ == "__main__":
    main()
