from __future__ import annotations

import argparse
from pathlib import Path

from ml.package_export import DEFAULT_PACKAGE_DIR, build_offline_data_package
from ml.record_features import DEFAULT_DATASET_DIR, DEFAULT_RECORD_DIR


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a zip package for offline labeled-data collection.")
    parser.add_argument("--records", type=Path, default=DEFAULT_RECORD_DIR, help="Directory containing fit_record_*.json files.")
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET_DIR, help="Directory for generated dataset CSV/manifest.")
    parser.add_argument("--package-dir", type=Path, default=DEFAULT_PACKAGE_DIR, help="Directory where the zip package will be written.")
    parser.add_argument("--include-rejected", action="store_true", help="Include poor/reject records for risk-model collection.")
    parser.add_argument("--app-version", default="0.1.0")
    args = parser.parse_args()

    path, manifest = build_offline_data_package(
        args.records,
        args.dataset_dir,
        args.package_dir,
        include_rejected=args.include_rejected,
        app_version=args.app_version,
    )
    print(f"Package: {path}")
    print(f"Candidate records: {manifest['counts']['candidate_records']}")


if __name__ == "__main__":
    main()
