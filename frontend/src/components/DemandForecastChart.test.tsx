import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("react-chartjs-2", () => ({
  Line: () => <div data-testid="line-chart">Responsive chart</div>,
}));

import DemandForecastChart from "./DemandForecastChart";
import type { CalibrationSnapshot, GridStatus, ProbabilityData } from "../types/dashboard";

const grid: GridStatus = {
  current_demand_mw: 950,
  current_generation_mw: 960,
  total_available_capacity_mw: 1200,
  reserve_margin_percent: 26,
  grid_status: "NORMAL",
  demand_period: "AFTERNOON",
  source_provider: "MockGridProvider",
  generation_units: [],
};

const probability: ProbabilityData = {
  probability_score: 0.4,
  risk_level: "LOW",
  forecast_demand_30m: 970,
  forecast_demand_60m: 985,
  factors: [],
  reason: "Stable",
};

const calibration: CalibrationSnapshot = {
  selected_scenario_key: "hot",
  selected_scenario_label: "Hot Day",
  selection_reason: "Hot profile is the closest match",
  selection_confidence: 0.8,
  scenario_scores: { hot: 0.8, typical: 0.4, rainy: 0.2 },
  scenarios: [
    {
      scenario_key: "hot",
      scenario_label: "Hot Day",
      operating_regime: "HOT",
      source_workbook: "Load forecasting data.xlsx",
      source_sheet: "Hot day",
      demand_curve: [{ hour: 1, demand_mw: 1100, spin_mw: 150 }],
      scada_temperature_trace: [{ hour: 1, temperature_c: 30 }],
    },
  ],
};

describe("DemandForecastChart", () => {
  it("renders the selected calibration profile in a responsive chart container", () => {
    render(
      <DemandForecastChart
        gridStatus={grid}
        probability={probability}
        calibration={calibration}
      />,
    );

    expect(screen.getByText("Hot Day Profile")).toBeInTheDocument();
    expect(screen.getByText("SCADA + Scenario")).toBeInTheDocument();
    expect(screen.getByTestId("line-chart").parentElement).toHaveClass("w-full");
  });
});
