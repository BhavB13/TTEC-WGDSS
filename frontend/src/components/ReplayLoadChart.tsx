import { useMemo } from "react";
import {
  CategoryScale,
  Chart as ChartJS,
  Filler,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
} from "chart.js";
import { Line } from "react-chartjs-2";

import type { ReplayDashboard } from "../types/dashboard";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip);

export default function ReplayLoadChart({
  replay,
  theme = "dark",
  compact = false,
}: {
  replay: ReplayDashboard;
  theme?: "dark" | "light";
  compact?: boolean;
}) {
  const text = theme === "light" ? "#334155" : "#cbd5e1";
  const grid = theme === "light" ? "rgba(71,85,105,.16)" : "rgba(148,163,184,.12)";
  const points = replay.full_day_load_forecast;
  const usesTraGeneration = replay.status.mode === "historical_replay";
  const generationSeriesLabel = usesTraGeneration
    ? "Generation (TRA)"
    : "Revealed generation";
  const { revealedGeneration, revealedSystemSpin } = useMemo(() => {
    const operationsByTimestamp = new Map(
      replay.operational_history.map((point) => [
        new Date(point.timestamp).getTime(),
        point,
      ]),
    );
    return {
      revealedGeneration: points.map(
        (point) =>
          operationsByTimestamp.get(new Date(point.timestamp).getTime())
            ?.generation_mw ?? null,
      ),
      revealedSystemSpin: points.map(
        (point) =>
          operationsByTimestamp.get(new Date(point.timestamp).getTime())
            ?.spinning_reserve_mw ?? null,
      ),
    };
  }, [points, replay.operational_history]);
  const hasRevealedGeneration = revealedGeneration.some(
    (value) => value !== null,
  );

  const data = useMemo(() => {
    return {
      labels: points.map((point) => formatHour(point.timestamp)),
      datasets: [
        {
          label: "Forecast lower bound",
          data: points.map((point) => point.forecast_demand_mw - point.uncertainty_mw),
          borderColor: "rgba(34,211,238,.2)",
          backgroundColor: "rgba(34,211,238,.08)",
          borderWidth: 0.8,
          pointRadius: 0,
          tension: 0.3,
        },
        {
          label: "Forecast uncertainty",
          data: points.map((point) => point.forecast_demand_mw + point.uncertainty_mw),
          borderColor: "rgba(34,211,238,.2)",
          backgroundColor: "rgba(34,211,238,.08)",
          fill: "-1",
          borderWidth: 0.8,
          pointRadius: 0,
          tension: 0.3,
        },
        {
          label: "Forecast demand",
          data: points.map((point) => point.forecast_demand_mw),
          borderColor: "#22d3ee",
          backgroundColor: "rgba(34,211,238,.10)",
          fill: true,
          borderWidth: 2,
          pointRadius: compact ? 0 : 1.8,
          pointHoverRadius: 5,
          pointHitRadius: 14,
          tension: 0.3,
        },
        {
          label: "Historical hourly average",
          data: points.map((point) => point.historical_average_mw),
          borderColor: "#64748b",
          borderDash: [5, 4],
          borderWidth: 1.5,
          pointRadius: 0,
          pointHoverRadius: 4,
          pointHitRadius: 14,
          tension: 0.3,
        },
        {
          label: "Revealed actual",
          data: points.map((point) => point.actual_demand_mw ?? null),
          borderColor: "#34d399",
          backgroundColor: "#34d399",
          borderWidth: 2.5,
          pointRadius: 2,
          pointHoverRadius: 5,
          pointHitRadius: 14,
          spanGaps: false,
          tension: 0.2,
        },
        ...(hasRevealedGeneration
          ? [
              {
                label: generationSeriesLabel,
                data: revealedGeneration,
                borderColor: "#fbbf24",
                backgroundColor: "#fbbf24",
                borderWidth: 2.2,
                borderDash: [7, 4],
                pointRadius: compact ? 0 : 2,
                pointHoverRadius: 5,
                pointHitRadius: 14,
                spanGaps: false,
                tension: 0.2,
              },
            ]
          : []),
      ],
    };
  }, [compact, generationSeriesLabel, hasRevealedGeneration, points, revealedGeneration]);

  return (
    <section className="flex h-full min-h-0 w-full min-w-0 flex-col rounded-2xl border border-cyan-500/15 bg-slate-900/80 p-2.5 shadow-[0_0_34px_rgba(8,145,178,0.08)]">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">Full-Day Load Forecast</p>
          <h2 className="mt-0.5 text-sm font-semibold text-white">
            {usesTraGeneration
              ? "Demand forecast with revealed demand and TRA"
              : "Demand forecast with revealed demand and generation"}
          </h2>
          <p className="mt-0.5 text-[9px] text-slate-400">
            {replay.summary.forecast_model} · MAE {replay.summary.forecast_mae_mw.toFixed(1)} MW · {replay.summary.training_rows} prior rows
          </p>
        </div>
        <span className="rounded-full border border-cyan-500/25 bg-cyan-500/10 px-2 py-1 text-[9px] font-semibold text-cyan-100">
          Peak {replay.summary.current_day_peak_forecast_mw.toFixed(0)} MW
        </span>
      </div>
      <ChartKey
        generationLabel={usesTraGeneration ? "Generation (TRA)" : "Generation output"}
        showGeneration={hasRevealedGeneration}
      />
      <div className="mt-1 min-h-[12rem] flex-1 cursor-crosshair">
        <Line
          data={data}
          options={{
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            interaction: { mode: "index", intersect: false, axis: "x" },
            hover: { mode: "index", intersect: false },
            plugins: {
              legend: {
                display: false,
              },
              tooltip: {
                enabled: true,
                mode: "index",
                intersect: false,
                position: "nearest",
                backgroundColor: theme === "light" ? "rgba(255,255,255,.98)" : "rgba(2,6,23,.97)",
                titleColor: theme === "light" ? "#0f172a" : "#f8fafc",
                bodyColor: theme === "light" ? "#334155" : "#e2e8f0",
                borderColor: theme === "light" ? "rgba(8,145,178,.35)" : "rgba(34,211,238,.35)",
                borderWidth: 1,
                cornerRadius: 8,
                padding: 12,
                caretPadding: 8,
                titleMarginBottom: 8,
                bodySpacing: 5,
                displayColors: true,
                boxWidth: 10,
                boxHeight: 10,
                filter: (context) =>
                  context.dataset.label !== "Forecast lower bound" &&
                  context.dataset.label !== "Forecast uncertainty",
                callbacks: {
                  title: (items) => {
                    const point = points[items[0]?.dataIndex ?? 0];
                    return point ? formatTooltipTimestamp(point.timestamp) : "";
                  },
                  label: (context) => {
                    const labels: Record<string, string> = {
                      "Forecast demand": "Forecast demand",
                      "Historical hourly average": "Historical average",
                      "Revealed actual": "Actual demand",
                      "Revealed generation": "Generation output",
                      "Generation (TRA)": "Generation (TRA)",
                    };
                    const label = labels[context.dataset.label ?? ""] ?? context.dataset.label;
                    return `${label}: ${formatMegawatts(Number(context.raw))}`;
                  },
                  afterLabel: (context) => {
                    if (context.dataset.label !== "Forecast demand") {
                      return [];
                    }
                    const point = points[context.dataIndex];
                    if (!point) {
                      return [];
                    }
                    return [
                      `90% forecast range: ${formatMegawatts(point.forecast_demand_mw - point.uncertainty_mw)} to ${formatMegawatts(point.forecast_demand_mw + point.uncertainty_mw)}`,
                    ];
                  },
                  afterBody: (items) => {
                    const index = items[0]?.dataIndex ?? 0;
                    const point = points[index];
                    if (!point) {
                      return [];
                    }

                    const generation = revealedGeneration[index];
                    const systemSpin = revealedSystemSpin[index];
                    const comparisonDemand = point.actual_demand_mw ?? point.forecast_demand_mw;
                    const details = [
                      "",
                      `Weather adjustment: ${formatSignedMegawatts(point.weather_impact_mw, 1)}`,
                      `Weather confidence: ${(point.weather_confidence * 100).toFixed(0)}% - ${formatSourceCount(point.weather_source_count)}`,
                    ];
                    if (generation !== null) {
                      const rawGap = generation - comparisonDemand;
                      details.push(
                        `${usesTraGeneration ? "TRA-demand gap" : "Generation balance"}: ${formatSignedMegawatts(rawGap)}`,
                      );
                      if (systemSpin !== null) {
                        details.push(
                          `System spin (corrected): ${formatMegawatts(systemSpin)}`,
                          `Spin adjustment: ${formatSignedMegawatts(systemSpin - rawGap)}`,
                        );
                      }
                    }
                    return details;
                  },
                },
              },
            },
            scales: {
              x: { ticks: { color: text, maxTicksLimit: 12, font: { size: 9 } }, grid: { color: grid } },
              y: { min: 650, max: 1500, ticks: { color: text, callback: (value) => `${value} MW`, font: { size: 9 } }, grid: { color: grid } },
            },
          }}
        />
      </div>
    </section>
  );
}

