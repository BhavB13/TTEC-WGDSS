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

import type { CalibrationScenario } from "../types/dashboard";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend);

interface ScenarioComparisonChartProps {
  scenarios: CalibrationScenario[];
  selectedScenarioKey?: string | null;
  className?: string;
}

const PALETTE: Record<string, { border: string; background: string }> = {
  hot: {
    border: "rgba(244, 114, 182, 1)",
    background: "rgba(244, 114, 182, 0.18)",
  },
  typical: {
    border: "rgba(34, 211, 238, 1)",
    background: "rgba(34, 211, 238, 0.18)",
  },
  rainy: {
    border: "rgba(96, 165, 250, 1)",
    background: "rgba(96, 165, 250, 0.18)",
  },
};

export default function ScenarioComparisonChart({
  scenarios,
  selectedScenarioKey,
  className = "",
}: ScenarioComparisonChartProps) {
  const { data, options } = useMemo(() => {
    const labels = Array.from({ length: 24 }, (_, index) => `${index + 1}:00`);
    return {
      data: {
        labels,
        datasets: scenarios.map((scenario) => {
          const palette = PALETTE[scenario.scenario_key] ?? {
            border: "rgba(148, 163, 184, 1)",
            background: "rgba(148, 163, 184, 0.16)",
          };
          return {
            label: scenario.scenario_label,
            data: labels.map((_, index) => {
              const point = scenario.demand_curve.find((entry) => entry.hour === index + 1);
              return point?.demand_mw ?? null;
            }),
            borderColor: palette.border,
            backgroundColor: palette.background,
            borderWidth: scenario.scenario_key === selectedScenarioKey ? 3 : 2,
            pointRadius: scenario.scenario_key === selectedScenarioKey ? 3.5 : 2.5,
            tension: 0.35,
            fill: false,
          };
        }),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: true,
            position: "bottom" as const,
            labels: {
              color: "#cbd5e1",
              usePointStyle: true,
              pointStyle: "line",
              boxWidth: 12,
            },
          },
        },
        scales: {
          x: {
            ticks: {
              color: "#cbd5e1",
              maxRotation: 0,
              autoSkip: true,
            },
            grid: {
              color: "rgba(148, 163, 184, 0.1)",
            },
          },
          y: {
            min: 700,
            max: 1500,
            ticks: {
              color: "#cbd5e1",
              stepSize: 100,
            },
            grid: {
              color: "rgba(148, 163, 184, 0.12)",
            },
          },
        },
      },
    };
  }, [scenarios, selectedScenarioKey]);

  if (scenarios.length === 0) {
    return (
      <div className={`flex h-full min-h-0 w-full items-center justify-center rounded-2xl border border-slate-800 bg-slate-950/50 p-4 text-sm text-slate-400 ${className}`}>
        Calibration profiles are unavailable.
      </div>
    );
  }

  return (
    <div className={`flex h-full w-full min-w-0 flex-col rounded-2xl border border-cyan-500/15 bg-slate-900/80 p-3 shadow-[0_0_34px_rgba(8,145,178,0.08)] ${className}`}>
      <div className="mb-2 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">
            Calibration Profiles
          </p>
          <h2 className="mt-1 text-[0.98rem] font-semibold leading-tight text-white">
            Hot, Typical, and Rainy Demand Curves
          </h2>
        </div>
        <span className="rounded-full border border-slate-700 bg-slate-950/60 px-2.5 py-1 text-[11px] font-medium text-slate-300">
          24h Comparison
        </span>
      </div>

      <div className="min-h-[14rem] flex-1 w-full min-w-0">
        <Line data={data} options={options} />
      </div>
    </div>
  );
}
