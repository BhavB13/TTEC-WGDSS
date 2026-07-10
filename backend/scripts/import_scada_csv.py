from __future__ import annotations

import argparse
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.scada_import_service import ScadaImportService


def main() -> int:
    parser = argparse.ArgumentParser(description="Import a historical SCADA CSV export.")
    parser.add_argument("csv_path", help="Path to the SCADA CSV export")
    args = parser.parse_args()

    result = ScadaImportService().import_csv(args.csv_path)
    if result.skipped_duplicate:
        print(
            "Duplicate SCADA CSV skipped: "
            f"{result.source_filename} ({result.row_count} existing row(s))"
        )
    else:
        print(
            "Imported SCADA CSV: "
            f"{result.source_filename} ({result.row_count} row(s))"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
