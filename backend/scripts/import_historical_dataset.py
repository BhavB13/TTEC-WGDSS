from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.historical_data_import_service import HistoricalDataImportService


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate and import a registered WGDSS historical dataset."
    )
    parser.add_argument("source", help="CSV or ZIP dataset path")
    parser.add_argument("--adapter", help="Optional registered adapter id")
    args = parser.parse_args()
    report = HistoricalDataImportService().import_dataset(args.source, args.adapter)
    print(json.dumps(asdict(report), indent=2))


if __name__ == "__main__":
    main()
