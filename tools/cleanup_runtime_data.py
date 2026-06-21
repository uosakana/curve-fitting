"""Dry-run first cleanup for local runtime data.

This script is intentionally conservative. It only targets ignored runtime
folders under app_data, prints the files it would remove by default, and
requires --apply plus an age filter or --all before deleting anything.
"""

from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


TARGETS = {
    "uploads": "uploads",
    "datasets": "datasets",
    "records": "records",
    "packages": "packages",
    "models": "models",
    "replays": "replays",
    "smoke": "smoke",
}


@dataclass(frozen=True)
class CleanupItem:
    path: Path
    size: int
    modified: datetime


def workspace_root() -> Path:
    return Path(__file__).resolve().parents[1]


def app_data_root(root: Path) -> Path:
    return checked_child(root, "app_data")


def checked_child(parent: Path, child: str) -> Path:
    candidate = (parent / child).resolve()
    if parent.resolve() not in [candidate, *candidate.parents]:
        raise ValueError(f"Refusing path outside workspace: {candidate}")
    return candidate


def format_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def collect_files(target_dirs: list[Path], older_than_days: int | None, include_all: bool) -> list[CleanupItem]:
    cutoff = None
    if older_than_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)

    items: list[CleanupItem] = []
    for target_dir in target_dirs:
        if not target_dir.exists():
            continue
        for path in sorted(target_dir.rglob("*")):
            if not path.is_file():
                continue
            stat = path.stat()
            modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            if include_all or cutoff is None or modified <= cutoff:
                items.append(CleanupItem(path=path, size=stat.st_size, modified=modified))
    return items


def collect_empty_dirs(target_dirs: list[Path]) -> list[Path]:
    empty_dirs: list[Path] = []
    for target_dir in target_dirs:
        if not target_dir.exists():
            continue
        for path in sorted((p for p in target_dir.rglob("*") if p.is_dir()), reverse=True):
            try:
                next(path.iterdir())
            except StopIteration:
                empty_dirs.append(path)
    return empty_dirs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preview or clean ignored app_data runtime files.")
    parser.add_argument(
        "--target",
        choices=[*TARGETS.keys(), "all"],
        default="uploads",
        help="Runtime area to clean. Default: uploads.",
    )
    parser.add_argument(
        "--older-than-days",
        type=int,
        default=None,
        help="Only include files whose modified time is at least this many days old.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Include files of any age. Required with --apply when no age filter is provided.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete matched files. Without this flag the command is a dry run.",
    )
    parser.add_argument(
        "--remove-empty-dirs",
        action="store_true",
        help="After deleting files, also remove empty directories inside the selected target.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=40,
        help="Maximum file rows to print. Use 0 to print only the summary.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.older_than_days is not None and args.older_than_days < 0:
        raise SystemExit("--older-than-days must be >= 0")
    if args.apply and args.older_than_days is None and not args.all:
        raise SystemExit("Refusing --apply without --older-than-days or --all.")

    root = workspace_root()
    app_data = app_data_root(root)
    selected = TARGETS.keys() if args.target == "all" else [args.target]
    target_dirs = [checked_child(app_data, TARGETS[name]) for name in selected]

    items = collect_files(target_dirs, args.older_than_days, args.all)
    total_size = sum(item.size for item in items)
    mode = "APPLY" if args.apply else "DRY RUN"
    age = "all ages" if args.all or args.older_than_days is None else f">= {args.older_than_days} days old"

    print(f"{mode}: target={args.target}, age={age}")
    print(f"Matched {len(items)} file(s), {format_size(total_size)}")

    if args.limit:
        for item in items[: args.limit]:
            relative = item.path.relative_to(root)
            when = item.modified.astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
            print(f"- {relative} | {format_size(item.size)} | {when}")
        remaining = len(items) - args.limit
        if remaining > 0:
            print(f"... {remaining} more file(s)")

    if not args.apply:
        print("No files deleted. Add --apply to delete matched files.")
        return 0

    for item in items:
        item.path.unlink()

    removed_dirs = 0
    if args.remove_empty_dirs:
        for directory in collect_empty_dirs(target_dirs):
            shutil.rmtree(directory)
            removed_dirs += 1

    print(f"Deleted {len(items)} file(s), {format_size(total_size)}.")
    if args.remove_empty_dirs:
        print(f"Removed {removed_dirs} empty directory/directories.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
