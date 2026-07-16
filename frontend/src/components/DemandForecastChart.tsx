import { useMemo } from "react";
import {
  CategoryScale,
  Chart as ChartJS,
  LineElement,
  Legend,
  LinearScale,
  PointElement,
  Tooltip,
} from "chart.js";
import { Line } from "react-chartjs-2";

import type {
  CalibrationSnapshot,
  DemandForecastBundle,
  GridStatus,
  ProbabilityData,
} from "../types/dashboard";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend);

interface DemandForecastChartProps {
  gridStatus: GridStatus;
  probability: ProbabilityData;
  calibration?: CalibrationSnapshot | null;
  modelForecast?: DemandForecastBundle | null;
  theme?: "dark" | "light";
  view?: "day" | "nearTerm";
  className?: string;
  showHeader?: boolean;
  showSummary?: boolean;
}

export default function DemandForecastChart({
  gridStatus,
  probability,
  calibration = null,
  modelForecast = null,
  theme = "dark",
  view = "day",
  className = "",
  showHeader = true,
  showSummary = true,
}: DemandForecastChartProps) {
  const chartTextColor = theme === "light" ? "#334155" : "#cbd5e1";
  const chartGridColor =
    theme === "light" ? "rgba(71, 85, 105, 0.18)" : "rgba(148, 163, 184, 0.14)";
  const generationSeriesLabel =
    ["HistoricalScadaReplay", "HistoricalScadaSimulatedReplay"].includes(
      gridStatus.source_provider,
    )
      ? "Generation (TRA)"
      : "Current Generation Reference";
  const activeScenario = useMemo(() => {
    if (!calibration?.scenarios?.length) {
      return null;
    }
    return (
      calibration.scenarios.find((scenario) => scenario.scenario_key === calibration.selected_scenario_key) ??
      calibration.scenarios[0]
    );
  }, [calibration]);

  const dayEstimate = useMemo(() => {
    if (!activeScenario?.demand_curve?.length) {
      return null;
    }

    const points = [...activeScenario.demand_curve]
      .filter((point) => point.demand_mw != null && point.demand_mw > 0)
      .sort((left, right) => left.hour - right.hour);
    if (!points.length) {
      return null;
    }

    const selectedHour = calibration?.selected_hour ?? getTrinidadHour();
    const referencePoint = points.reduce((closest, point) =>
      circularHourDistance(point.hour, selectedHour) < circularHourDistance(closest.hour, selectedHour)
        ? point
        : closest,
    );
    const profileDemand = referencePoint.demand_mw ?? gridStatus.current_demand_mw;
    const scale = profileDemand > 0 ? gridStatus.current_demand_mw / profileDemand : 1;
    const currentIndex = points.findIndex((point) => point === referencePoint);
    const nextIndex = (currentIndex + 1) % points.length;

    return {
      labels: points.map((point) => formatHour(point.hour)),
      hours: points.map((point) => point.hour),
      estimatedDemand: points.map((point) =>
        Math.round((point.demand_mw ?? 0) * scale),
      ),
      currentIndex,
      nextIndex,
    };
  }, [activeScenario, calibration?.selected_hour, gridStatus.current_demand_mw]);

  const displayedDayEstimate = view === "day" ? dayEstimate : null;
  const validatedModelHorizons = useMemo(
    () =>
      [...(modelForecast?.horizons ?? [])]
        .filter(
          (horizon) =>
            horizon.forecast_demand_mw > 0 &&
            ["ML_ACTIVE", "BASELINE_ACTIVE"].some((status) =>
              horizon.quality_status.startsWith(status),
            ),
        )
        .sort((left, right) => left.horizon_hours - right.horizon_hours),
    [modelForecast],
  );
  const modelIsActive = validatedModelHorizons.some((horizon) =>
    horizon.quality_status.startsWith("ML_ACTIVE"),
  );
  const modelOverlay = useMemo(() => {
    if (!displayedDayEstimate || validatedModelHorizons.length === 0) {
      return null;
    }

    const data = displayedDayEstimate.estimatedDemand.map(() => null as number | null);
    data[displayedDayEstimate.currentIndex] = gridStatus.current_demand_mw;
    for (const horizon of validatedModelHorizons) {
      const targetHour = getTrinidadHourAt(horizon.forecast_timestamp);
      const targetIndex = displayedDayEstimate.hours.findIndex(
        (hour) => normalizeHour(hour) === targetHour,
      );
      if (targetIndex >= 0) {
        data[targetIndex] = horizon.forecast_demand_mw;
      }
    }

    return data.some(
      (value, index) =>
        index !== displayedDayEstimate.currentIndex && value !== null,
    )
      ? data
      : null;
  }, [displayedDayEstimate, gridStatus.current_demand_mw, validatedModelHorizons]);

  const chartConfig = useMemo(() => {
    if (displayedDayEstimate && activeScenario) {
      return {
        labels: displayedDayEstimate.labels,
        datasets: [
          {
            label: "Estimated Total Day Demand (MW)",
            data: displayedDayEstimate.estimatedDemand,
            borderColor: "rgba(34, 211, 238, 1)",
            backgroundColor: "rgba(34, 211, 238, 0.18)",
            borderWidth: 2,
            tension: 0.35,
            pointRadius: 2.5,
            yAxisID: "demand",
          },
          {
            label: generationSeriesLabel,
            data: displayedDayEstimate.estimatedDemand.map(
              () => gridStatus.current_generation_mw,
            ),
            borderColor: "rgba(52, 211, 153, 1)",
            backgroundColor: "rgba(52, 211, 153, 0.12)",
            borderWidth: 1.8,
            borderDash: [8, 5],
            pointRadius: 0,
            pointHoverRadius: 3,
            tension: 0,
            yAxisID: "demand",
          },
          {
            label: "Measured Current Demand",
            data: displayedDayEstimate.estimatedDemand.map((_, index) =>
              index === displayedDayEstimate.currentIndex ? gridStatus.current_demand_mw : null,
            ),
            borderColor: "rgba(255, 255, 255, 0)",
            backgroundColor: "rgba(255, 255, 255, 1)",
            pointBackgroundColor: "rgba(255, 255, 255, 1)",
            pointBorderColor: "rgba(8, 47, 73, 1)",
            pointBorderWidth: 2,
            pointRadius: 5,
            pointHoverRadius: 6,
            showLine: false,
            yAxisID: "demand",
          },
          {
            label: "60m Forecast",
            data: displayedDayEstimate.estimatedDemand.map((_, index) =>
              index === displayedDayEstimate.nextIndex ? probability.forecast_demand_60m : null,
            ),
            borderColor: "rgba(244, 114, 182, 0)",
            backgroundColor: "rgba(244, 114, 182, 1)",
            pointBackgroundColor: "rgba(244, 114, 182, 1)",
            pointBorderColor: "rgba(80, 7, 36, 1)",
            pointBorderWidth: 2,
            pointRadius: 5,
            pointHoverRadius: 6,
            showLine: false,
            yAxisID: "demand",
          },
          ...(modelOverlay
            ? [
                {
                  label: modelIsActive
                    ? "Validated ML Forecast"
                    : "Validated Baseline Forecast",
                  data: modelOverlay,
                  borderColor: "rgba(167, 139, 250, 1)",
                  backgroundColor: "rgba(167, 139, 250, 0.18)",
                  borderWidth: 2,
                  borderDash: [6, 4],
                  pointBackgroundColor: "rgba(196, 181, 253, 1)",
                  pointBorderColor: "rgba(76, 29, 149, 1)",
                  pointBorderWidth: 2,
                  pointRadius: 4,
                  pointHoverRadius: 6,
                  spanGaps: true,
                  yAxisID: "demand",
                },
              ]
            : []),
        ],
      };
    }

    return {
      labels: ["Current", "30m Forecast", "60m Forecast"],
      datasets: [
        {
          label: "Demand Forecast (MW)",
          data: [
            gridStatus.current_demand_mw,
            probability.forecast_demand_30m,
            probability.forecast_demand_60m,
          ],
          backgroundColor: [
            "rgba(34, 211, 238, 0.55)",
            "rgba(59, 130, 246, 0.55)",
            "rgba(244, 114, 182, 0.55)",
          ],
          borderColor: [
            "rgba(34, 211, 238, 1)",
            "rgba(59, 130, 246, 1)",
            "rgba(244, 114, 182, 1)",
          ],
          borderWidth: 1,
          yAxisID: "demand",
        },
        {
          label: generationSeriesLabel,
          data: [
            gridStatus.current_generation_mw,
            gridStatus.current_generation_mw,
            gridStatus.current_generation_mw,
          ],
          borderColor: "rgba(52, 211, 153, 1)",
          backgroundColor: "rgba(52, 211, 153, 0.12)",
          borderWidth: 1.8,
          borderDash: [8, 5],
          pointRadius: 0,
          pointHoverRadius: 3,
          tension: 0,
          yAxisID: "demand",
        },
      ],
    };
  }, [
    activeScenario,
    displayedDayEstimate,
    gridStatus.current_demand_mw,
    gridStatus.current_generation_mw,
    generationSeriesLabel,
    modelIsActive,
    modelOverlay,
    probability.forecast_demand_30m,
    probability.forecast_demand_60m,
  ]);

  const options = useMemo(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: true,
          position: "bottom" as const,
          labels: {
            color: chartTextColor,
            usePointStyle: true,
            pointStyle: "line",
            boxWidth: 14,
            padding: 8,
            font: {
              size: 9,
            },
          },
        },
      },
      scales: displayedDayEstimate
        ? {
            x: {
              ticks: {
                color: chartTextColor,
              },
              grid: {
                color: chartGridColor,
              },
            },
            demand: {
              type: "linear" as const,
              position: "left" as const,
              min: 700,
              max: 1500,
              ticks: {
                color: chartTextColor,
                stepSize: 100,
              },
              grid: {
                color: chartGridColor,
              },
            },
          }
        : {
            x: {
              ticks: {
                color: chartTextColor,
              },
              grid: {
                color: chartGridColor,
              },
            },
            demand: {
              type: "linear" as const,
              position: "left" as const,
              min: 700,
              max: 1500,
              ticks: {
                color: chartTextColor,
                stepSize: 100,
              },
              grid: {
                color: chartGridColor,
              },
            },
          },
    }),
    [chartGridColor, chartTextColor, displayedDayEstimate],
  );

  return (
    <div className={`flex h-full w-full min-w-0 flex-col rounded-2xl border border-cyan-500/15 bg-slate-900/80 p-2.5 shadow-[0_0_34px_rgba(8,145,178,0.08)] ${className}`}>
      {showHeader ? (
        <div className="mb-2 flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">
              Demand Forecast
            </p>
            <h2 className="mt-1 text-[0.98rem] font-semibold text-white">
              {displayedDayEstimate ? "Estimated Total Day Demand" : "Current and Near-Term Load"}
            </h2>
            {calibration?.selection_reason ? (
              <p className="mt-1 text-[11px] text-slate-400">
                {displayedDayEstimate
                  ? `${calibration.selection_reason} Profile shape is aligned to the live demand reading.`
                  : calibration.selection_reason}
              </p>
            ) : null}
          </div>
          <span className="rounded-full border border-slate-700 px-2.5 py-1 text-[11px] font-medium text-slate-300">
            {validatedModelHorizons.length > 0
              ? modelIsActive
                ? "ML forecast active"
                : "Validated baseline active"
              : displayedDayEstimate
                ? "Live-adjusted profile"
                : "Near-term only"}
          </span>
        </div>
      ) : null}

      <div className="min-h-[clamp(9rem,16vh,11rem)] flex-1 w-full min-w-0">
        <Line
          data={chartConfig}
          options={{
            ...options,
            elements: {
              line: {
                tension: 0.35,
                borderWidth: 2,
              },
              point: {
                radius: 4,
                hoverRadius: 6,
              },
            },
          }}
        />
      </div>

      {showSummary ? (
        <div className="mt-2 grid gap-2 sm:grid-cols-3">
          <div className="flex min-h-[3.25rem] flex-col items-center justify-center rounded-lg border border-slate-800 bg-slate-950/60 px-2.5 py-2 text-center shadow-inner shadow-black/20">
            <p className="text-[10px] uppercase tracking-[0.12em] text-slate-400">Current</p>
            <p className="mt-1 text-[0.86rem] font-semibold leading-tight text-white">
              {gridStatus.current_demand_mw.toFixed(0)} MW
            </p>
          </div>
          {(validatedModelHorizons.length > 0
            ? validatedModelHorizons.slice(0, 2).map((horizon) => ({
                label: `${horizon.horizon_hours}h ${modelIsActive ? "ML" : "Model"}`,
                value: `${horizon.forecast_demand_mw.toFixed(0)} MW`,
                detail: `+/- ${horizon.forecast_uncertainty_mw.toFixed(0)} MW`,
              }))
            : [
                {
                  label: "30m Estimate",
                  value: `${probability.forecast_demand_30m.toFixed(0)} MW`,
                  detail: "Operating forecast",
                },
                {
                  label: "60m Estimate",
                  value: `${probability.forecast_demand_60m.toFixed(0)} MW`,
                  detail: "Operating forecast",
                },
              ]).map((summary) => (
            <div key={summary.label} className="flex min-h-[3.25rem] flex-col items-center justify-center rounded-lg border border-slate-800 bg-slate-950/60 px-2.5 py-2 text-center shadow-inner shadow-black/20">
              <p className="text-[10px] uppercase tracking-[0.12em] text-slate-400">{summary.label}</p>
              <p className="mt-1 text-[0.86rem] font-semibold leading-tight text-white">{summary.value}</p>
              <p className="mt-0.5 text-[9px] text-slate-500">{summary.detail}</p>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function getTrinidadHour(): number {
  const hour = new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    hour12: false,
    timeZone: "America/Port_of_Spain",
  }).formatToParts(new Date()).find((part) => part.type === "hour")?.value;
  const parsed = Number(hour);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 24;
}

function getTrinidadHourAt(timestamp: string): number {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return -1;
  }
  const hour = new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    hour12: false,
    timeZone: "America/Port_of_Spain",
  }).formatToParts(date).find((part) => part.type === "hour")?.value;
  return normalizeHour(Number(hour));
}

function normalizeHour(hour: number): number {
  return Number.isFinite(hour) ? hour % 24 : -1;
}

function circularHourDistance(left: number, right: number): number {
  const distance = Math.abs(left - right);
  return Math.min(distance, 24 - distance);
}

function formatHour(hour: number): string {
  const normalized = hour % 24;
  const suffix = normalized >= 12 ? "PM" : "AM";
  const displayHour = normalized % 12 || 12;
  return `${displayHour} ${suffix}`;
}
