import { useMemo } from "react";
import {
  CategoryScale,
  Chart as ChartJS,
  Filler,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
  type ChartOptions,
} from "chart.js";
import { Line } from "react-chartjs-2";

import type {
  CapacityPlan,
  ProbabilityData,
  RiskHorizon,
} from "../types/dashboard";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
);

interface RiskTimelineChartProps {
  probability: ProbabilityData;
  capacityPlan?: CapacityPlan | null;
  theme?: "dark" | "light";
  className?: string;
}

export default function RiskTimelineChart({
  probability,
  capacityPlan = null,
  theme = "dark",
  className = "",
}: RiskTimelineChartProps) {
  const profile = useMemo(
    () =>
      [...(probability.risk_profile ?? [])]
        .filter(
          (point) =>
            point.horizon_minutes > 0 &&
            point.horizon_minutes <= 360 &&
            Number.isFinite(point.probability) &&
            Number.isFinite(point.forecast_tra_mw) &&
            Number.isFinite(point.projected_reserve_mw),
        )
        .sort((left, right) => left.horizon_minutes - right.horizon_minutes),
    [probability.risk_profile],
  );
  const textColor = theme === "light" ? "#334155" : "#cbd5e1";
  const gridColor =
    theme === "light" ? "rgba(71,85,105,0.16)" : "rgba(148,163,184,0.13)";
  const labels = profile.map(formatHorizon);
  const planByHorizon = useMemo(
    () =>
      new Map(
        (capacityPlan?.profile ?? []).map((point) => [
          point.horizon_minutes,
          point,
        ]),
      ),
    [capacityPlan?.profile],
  );
  const showPlanned = Boolean(
    capacityPlan?.evaluated_actions.some(
      (action) => action.applied_to_projection,
    ),
  );
  const chartData = useMemo(
    () => ({
      labels,
      datasets: [
        {
          label: "_lower",
          data: profile.map((point) => point.forecast_lower_mw),
          borderColor: "rgba(34,211,238,0)",
          backgroundColor: "rgba(34,211,238,0)",
          borderWidth: 0,
          pointRadius: 0,
          tension: 0.25,
          yAxisID: "demand",
        },
        {
          label: "Demand uncertainty",
          data: profile.map((point) => point.forecast_upper_mw),
          borderColor: "rgba(34,211,238,0.22)",
          backgroundColor: "rgba(34,211,238,0.13)",
          borderWidth: 1,
          pointRadius: 0,
          fill: "-1",
          tension: 0.25,
          yAxisID: "demand",
        },
        {
          label: "Forecast demand",
          data: profile.map((point) => point.forecast_demand_mw),
          borderColor: "#22d3ee",
          backgroundColor: "#22d3ee",
          borderWidth: 2.5,
          pointRadius: 3,
          pointHoverRadius: 5,
          tension: 0.25,
          yAxisID: "demand",
        },
        {
          label: "Current TRA held",
          data: profile.map(
            (point) =>
              planByHorizon.get(point.horizon_minutes)?.baseline_tra_mw ??
              point.forecast_tra_mw,
          ),
          borderColor: "#fbbf24",
          backgroundColor: "#fbbf24",
          borderWidth: 2,
          borderDash: [7, 5],
          pointRadius: 2,
          pointHoverRadius: 4,
          tension: 0.15,
          yAxisID: "demand",
        },
        ...(showPlanned
          ? [
              {
                label: "TRA after proposed starts",
                data: profile.map(
                  (point) =>
                    planByHorizon.get(point.horizon_minutes)?.planned_tra_mw ??
                    point.forecast_tra_mw,
                ),
                borderColor: "#c084fc",
                backgroundColor: "#c084fc",
                borderWidth: 2.2,
                stepped: "after" as const,
                pointRadius: 2,
                pointHoverRadius: 4,
                yAxisID: "demand",
              },
            ]
          : []),
        {
          label: "No-action reserve",
          data: profile.map(
            (point) =>
              planByHorizon.get(point.horizon_minutes)?.baseline_reserve_mw ??
              point.projected_reserve_mw,
          ),
          borderColor: "#34d399",
          backgroundColor: "#34d399",
          borderWidth: 2,
          pointRadius: 3,
          pointHoverRadius: 5,
          tension: 0.2,
          yAxisID: "reserve",
        },
        ...(showPlanned
          ? [
              {
                label: "Post-plan reserve",
                data: profile.map(
                  (point) =>
                    planByHorizon.get(point.horizon_minutes)?.planned_reserve_mw ??
                    point.projected_reserve_mw,
                ),
                borderColor: "#a78bfa",
                backgroundColor: "#a78bfa",
                borderWidth: 2,
                pointRadius: 2,
                pointHoverRadius: 4,
                tension: 0.2,
                yAxisID: "reserve",
              },
            ]
          : []),
        {
          label: "Required reserve",
          data: profile.map((point) => point.required_reserve_mw),
          borderColor: "#fb7185",
          backgroundColor: "#fb7185",
          borderWidth: 1.7,
          borderDash: [4, 4],
          pointRadius: 0,
          tension: 0,
          yAxisID: "reserve",
        },
      ],
    }),
    [labels, planByHorizon, profile, showPlanned],
  );
  const options = useMemo<ChartOptions<"line">>(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: "index", intersect: false },
      layout: { padding: { top: 2, right: 4, bottom: 0, left: 0 } },
      plugins: {
        legend: {
          display: false,
        },
        tooltip: {
          backgroundColor: "rgba(2,6,23,0.96)",
          borderColor: "rgba(34,211,238,0.3)",
          borderWidth: 1,
          titleColor: "#f8fafc",
          bodyColor: "#e2e8f0",
          padding: 10,
          filter: (item) => item.dataset.label !== "_lower",
          callbacks: {
            title: (items) => {
              const point = profile[items[0]?.dataIndex ?? 0];
              return point ? formatPointTime(point) : "Risk horizon";
            },
            label: (context) => {
              const point = profile[context.dataIndex];
              if (!point) return "";
              const datasetLabel = context.dataset.label;
              const planPoint = planByHorizon.get(point.horizon_minutes);
              if (datasetLabel === "Demand uncertainty") {
                const confidenceLevel = Math.round(
                  (point.confidence_level ?? 0.9) * 100,
                );
                return `${confidenceLevel}% demand range: ${point.forecast_lower_mw.toFixed(1)}-${point.forecast_upper_mw.toFixed(1)} MW`;
              }
              if (datasetLabel === "Forecast demand") {
                return `Forecast demand: ${point.forecast_demand_mw.toFixed(1)} MW`;
              }
              if (datasetLabel === "Current TRA held") {
                return `Current TRA held: ${(planPoint?.baseline_tra_mw ?? point.forecast_tra_mw).toFixed(1)} MW`;
              }
              if (datasetLabel === "TRA after proposed starts") {
                return `TRA after proposed starts: ${(planPoint?.planned_tra_mw ?? point.forecast_tra_mw).toFixed(1)} MW`;
              }
              if (datasetLabel === "No-action reserve") {
                return [
                  `No-action reserve: ${(planPoint?.baseline_reserve_mw ?? point.projected_reserve_mw).toFixed(1)} MW`,
                  `Generation need without action: ${(planPoint?.baseline_capacity_risk_percent ?? point.capacity_risk_percent).toFixed(1)}%`,
                ];
              }
              if (datasetLabel === "Post-plan reserve") {
                return [
                  `Post-plan reserve: ${(planPoint?.planned_reserve_mw ?? point.projected_reserve_mw).toFixed(1)} MW`,
                  `Post-plan risk: ${(planPoint?.planned_capacity_risk_percent ?? point.capacity_risk_percent).toFixed(1)}%`,
                ];
              }
              const balance = (planPoint?.planned_reserve_surplus_mw ?? point.reserve_surplus_mw) >= 0
                ? `Surplus: +${(planPoint?.planned_reserve_surplus_mw ?? point.reserve_surplus_mw).toFixed(1)} MW`
                : `Deficit: ${(planPoint?.planned_reserve_deficit_mw ?? point.reserve_deficit_mw).toFixed(1)} MW`;
              return [
                `Required reserve: ${point.required_reserve_mw.toFixed(1)} MW`,
                balance,
              ];
            },
          },
        },
      },
      scales: {
        x: {
          grid: { color: gridColor },
          ticks: { color: textColor, font: { size: 10 } },
        },
        demand: {
          position: "left",
          grid: { color: gridColor },
          ticks: {
            color: textColor,
            font: { size: 10 },
            callback: (value) => `${Number(value).toFixed(0)} MW`,
          },
        },
        reserve: {
          position: "right",
          grid: { drawOnChartArea: false },
          ticks: {
            color: "#6ee7b7",
            font: { size: 9 },
            callback: (value) => `${Number(value).toFixed(0)} MW`,
          },
        },
      },
    }),
    [gridColor, planByHorizon, profile, textColor],
  );

  return (
    <section
      className={`flex h-full min-h-0 w-full min-w-0 flex-col overflow-hidden rounded-2xl border border-cyan-500/15 bg-slate-900/80 p-3 shadow-[0_0_34px_rgba(8,145,178,0.08)] ${className}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-cyan-300">
            Six-Hour Capacity Outlook
          </p>
          <h2 className="mt-0.5 text-sm font-semibold leading-tight text-white">
            Demand, TRA and reserve trajectory
          </h2>
        </div>
        <span className="shrink-0 rounded-full border border-cyan-400/25 bg-cyan-500/10 px-2 py-1 text-[9px] font-semibold text-cyan-100">
          {capacityPlan?.status === "AVAILABLE"
            ? `Risk ${capacityPlan.baseline_peak_risk_percent.toFixed(1)}% -> ${capacityPlan.post_plan_peak_risk_percent.toFixed(1)}%`
            : `Peak ${formatPeakHorizon(probability.peak_risk_horizon_minutes)}`}
        </span>
      </div>

      <div className="mt-1.5 flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 border-y border-slate-800/80 py-1 text-[9px] text-slate-400">
        <TimelineLegend swatch="bg-cyan-400" label="Forecast demand" />
        <TimelineLegend
          swatch="border border-cyan-400/45 bg-cyan-400/10"
          label="90% range"
        />
        <TimelineLegend
          swatch="border-t-2 border-dashed border-amber-400"
          label="Current TRA"
        />
        {showPlanned ? (
          <TimelineLegend swatch="bg-violet-400" label="TRA with starts" />
        ) : null}
        <TimelineLegend swatch="bg-emerald-400" label="Reserve" />
        <TimelineLegend
          swatch="border-t-2 border-dashed border-rose-400"
          label="Reserve target"
        />
      </div>

      {profile.length ? (
        <div className="mt-1.5 min-h-[4.25rem] flex-1">
          <Line data={chartData} options={options} />
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 items-center justify-center rounded-xl border border-dashed border-slate-700 bg-slate-950/40 p-4 text-center text-sm text-slate-400">
          Per-horizon capacity-risk evidence is unavailable for this snapshot.
        </div>
      )}
    </section>
  );
}

function TimelineLegend({ swatch, label }: { swatch: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <span className={`h-1.5 w-4 shrink-0 ${swatch}`} aria-hidden="true" />
      <span>{label}</span>
    </span>
  );
}

function formatHorizon(point: RiskHorizon): string {
  if (point.horizon_minutes < 60) return `+${point.horizon_minutes}m`;
  const hours = point.horizon_minutes / 60;
  return Number.isInteger(hours) ? `+${hours}h` : `+${hours.toFixed(1)}h`;
}

function formatPeakHorizon(minutes?: number | null): string {
  if (minutes == null) return "--";
  return minutes < 60 ? `+${minutes}m` : `+${minutes / 60}h`;
}

function formatPointTime(point: RiskHorizon): string {
  if (!point.forecast_timestamp) return formatHorizon(point);
  const date = new Date(point.forecast_timestamp);
  if (Number.isNaN(date.getTime())) return formatHorizon(point);
  return `${formatHorizon(point)} - ${new Intl.DateTimeFormat("en-TT", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/Port_of_Spain",
  }).format(date)}`;
}
