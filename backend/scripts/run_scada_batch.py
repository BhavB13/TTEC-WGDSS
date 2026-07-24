from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.scada_batch_ingestion_service import ScadaBatchIngestionService
from app.services.operational_forecast_orchestrator import (
    OperationalForecastOrchestrator,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Process stable periodic SCADA CSV/ZIP exports"
    )
    parser.add_argument("--input-dir", default=None)
    parser.add_argument("--state", default=None)
    args = parser.parse_args()
    orchestrator = OperationalForecastOrchestrator()
    result = ScadaBatchIngestionService(
        input_directory=args.input_dir,
        state_path=args.state,
        on_watermark_advanced=lambda watermark: orchestrator.issue(
            watermark,
            data_mode="BATCH_SCADA_EXPORT",
            source_provider="CSV_TREND_EXPORT",
        ),
    ).run()
    print(json.dumps(asdict(result), indent=2))
    return 1 if any(item.status == "FAILED" for item in result.files) else 0


if __name__ == "__main__":
    raise SystemExit(main())
