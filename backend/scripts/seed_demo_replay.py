from __future__ import annotations

import argparse
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.schemas.replay import ReplayControlRequest
from app.services.demo_replay_service import DemoReplayService


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed/reset the deterministic 12-month WGDSS demonstration replay."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace the existing demonstration archive before resetting playback.",
    )
    args = parser.parse_args()

    service = DemoReplayService()
    rows = service.ensure_seeded(force=args.force)
    status = service.control(ReplayControlRequest(action="reset"))
    print(f"demo observations: {rows}")
    print(f"replay window: {status.replay_start.isoformat()} to {status.replay_end.isoformat()}")
    print(f"cursor reset to: {status.cursor_at.isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
