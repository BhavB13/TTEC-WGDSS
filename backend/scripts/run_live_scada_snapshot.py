from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.live_scada_experiment_service import LiveScadaExperimentService


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the isolated, read-only WGDSS static SCADA snapshot test"
    )
    parser.add_argument("source", type=Path, help="CSV or ZIP Excel/OSI export")
    parser.add_argument("--session-root", type=Path, default=None)
    args = parser.parse_args()
    service = LiveScadaExperimentService(source_path=args.source)
    if args.session_root is not None:
        service.repository.root = args.session_root
    session = asyncio.run(service.run())
    print(f"session_id={session.session_id}")
    print(f"boundary={session.source.latest_valid_timestamp}")
    print(f"model_status={session.model.status}")
    print(f"report={session.artifacts.test_report_path}")


if __name__ == "__main__":
    main()
