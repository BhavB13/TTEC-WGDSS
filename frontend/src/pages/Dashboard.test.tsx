import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { dashboardFixture } from "../test/dashboardFixture";

const getDashboardSnapshot = vi.fn();

vi.mock("../services/api", () => ({
  getDashboardSnapshot: (...args: unknown[]) => getDashboardSnapshot(...args),
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

import Dashboard from "./Dashboard";

describe("Dashboard", () => {
  beforeEach(() => {
    getDashboardSnapshot.mockReset();
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
    expect(await screen.findByText("950 MW")).toBeInTheDocument();
    expect(screen.getAllByText("LIVE").length).toBeGreaterThan(0);
    expect(screen.getByTestId("weather-map")).toBeInTheDocument();
  });

  it("switches across the home, operations, weather, forecast, risk, guidance, and analytics tabs", async () => {
    getDashboardSnapshot.mockResolvedValue(dashboardFixture);
    const user = userEvent.setup();
    render(<Dashboard />);
    await screen.findByText("950 MW");

    await user.click(screen.getByRole("button", { name: "Home" }));
    expect(screen.getByText("Weather Drivers")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "700 to 1500 MW Window" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Operations" }));
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
  });

  it("shows the API error state and retries", async () => {
    getDashboardSnapshot
      .mockRejectedValueOnce(new Error("Backend unavailable"))
      .mockResolvedValueOnce(dashboardFixture);
    const user = userEvent.setup();
    render(<Dashboard />);

    expect(await screen.findByText("Backend unavailable")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.getByText("950 MW")).toBeInTheDocument());
    expect(getDashboardSnapshot).toHaveBeenCalledTimes(2);
  });
});