function ChartKey({
  generationLabel,
  showGeneration,
}: {
  generationLabel: string;
  showGeneration: boolean;
}) {
  return (
    <div
      aria-label="Load forecast chart key"
      className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-slate-700/50 pt-1.5 text-[10px] font-medium text-slate-300"
    >
      <ChartKeyItem label="90% forecast range" variant="band" />
      <ChartKeyItem label="Forecast demand" variant="forecast" />
      <ChartKeyItem label="Historical average" variant="historical" />
      <ChartKeyItem label="Actual demand" variant="actual" />
      {showGeneration ? (
        <ChartKeyItem label={generationLabel} variant="generation" />
      ) : null}
    </div>
  );
}

function ChartKeyItem({
  label,
  variant,
}: {
  label: string;
  variant: "band" | "forecast" | "historical" | "actual" | "generation";
}) {
  const indicatorClass = {
    band: "h-2.5 border border-cyan-400/40 bg-cyan-400/10",
    forecast: "h-0 border-t-2 border-cyan-400",
    historical: "h-0 border-t-2 border-dashed border-slate-500",
    actual: "h-0 border-t-[3px] border-emerald-400",
    generation: "h-0 border-t-[3px] border-dashed border-amber-400",
  }[variant];

  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <span aria-hidden="true" className={`w-4 shrink-0 ${indicatorClass}`} />
      <span>{label}</span>
    </span>
  );
}

function formatHour(value: string): string {
  return new Intl.DateTimeFormat("en-TT", {
    hour: "numeric",
    hour12: true,
    timeZone: "America/Port_of_Spain",
  }).format(new Date(value));
}

function formatTooltipTimestamp(value: string): string {
  return new Intl.DateTimeFormat("en-TT", {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
    timeZone: "America/Port_of_Spain",
    timeZoneName: "short",
  }).format(new Date(value));
}

function formatMegawatts(value: number): string {
  return `${Math.round(value).toLocaleString("en-TT")} MW`;
}

function formatSignedMegawatts(value: number, fractionDigits = 0): string {
  const precision = 10 ** fractionDigits;
  const rounded = Math.round(value * precision) / precision;
  const normalized = Object.is(rounded, -0) ? 0 : rounded;
  return `${normalized >= 0 ? "+" : ""}${normalized.toLocaleString("en-TT", {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  })} MW`;
}

function formatSourceCount(count: number): string {
  return `${count} ${count === 1 ? "source" : "sources"}`;
}
