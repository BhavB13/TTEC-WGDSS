from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.calibration_import_service import CalibrationImportService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import WGDSS calibration data from the provided data.zip archive.",
    )
    parser.add_argument(
        "archive",
        nargs="?",
        help="Path to the calibration zip archive (defaults to backend/data.zip or CALIBRATION_DATA_ZIP_PATH).",
    )
    parser.add_argument(
        "--no-replace",
        action="store_true",
        help="Append data instead of replacing existing rows from the same archive.",
    )
    return parser


def resolve_archive_path(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()

    import os

    env_path = os.environ.get("CALIBRATION_DATA_ZIP_PATH", "").strip()
    if env_path:
        return Path(env_path).expanduser().resolve()

    default_path = Path(__file__).resolve().parents[2] / "data.zip"
    return default_path.resolve()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = build_parser()
    args = parser.parse_args()
    archive_path = resolve_archive_path(args.archive)

    service = CalibrationImportService()
    counts = service.import_archive(archive_path, replace_existing=not args.no_replace)

    print(
        "Imported calibration archive:",
        archive_path,
        "|",
        ", ".join(f"{key}={value}" for key, value in counts.items()),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
