import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { lineChartSpy } = vi.hoisted(() => ({
  lineChartSpy: vi.fn(),
}));

vi.mock("react-chartjs-2", () => ({
  Line: (props: unknown) => {
    lineChartSpy(props);
    return <div data-testid="replay-line-chart">Replay chart</div>;
  },
}));

import ReplayLoadChart from "./ReplayLoadChart";
import { replayDashboardFixture } from "../test/dashboardFixture";

describe("ReplayLoadChart", () => {
  beforeEach(() => {
    lineChartSpy.mockClear();
  });

  it("aligns revealed generation to the full-day demand timestamps", () => {
    const replay = replayDashboardFixture.replay;
    if (!replay) {
      throw new Error("Replay fixture is required");
    }

    render(
      <ReplayLoadChart
        replay={{
          ...replay,
          status: {
            ...replay.status,
            source: "Historical SCADA Replay — June 2026",
            mode: "historical_replay",
          },
          operational_history: [
            {
              timestamp: "2025-06-01T00:00:00-04:00",
              demand_mw: 795,
              generation_mw: 825,
              spinning_reserve_mw: 25,
              available_capacity_mw: 1200,
              reserve_margin_percent: 51,
              temperature_c: 25,
              rainfall_mm_hr: 0,
              data_phase: "REPLAY_REVEALED",
            },
            {
              timestamp: "2025-06-01T01:00:00-04:00",
              demand_mw: 805,
              generation_mw: 835,
              spinning_reserve_mw: 27,
              available_capacity_mw: 1200,
              reserve_margin_percent: 49,
              temperature_c: 25,
              rainfall_mm_hr: 0,
              data_phase: "REPLAY_REVEALED",
            },
          ],
        }}
      />,
    );

    const chartProps = lineChartSpy.mock.calls.at(-1)?.[0] as {
      data: { datasets: Array<{ label: string; data: Array<number | null> }> };
    };
    const generation = chartProps.data.datasets.find(
      (dataset) => dataset.label === "Generation (TRA)",
    );

    expect(generation?.data.slice(0, 3)).toEqual([825, 835, null]);
    expect(
      screen.getByLabelText("Load forecast chart key"),
    ).toHaveTextContent(
      "90% forecast rangeForecast demandHistorical averageActual demandGeneration (TRA)Temperature · observed / forecast",
    );

    const observedTemperature = chartProps.data.datasets.find(
      (dataset) => dataset.label === "Observed temperature",
    );
    const forecastTemperature = chartProps.data.datasets.find(
      (dataset) => dataset.label === "Forecast temperature",
    );
    expect(observedTemperature?.data.slice(7, 10)).toEqual([27.8, 28.2, null]);
    expect(forecastTemperature?.data.slice(7, 11)).toEqual([
      null,
      28.2,
      28.6,
      28.75,
    ]);

    const options = lineChartSpy.mock.calls.at(-1)?.[0] as {
      options: {
        plugins: {
          legend: { display: boolean };
          tooltip: {
            filter: (context: { dataset: { label: string } }) => boolean;
            callbacks: {
              label: (context: {
                dataset: { label: string };
                raw: number;
              }) => string;
              afterLabel: (context: {
                dataset: { label: string };
                dataIndex: number;
              }) => string[];
              afterBody: (items: Array<{ dataIndex: number }>) => string[];
            };
          };
        };
        scales: {
          x: { offset: boolean; ticks: { maxTicksLimit: number } };
          y: {
            min: number;
            max: number;
            ticks: { stepSize: number };
          };
          temperature: {
            min: number;
            max: number;
            position: string;
          };
        };
      };
    };
    expect(options.options.plugins.legend.display).toBe(false);
    expect(options.options.scales.x.offset).toBe(true);
    expect(options.options.scales.x.ticks.maxTicksLimit).toBe(12);
    expect(options.options.scales.y).toMatchObject({
      min: 700,
      max: 1500,
      ticks: { stepSize: 100 },
    });
    expect(options.options.scales.temperature).toMatchObject({
      position: "right",
      min: 24,
      max: 32,
    });
    expect(
      options.options.plugins.tooltip.filter({
        dataset: { label: "Forecast uncertainty" },
      }),
    ).toBe(false);
    expect(
      options.options.plugins.tooltip.callbacks.afterLabel({
        dataset: { label: "Forecast demand" },
        dataIndex: 0,
      }),
    ).toEqual(["90% forecast range: 780 MW to 820 MW"]);
    expect(
      options.options.plugins.tooltip.callbacks.label({
        dataset: { label: "Observed temperature" },
        raw: 25,
      }),
    ).toBe("Observed temperature: 25.0°C");
    expect(
      options.options.plugins.tooltip.callbacks.afterBody([{ dataIndex: 0 }]),
    ).toEqual(
      expect.arrayContaining([
        "TRA-demand gap: +30 MW",
        "System spin (corrected): 25 MW",
        "Spin adjustment: -5 MW",
      ]),
    );
  });

  it("keeps the standard operating scale and expands for visible extremes", () => {
    const replay = replayDashboardFixture.replay;
    if (!replay) {
      throw new Error("Replay fixture is required");
    }

    render(
      <ReplayLoadChart
        replay={{
          ...replay,
          status: { ...replay.status, mode: "historical_replay" },
          operational_history: [
            {
              timestamp: "2025-06-01T00:00:00-04:00",
              demand_mw: 795,
              generation_mw: 1725,
              spinning_reserve_mw: 25,
              available_capacity_mw: 1800,
              reserve_margin_percent: 51,
              temperature_c: 25,
              rainfall_mm_hr: 0,
              data_phase: "REPLAY_REVEALED",
            },
          ],
        }}
      />,
    );

    const chartProps = lineChartSpy.mock.calls.at(-1)?.[0] as {
      options: { scales: { y: { min: number; max: number } } };
    };
    expect(chartProps.options.scales.y).toMatchObject({ min: 700, max: 1800 });
  });
});
