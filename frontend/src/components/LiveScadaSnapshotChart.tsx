import { useMemo } from "react";
import {
  CategoryScale,
  Chart as ChartJS,
  Filler,
  Legend,
  LineElement,
  LinearScale,
  PointElement,
  Tooltip,
} from "chart.js";
import { Line } from "react-chartjs-2";

import type {
  ExperimentalForecastPoint,
  SnapshotHourlyPoint,
} from "../types/liveScadaExperiment";


ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
);

interface LiveScadaSnapshotChartProps {
  observed: SnapshotHourlyPoint[];
  forecast: ExperimentalForecastPoint[];
  boundary?: string | null;
  isModelForecast: boolean;
}

export default function LiveScadaSnapshotChart({
  observed,
  forecast,
  boundary,
  isModelForecast,
}: LiveScadaSnapshotChartProps) {
  const chart = useMemo(() => {
    const observedPoints = [...observed].sort(
      (left, right) =>
        new Date(left.timestamp).getTime() - new Date(right.timestamp).getTime(),
    );
    const forecastPoints = [...forecast].sort(
      (left, right) =>
        new Date(left.forecast_timestamp).getTime() -
        new Date(right.forecast_timestamp).getTime(),
    );
    const labels = [
      ...observedPoints.map((point) => point.available_at),
      ...forecastPoints.map((point) => point.forecast_timestamp),
    ];
    const observedLength = observedPoints.length;
    const forecastPrefix = Array<number | null>(Math.max(0, observedLength - 1)).fill(
      null,
    );
    const boundaryDemand =
      observedPoints.at(-1)?.demand_mw ?? forecastPoints.at(0)?.forecast_demand_mw ?? null;

    return {
      labels: labels.map(formatChartTime),
      datasets: [
        {
          label: "Observed demand",
          data: [
            ...observedPoints.map((point) => point.demand_mw),
            ...forecastPoints.map(() => null),
          ],
          borderColor: "#34d399",
          backgroundColor: "rgba(52, 211, 153, 0.08)",
          pointBackgroundColor: "#34d399",
          pointRadius: 2.5,
          borderWidth: 2.5,
          tension: 0.25,
          spanGaps: false,
        },
        {
          label: "Observed generation (TRA)",
          data: [
            ...observedPoints.map((point) => point.generation_tra_mw),
            ...forecastPoints.map(() => null),
          ],
          borderColor: "#fbbf24",
          pointBackgroundColor: "#fbbf24",
          pointRadius: 2,
          borderWidth: 2,
          tension: 0.2,
          spanGaps: false,
        },
        {
          label: isModelForecast ? "Demand forecast" : "Persistence reference",
          data: [
            ...forecastPrefix,
            boundaryDemand,
            ...forecastPoints.map((point) => point.forecast_demand_mw),
          ],
          borderColor: "#22d3ee",
          pointBackgroundColor: "#22d3ee",
          pointRadius: 3,
          borderWidth: 2.5,
          borderDash: [7, 5],
          tension: 0.25,
          spanGaps: false,
        },
        {
          label: "SCADA temperature",
          data: [
            ...observedPoints.map((point) => point.temperature_c),
            ...forecastPoints.map(() => null),
          ],
          borderColor: "#fb7185",
          pointBackgroundColor: "#fb7185",
          pointRadius: 2,
          borderWidth: 1.8,
          tension: 0.25,
          yAxisID: "temperature",
          spanGaps: false,
        },
      ],
    };
  }, [forecast, isModelForecast, observed]);

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/65 p-3">
      <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-cyan-300">
            Imported SCADA timeline
          </p>
          <p className="mt-1 text-sm text-slate-300">
            Hourly overlap-weighted demand, TRA, and ambient temperature
          </p>
        </div>
        <div className="text-right text-[10px] uppercase tracking-wider">
          <p className="text-emerald-300">Alignment validated</p>
          <p className="mt-1 text-amber-300">Forecast accuracy pending later actuals</p>
        </div>
      </div>
      <div className="h-[clamp(15rem,34vh,21rem)] min-h-0 w-full min-w-0">
        <Line
          data={chart}
          options={{
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: "index", intersect: false },
            plugins: {
              legend: {
                position: "top",
                align: "start",
                labels: {
                  color: "#cbd5e1",
                  boxWidth: 22,
                  boxHeight: 3,
                  usePointStyle: true,
                  pointStyle: "line",
                  padding: 14,
                },
              },
              tooltip: {
                backgroundColor: "rgba(2, 6, 23, 0.96)",
                titleColor: "#f8fafc",
                bodyColor: "#e2e8f0",
                borderColor: "rgba(34, 211, 238, 0.35)",
                borderWidth: 1,
                callbacks: {
                  label(context) {
                    const value = context.parsed.y;
                    if (value == null) return "";
                    const suffix =
                      context.dataset.yAxisID === "temperature" ? "°C" : " MW";
                    return `${context.dataset.label}: ${value.toFixed(1)}${suffix}`;
                  },
                },
              },
            },
            scales: {
              x: {
                grid: { color: "rgba(148, 163, 184, 0.10)" },
                ticks: { color: "#94a3b8", maxRotation: 0, autoSkip: true },
                title: {
                  display: true,
                  text: boundary
                    ? `Observed boundary: ${formatBoundary(boundary)}`
                    : "Snapshot time (AST)",
                  color: "#64748b",
                },
              },
              y: {
                position: "left",
                grid: { color: "rgba(148, 163, 184, 0.12)" },
                ticks: {
                  color: "#cbd5e1",
                  callback: (value) => `${value} MW`,
                },
                title: { display: true, text: "Power (MW)", color: "#94a3b8" },
              },
              temperature: {
                position: "right",
                grid: { drawOnChartArea: false },
                ticks: {
                  color: "#fb7185",
                  callback: (value) => `${value}°C`,
                },
                title: {
                  display: true,
                  text: "Temperature",
                  color: "#fb7185",
                },
              },
            },
          }}
        />
      </div>
    </div>
  );
}

function formatChartTime(value: string): string {
  return new Intl.DateTimeFormat("en-TT", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/Port_of_Spain",
  }).format(new Date(value));
}

function formatBoundary(value: string): string {
  return new Intl.DateTimeFormat("en-TT", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/Port_of_Spain",
  }).format(new Date(value));
}
