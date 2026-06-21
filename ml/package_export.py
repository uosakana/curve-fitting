from __future__ import annotations

import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from ml.dataset_builder import build_training_dataset
from ml.record_features import DEFAULT_DATASET_DIR, DEFAULT_RECORD_DIR, flatten_record, load_records
from ml.record_schema import SCHEMA_VERSION


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACKAGE_DIR = ROOT / "app_data" / "packages"


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return counts


def _is_candidate(row: dict[str, Any], include_rejected: bool) -> bool:
    if include_rejected:
        return True
    if row.get("accepted"):
        return True
    return row.get("quality") in {"good", "acceptable"}


def _readme_text(manifest: dict[str, Any]) -> str:
    return (
        "# JV Fit Offline Data Package\n\n"
        "This package was exported by the local JV dark-current fitting app.\n\n"
        f"- Package ID: {manifest['package_id']}\n"
        f"- Created at: {manifest['created_at']}\n"
        f"- Schema version: {manifest['schema_version']}\n"
        f"- Candidate records: {manifest['counts']['candidate_records']}\n"
        f"- Include rejected records: {manifest['filters']['include_rejected']}\n\n"
        "Contents:\n\n"
        "- `records/`: raw labeled fit records in JSON format.\n"
        "- `datasets/`: flattened CSV dataset and dataset manifest.\n"
        "- `package_manifest.json`: package-level summary for data collection.\n"
    )


def build_offline_data_package(
    record_dir: str | Path = DEFAULT_RECORD_DIR,
    dataset_dir: str | Path = DEFAULT_DATASET_DIR,
    package_dir: str | Path = DEFAULT_PACKAGE_DIR,
    *,
    include_rejected: bool = False,
    app_version: str = "0.1.0",
) -> tuple[Path, dict[str, Any]]:
    records = load_records(record_dir)
    rows = [flatten_record(record) for record in records]
    candidates = [row for row in rows if _is_candidate(row, include_rejected)]

    csv_path, dataset_manifest_path, dataset_manifest = build_training_dataset(
        record_dir,
        dataset_dir,
        include_rejected=include_rejected,
    )

    output = Path(package_dir)
    output.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    package_id = f"jv_fit_records_{timestamp}"
    package_path = output / f"{package_id}.zip"

    candidate_record_paths = [
        Path(row["record_path"])
        for row in candidates
        if row.get("record_path") and Path(row["record_path"]).exists()
    ]

    manifest = {
        "package_id": package_id,
        "package_type": "jv_fit_offline_records",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "app_version": app_version,
        "schema_version": SCHEMA_VERSION,
        "record_dir": str(Path(record_dir)),
        "filters": {
            "include_rejected": bool(include_rejected),
            "candidate_rule": "accepted=true OR quality in {good, acceptable}",
        },
        "counts": {
            "raw_records": len(records),
            "candidate_records": len(candidates),
            "accepted": _count_by(candidates, "accepted"),
            "quality": _count_by(candidates, "quality"),
            "hypothesis": _count_by(candidates, "hypothesis"),
            "fit_strategy": _count_by(candidates, "fit_strategy"),
        },
        "dataset": dataset_manifest,
        "files": {
            "dataset_csv": f"datasets/{csv_path.name}",
            "dataset_manifest": f"datasets/{dataset_manifest_path.name}",
            "record_count": len(candidate_record_paths),
        },
    }

    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("package_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr("README.md", _readme_text(manifest))
        archive.write(csv_path, f"datasets/{csv_path.name}")
        archive.write(dataset_manifest_path, f"datasets/{dataset_manifest_path.name}")
        for path in candidate_record_paths:
            archive.write(path, f"records/{path.name}")

    return package_path, manifest
