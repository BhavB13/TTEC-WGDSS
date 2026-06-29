import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("react-chartjs-2", () => ({
  Line: () => <div data-testid="scenario-line-chart">Scenario chart</div>,
}));

import ScenarioComparisonChart from "./ScenarioComparisonChart";
import type { CalibrationScenario } from "../types/dashboard";

const scenarios: CalibrationScenario[] = [
  {
    scenario_key: "hot",
    scenario_label: "Hot Day",
    operating_regime: "HOT",
    source_workbook: "Load forecasting data.xlsx",
    source_sheet: "Hot day",
    demand_curve: [
      { hour: 1, demand_mw: 1100, spin_mw: 150 },
      { hour: 2, demand_mw: 1110, spin_mw: 150 },
    ],
    scada_temperature_trace: [{ hour: 1, temperature_c: 31 }],
  },
  {
    scenario_key: "typical",
    scenario_label: "Typical Day",
    operating_regime: "TYPICAL",
    source_workbook: "Load forecasting data.xlsx",
    source_sheet: "Typical day",
    demand_curve: [
      { hour: 1, demand_mw: 950, spin_mw: 150 },
      { hour: 2, demand_mw: 960, spin_mw: 150 },
    ],
    scada_temperature_trace: [{ hour: 1, temperature_c: 29 }],
  },
];

describe("ScenarioComparisonChart", () => {
  it("renders the calibration comparison with a responsive parent container", () => {
    render(<ScenarioComparisonChart scenarios={scenarios} selectedScenarioKey="typical" />);

    expect(screen.getByText("Hot, Typical, and Rainy Demand Curves")).toBeInTheDocument();
    expect(screen.getByText("24h Comparison")).toBeInTheDocument();
    expect(screen.getByTestId("scenario-line-chart").parentElement).toHaveClass("w-full");
  });
});
