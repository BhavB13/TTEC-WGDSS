from __future__ import annotations

import argparse
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.demand_forecast_model_service import DemandForecastModelService


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Train/evaluate demand forecast baselines and optional ML model."
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append forecast results instead of replacing existing results",
    )
    args = parser.parse_args()

    result = DemandForecastModelService().train_and_store(
        replace_existing=not args.append
    )
    print(f"Demand forecast horizons evaluated: {len(result.results)}")
    for item in result.results:
        print(
            f"{item.horizon_hours}h: {item.active_model} "
            f"{item.forecast_demand_mw:.2f} MW "
            f"+/- {item.forecast_uncertainty_mw:.2f} MW "
            f"({item.mode})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
