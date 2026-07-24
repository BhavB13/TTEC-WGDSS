from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.frozen_model_artifact_service import FrozenModelArtifactService

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export the validated October-May WGDSS demand models"
    )
    parser.add_argument(
        "--output",
        default="var/models/wgdss-demand-v5.joblib",
        help="Destination joblib artifact",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            FrozenModelArtifactService().export(args.output),
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
