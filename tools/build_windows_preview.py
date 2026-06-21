from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import textwrap
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST_ROOT = ROOT / "dist"
BUILD_ROOT = ROOT / "build" / "pyinstaller_preview"
APP_NAME = "DarkCurrentWorkbench"
PACKAGE_NAME = "DarkCurrentWorkbenchPreview"
EXCLUDED_MODULES = (
    "IPython",
    "PIL",
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    "jupyter",
    "matplotlib",
    "notebook",
    "pyarrow",
    "pygame",
    "pytest",
    "sklearn",
    "sympy",
    "tensorflow",
    "tkinter",
    "torch",
    "torchaudio",
    "torchvision",
)


def checked_child(parent: Path, child: str) -> Path:
    candidate = (parent / child).resolve()
    if parent.resolve() not in [candidate, *candidate.parents]:
        raise ValueError(f"Refusing path outside workspace: {candidate}")
    return candidate


def run(command: list[str]) -> None:
    print("+ " + " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def verify_pyinstaller() -> None:
    try:
        subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--version"],
            cwd=ROOT,
            check=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            "PyInstaller is not available. Run build_preview_package.bat so it can "
            "install/repair the packaging tools first."
        ) from exc


def write_preview_files(app_dir: Path) -> None:
    launcher = app_dir / "Start Preview.bat"
    launcher.write_text(
        textwrap.dedent(
            f"""\
            @echo off
            cd /d "%~dp0"
            {APP_NAME}.exe
            set EXIT_CODE=%ERRORLEVEL%
            if not "%EXIT_CODE%"=="0" (
              echo.
              echo Preview exited with error code %EXIT_CODE%.
              pause
            )
            exit /b %EXIT_CODE%
            """
        ),
        encoding="utf-8",
    )

    readme = app_dir / "README_PREVIEW.txt"
    readme.write_text(
        textwrap.dedent(
            """\
            Dark Current Fitting Workbench - Preview Build

            How to run:
            1. Keep this whole folder together.
            2. Double-click "Start Preview.bat".
            3. Your browser should open automatically.

            Notes:
            - This preview build is local-only and starts a server on 127.0.0.1.
            - Runtime uploads are temporary and are cleared on normal shutdown.
            - Saved records/packages are written beside this executable under app_data/.
            - If Windows Defender warns on first launch, choose "More info" then "Run anyway"
              only if you received this package from a trusted source.
            """
        ),
        encoding="utf-8",
    )


def zip_dir(source_dir: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in source_dir.rglob("*"):
            archive.write(path, path.relative_to(source_dir.parent))


def build_package(*, skip_zip: bool = False) -> Path:
    verify_pyinstaller()

    output_dir = checked_child(DIST_ROOT, APP_NAME)
    package_dir = checked_child(DIST_ROOT, PACKAGE_NAME)
    zip_path = checked_child(DIST_ROOT, f"{PACKAGE_NAME}.zip")

    for target in (output_dir, package_dir):
        if target.exists():
            shutil.rmtree(target)
    if zip_path.exists():
        zip_path.unlink()

    static_dir = ROOT / "app" / "static"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name",
        APP_NAME,
        "--distpath",
        str(DIST_ROOT),
        "--workpath",
        str(BUILD_ROOT),
        "--specpath",
        str(BUILD_ROOT),
        "--add-data",
        f"{static_dir}{os.pathsep}app/static",
        "--collect-submodules",
        "uvicorn",
        "--hidden-import",
        "multipart.multipart",
        "--hidden-import",
        "uvicorn.lifespan.on",
        "--hidden-import",
        "uvicorn.protocols.http.h11_impl",
        "--hidden-import",
        "uvicorn.loops.auto",
        str(ROOT / "desktop_app.py"),
    ]
    for module in EXCLUDED_MODULES:
        command.extend(["--exclude-module", module])
    run(command)

    if not output_dir.exists():
        raise SystemExit(f"PyInstaller did not create expected output: {output_dir}")
    output_dir.rename(package_dir)
    write_preview_files(package_dir)

    if not skip_zip:
        zip_dir(package_dir, zip_path)
        print(f"Created {zip_path}", flush=True)
        return zip_path

    print(f"Created {package_dir}", flush=True)
    return package_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a Windows one-folder preview package.")
    parser.add_argument("--skip-zip", action="store_true", help="Leave only the dist folder; do not create a zip.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    artifact = build_package(skip_zip=args.skip_zip)
    print(f"Preview artifact: {artifact}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
