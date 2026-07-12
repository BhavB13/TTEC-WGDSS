from __future__ import annotations

import argparse
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.forecast_refresh_service import ForecastRefreshService


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Supervised freshness-aware demand forecast refresh."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Refresh even when no snapshot is newer than the existing training dataset.",
    )
    parser.add_argument(
        "--minimum-good-snapshots",
        type=int,
        default=48,
        help="Minimum Good-quality SCADA snapshots required before refresh (default: 48).",
    )
    args = parser.parse_args()

    result = ForecastRefreshService().refresh(
        force=args.force,
        minimum_good_snapshots=args.minimum_good_snapshots,
    )
    print(f"refreshed: {str(result.refreshed).lower()}")
    print(f"reason: {result.reason}")
    print(f"Good-quality snapshots: {result.good_snapshot_count}")
    if result.latest_good_snapshot_at is not None:
        print(f"latest Good-quality SCADA snapshot: {result.latest_good_snapshot_at.isoformat()}")
    if result.latest_training_feature_at is not None:
        print(f"latest training feature: {result.latest_training_feature_at.isoformat()}")
    if result.dataset_result is not None:
        print(f"training rows: {result.dataset_result.rows_created}")
    return 0 if result.refreshed else 2


if __name__ == "__main__":
    raise SystemExit(main())
