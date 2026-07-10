from __future__ import annotations

import argparse
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.scada_snapshot_service import ScadaSnapshotService


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build normalized hourly SCADA grid snapshots from raw imports."
    )
    parser.add_argument(
        "--import-run-id",
        type=int,
        default=None,
        help="Optional scada_import_runs.id to build from",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append snapshots instead of replacing matching timestamps",
    )
    args = parser.parse_args()

    result = ScadaSnapshotService().build_hourly_snapshots(
        import_run_id=args.import_run_id,
        replace_existing=not args.append,
    )
    print(
        "Built SCADA grid snapshots: "
        f"{result.snapshots_created} snapshot(s), "
        f"{result.source_measurements} source measurement(s), "
        f"{result.degraded_snapshots} degraded"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
