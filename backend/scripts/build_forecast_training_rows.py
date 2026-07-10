from __future__ import annotations

import argparse
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.forecast_dataset_service import ForecastDatasetService


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build model-ready demand forecast training rows."
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append rows instead of replacing existing training rows",
    )
    args = parser.parse_args()

    result = ForecastDatasetService().build_training_rows(
        replace_existing=not args.append
    )
    print(
        "Built forecast training rows: "
        f"{result.rows_created} row(s), "
        f"{result.source_snapshots} source snapshot(s), "
        f"{result.skipped_rows} skipped"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
