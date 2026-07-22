import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { dashboardFixture, replayDashboardFixture } from "../test/dashboardFixture";

const getDashboardSnapshot = vi.fn();
const controlReplay = vi.fn();
const evaluateCapacityPlan = vi.fn();

vi.mock("../services/api", () => ({
  getDashboardSnapshot: (...args: unknown[]) => getDashboardSnapshot(...args),
  controlReplay: (...args: unknown[]) => controlReplay(...args),
  evaluateCapacityPlan: (...args: unknown[]) => evaluateCapacityPlan(...args),
}));
vi.mock("../components/WeatherMap", () => ({
  default: () => <div data-testid="weather-map">Weather map</div>,
}));
vi.mock("../components/DemandForecastChart", () => ({
  default: () => <div data-testid="demand-chart">Demand chart</div>,
}));
vi.mock("../components/ProbabilityGauge", () => ({
  default: () => <div data-testid="probability-gauge">Probability gauge</div>,
}));
vi.mock("../components/RiskTimelineChart", () => ({
  default: () => <div data-testid="risk-timeline">Risk timeline</div>,
}));
vi.mock("../components/ScenarioComparisonChart", () => ({
  default: () => <div data-testid="scenario-chart">Scenario chart</div>,
}));
vi.mock("../components/ReplayLoadChart", () => ({
  default: () => <div data-testid="replay-load-chart">Replay load chart</div>,
}));
vi.mock("../components/HistoricalDemandChart", () => ({
  default: () => <div data-testid="historical-demand-chart">Historical demand chart</div>,
}));

import Dashboard from "./Dashboard";

describe("Dashboard", () => {
  beforeEach(() => {
    getDashboardSnapshot.mockReset();
    controlReplay.mockReset();
    evaluateCapacityPlan.mockReset();
    evaluateCapacityPlan.mockResolvedValue(dashboardFixture.capacity_plan);
    window.localStorage.clear();
  });

  it("renders the simulated-live control room and advances playback", async () => {
    getDashboardSnapshot.mockResolvedValue(replayDashboardFixture);
    controlReplay.mockResolvedValue(replayDashboardFixture.replay?.status);
    const user = userEvent.setup();
    render(<Dashboard />);

    expect(await screen.findByText("Simulation replay")).toBeInTheDocument();
    expect(screen.getByTestId("replay-load-chart")).toBeInTheDocument();
    expect(screen.getByText("Weather · Current + 6 Hours")).toBeInTheDocument();
    expect(
      screen.getByText(
        "2025 hourly SCADA + weather demonstration · 9/720 records · 1.1%",
      ),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Step" }));
    await waitFor(() =>
      expect(controlReplay).toHaveBeenCalledWith({ action: "step" }),
    );
  });

  it("shows a loading state and then renders live snapshot data", async () => {
    let resolveSnapshot: (value: typeof dashboardFixture) => void = () => {};
    getDashboardSnapshot.mockReturnValue(
      new Promise((resolve) => {
        resolveSnapshot = resolve;
      }),
    );

    const { container } = render(<Dashboard />);
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();

    resolveSnapshot(dashboardFixture);
    expect((await screen.findAllByText("950 MW")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("LIVE").length).toBeGreaterThan(0);
    expect(screen.getByTestId("weather-map")).toBeInTheDocument();
  });

  it("switches across the operator overview, grid operations, weather, forecast, risk, guidance, and analytics workspaces", async () => {
    getDashboardSnapshot.mockResolvedValue(dashboardFixture);
    const user = userEvent.setup();
    render(<Dashboard />);
    await screen.findAllByText("950 MW");

    await user.click(screen.getByRole("button", { name: "Operator Overview" }));
    expect(screen.getByText("Weather Drivers")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Next 60 Minutes" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Recommended Operating Posture" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Grid Operations" }));
    expect(screen.getByText("Station Dispatch")).toBeInTheDocument();
    expect(screen.getByText("Unit Readiness")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Weather" }));
    expect(screen.getByText("Current Weather Conditions")).toBeInTheDocument();
    expect(screen.getByText("Next 6 Hours")).toBeInTheDocument();
    expect(screen.getAllByText("3 sources")).toHaveLength(6);

    await user.click(screen.getByRole("button", { name: "Demand Forecast" }));
    expect(screen.getByTestId("demand-chart")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Risk Gauge" }));
    expect(screen.getByTestId("probability-gauge")).toBeInTheDocument();
    expect(screen.getByTestId("risk-timeline")).toBeInTheDocument();
    expect(screen.getByText("Capacity Risk Evidence")).toBeInTheDocument();
    expect(screen.getByText("Peak Forecast Demand")).toBeInTheDocument();
    expect(screen.getByText("Observed TRA")).toBeInTheDocument();
    expect(screen.getByText("Peak Reserve")).toBeInTheDocument();
    expect(screen.getByText("Post-Plan Peak Risk")).toBeInTheDocument();
    expect(screen.getByText("TRA With Starts")).toBeInTheDocument();
    expect(screen.getByText("Risk Reduction")).toBeInTheDocument();
    expect(screen.getByText("Risk Drivers")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Operational Guidance" }));
    expect(
      screen.getByText("ADVISORY ONLY - MANUAL OPERATOR ACTION REQUIRED"),
    ).toBeInTheDocument();
    expect(screen.getByText("Machine-Generated Suggestion")).toBeInTheDocument();
    expect(
      screen.getByText(
        "REVIEW START OF 2 X SMALL FAST-START SET (30.0 MW TOTAL)",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Aggregate Start Blocks")).toBeInTheDocument();
    expect(screen.getByText("Capacity Plan Evaluation")).toBeInTheDocument();
    expect(screen.getByText("Proposed Starts")).toBeInTheDocument();
    expect(screen.getByText("Operator Checks")).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: "Remove one Small fast-start set" }),
    );
    await user.click(screen.getByRole("button", { name: "Evaluate Selection" }));
    await waitFor(() =>
      expect(evaluateCapacityPlan).toHaveBeenCalledWith({
        snapshot_id: "snapshot-capacity-plan-1",
        actions: [{ block_id: "small-fast-start", count: 1 }],
      }),
    );

    await user.click(screen.getByRole("button", { name: "Analytics" }));
    expect(screen.getByText("Calibration Summary")).toBeInTheDocument();
    expect(screen.getByText("Forecast Assurance")).toBeInTheDocument();
    expect(screen.getByText("Source / Hour Alignment")).toBeInTheDocument();
  });

  it("shows the API error state and retries", async () => {
    getDashboardSnapshot
      .mockRejectedValueOnce(new Error("Backend unavailable"))
      .mockResolvedValueOnce(dashboardFixture);
    const user = userEvent.setup();
    render(<Dashboard />);

    expect(await screen.findByText("Backend unavailable")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.getAllByText("950 MW").length).toBeGreaterThan(0));
    expect(getDashboardSnapshot).toHaveBeenCalledTimes(2);
  });

  it("switches the control-room theme without affecting live dashboard rendering", async () => {
    getDashboardSnapshot.mockResolvedValue(dashboardFixture);
    const user = userEvent.setup();
    render(<Dashboard />);

    await screen.findAllByText("950 MW");
    const shell = screen.getByRole("main").parentElement;
    expect(shell).toHaveClass("theme-dark");

    await user.click(screen.getByRole("button", { name: "Use light theme" }));
    expect(shell).toHaveClass("theme-light");
    expect(screen.getByTestId("weather-map")).toBeInTheDocument();
  });
});
