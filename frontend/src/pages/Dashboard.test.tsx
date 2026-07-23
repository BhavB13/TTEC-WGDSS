import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { dashboardFixture, replayDashboardFixture } from "../test/dashboardFixture";

const getDashboardSnapshot = vi.fn();
const controlReplay = vi.fn();
const evaluateCapacityPlan = vi.fn();
const getLiveWeatherDisplay = vi.fn();
const weatherMapProps = vi.fn();

vi.mock("../services/api", () => ({
  getDashboardSnapshot: (...args: unknown[]) => getDashboardSnapshot(...args),
  controlReplay: (...args: unknown[]) => controlReplay(...args),
  evaluateCapacityPlan: (...args: unknown[]) => evaluateCapacityPlan(...args),
  getLiveWeatherDisplay: (...args: unknown[]) => getLiveWeatherDisplay(...args),
}));
vi.mock("../components/WeatherMap", () => ({
  default: (props: unknown) => {
    weatherMapProps(props);
    return <div data-testid="weather-map">Weather map</div>;
  },
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
vi.mock("../components/SelectedDayChart", () => ({
  default: () => <div data-testid="selected-day-chart">Selected day chart</div>,
}));

import Dashboard from "./Dashboard";

describe("Dashboard", () => {
  beforeEach(() => {
    getDashboardSnapshot.mockReset();
    controlReplay.mockReset();
    evaluateCapacityPlan.mockReset();
    getLiveWeatherDisplay.mockReset();
    weatherMapProps.mockReset();
    evaluateCapacityPlan.mockResolvedValue(dashboardFixture.capacity_plan);
    getLiveWeatherDisplay.mockResolvedValue({
      weather: {
        ...dashboardFixture.weather,
        timestamp: "2026-07-22T13:15:00-04:00",
        temperature_c: 30.9,
        provider_name: "Open-Meteo Best Match",
      },
      forecast: dashboardFixture.forecast.items.map((item, index) => ({
        ...item,
        forecast_timestamp: new Date(Date.now() + (index + 1) * 3_600_000).toISOString(),
        provider_name: "Consensus (Open-Meteo Best Match + MET Norway + Open-Meteo NOAA GFS)",
      })),
      fetchedAt: "2026-07-22T13:16:00-04:00",
    });
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
    await user.click(screen.getByRole("button", { name: "Weather" }));
    expect(screen.getByText("Active Weather")).toBeInTheDocument();
    await waitFor(() => expect(getLiveWeatherDisplay).toHaveBeenCalled());

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
    expect(screen.getByText("Next 6 Hours · Weather + Demand")).toBeInTheDocument();
    expect(screen.getAllByText("3 sources")).toHaveLength(6);
    await waitFor(() => expect(getLiveWeatherDisplay).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("30.9°C")).toBeInTheDocument();
    expect(
      screen.getByText("Current T&T provider network"),
    ).toBeInTheDocument();
    expect(screen.getByText("Open-Meteo Best Match")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Demand Forecast" }));
    expect(screen.getByTestId("demand-chart")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Risk Gauge" }));
    expect(screen.getByTestId("probability-gauge")).toBeInTheDocument();
    expect(screen.getByTestId("risk-timeline")).toBeInTheDocument();
    expect(screen.getByText("Generation Need Evidence")).toBeInTheDocument();
    expect(screen.getByText("Peak Forecast Demand")).toBeInTheDocument();
    expect(screen.getByText("Observed TRA")).toBeInTheDocument();
    expect(screen.getByText("Peak Reserve")).toBeInTheDocument();
    expect(screen.getByText("Maximum Need After Plan")).toBeInTheDocument();
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
    expect(screen.getByText(/Source \/ hour alignment:/i)).toBeInTheDocument();
  });

  it("selects a previous June day across tabs and resets to the active day", async () => {
    const previousDayFixture = {
      ...dashboardFixture,
      grid: {
        ...dashboardFixture.grid,
        current_demand_mw: 1010,
        grid_status: "REPLAY COMPLETE",
      },
      replay: null,
      time_context: {
        ...dashboardFixture.time_context,
        selected_date: "2026-06-20",
        is_active_day: false,
        displayed_at: "2026-06-20T23:00:00",
        value_classification: "SIMULATED_REPLAY_DAY",
        source: "AspenTech OSI June 2026 trend exports",
        record_count: 24,
        series: [
          {
            timestamp: "2026-06-20T23:00:00",
            demand_mw: 1010,
            generation_tra_mw: 1190,
            spinning_reserve_mw: 80,
            available_capacity_mw: 1300,
            temperature_c: 28,
            quality_status: "GOOD",
            completeness_percent: 100,
            data_phase: "JUNE_OBSERVED" as const,
          },
        ],
      },
    };
    getDashboardSnapshot.mockImplementation(
      (options?: { selectedDate?: string | null }) =>
        Promise.resolve(
          options?.selectedDate === "2026-06-20"
            ? previousDayFixture
            : dashboardFixture,
        ),
    );
    const user = userEvent.setup();
    render(<Dashboard />);
    await screen.findByText(/ACTIVE · SIMULATED PRESENT/i);

    const dateInput = screen.getByLabelText("June replay date");
    fireEvent.change(dateInput, { target: { value: "2026-06-19" } });
    expect(
      screen.getByText("That date is unavailable in the June replay."),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Previous available day" }));
    await waitFor(() =>
      expect(getDashboardSnapshot).toHaveBeenLastCalledWith(
        expect.objectContaining({
          selectedDate: "2026-06-20",
        }),
      ),
    );
    expect(
      await screen.findByText(/PREVIOUS DAY · JUNE REPLAY/i),
    ).toBeInTheDocument();
    expect(screen.getAllByText("1010 MW").length).toBeGreaterThan(0);
    expect(screen.getByText("ARCHIVED")).toBeInTheDocument();
    expect(screen.getByText("NOT APPLICABLE")).toBeInTheDocument();
    expect(screen.getByText(/REPLAY COMPLETE/)).toBeInTheDocument();
    expect(weatherMapProps).toHaveBeenLastCalledWith(
      expect.objectContaining({ liveSamplingEnabled: false }),
    );

    await user.click(screen.getByRole("button", { name: "Demand Forecast" }));
    expect(screen.getByTestId("selected-day-chart")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Analytics" }));
    expect(screen.getByText(/PREVIOUS DAY · JUNE REPLAY/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Return to Active Day" }));
    await waitFor(() =>
      expect(getDashboardSnapshot).toHaveBeenLastCalledWith(
        expect.objectContaining({ selectedDate: null }),
      ),
    );
    expect(await screen.findByText(/ACTIVE · SIMULATED PRESENT/i)).toBeInTheDocument();
    expect(weatherMapProps).toHaveBeenLastCalledWith(
      expect.objectContaining({ liveSamplingEnabled: true }),
    );
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
