import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { dashboardFixture, replayDashboardFixture } from "../test/dashboardFixture";

const getDashboardSnapshot = vi.fn();
const controlReplay = vi.fn();

vi.mock("../services/api", () => ({
  getDashboardSnapshot: (...args: unknown[]) => getDashboardSnapshot(...args),
  controlReplay: (...args: unknown[]) => controlReplay(...args),
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
    window.localStorage.clear();
  });

  it("renders the simulated-live control room and advances playback", async () => {
    getDashboardSnapshot.mockResolvedValue(replayDashboardFixture);
    controlReplay.mockResolvedValue(replayDashboardFixture.replay?.status);
    const user = userEvent.setup();
    render(<Dashboard />);

    expect(await screen.findByText("Simulated Live SCADA")).toBeInTheDocument();
    expect(screen.getByTestId("replay-load-chart")).toBeInTheDocument();
    expect(screen.getByText("Weather · Current + 6 Hours")).toBeInTheDocument();
    expect(screen.getByText("9/720 June records · 1.1%")).toBeInTheDocument();

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

    await user.click(screen.getByRole("button", { name: "Operational Guidance" }));
    expect(screen.getByText("30m Headroom")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Analytics" }));
    expect(screen.getByText("Calibration Summary")).toBeInTheDocument();
    expect(screen.getByText("Model Status")).toBeInTheDocument();
    expect(screen.getByText("Baseline Active")).toBeInTheDocument();
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
