import type { CapacityStatus, ProbabilityData } from "../types/dashboard";

interface ProbabilityGaugeProps {
  probability: ProbabilityData;
  className?: string;
}

const RADIUS = 46;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

function statusPalette(status: CapacityStatus) {
  switch (status) {
    case "Add Generation":
      return {
        ring: "stroke-rose-400",
        badge: "border-rose-500/40 bg-rose-500/10 text-rose-100",
      };
    case "Prepare Generation":
      return {
        ring: "stroke-orange-400",
        badge: "border-orange-500/40 bg-orange-500/10 text-orange-100",
      };
    case "Watch":
      return {
        ring: "stroke-amber-400",
        badge: "border-amber-500/40 bg-amber-500/10 text-amber-100",
      };
    case "Normal":
      return {
        ring: "stroke-emerald-400",
        badge: "border-emerald-500/40 bg-emerald-500/10 text-emerald-100",
      };
    default:
      return {
        ring: "stroke-slate-500",
        badge: "border-slate-500/40 bg-slate-500/10 text-slate-200",
      };
  }
}

export default function ProbabilityGauge({
  probability,
  className = "",
}: ProbabilityGaugeProps) {
  const available =
    probability.risk_level !== "UNAVAILABLE" &&
    probability.capacity_status !== "Unavailable";
  const riskPercent = Math.max(
    0,
    Math.min(
      100,
      Number.isFinite(probability.capacity_risk_percent)
        ? probability.capacity_risk_percent
        : probability.probability_score * 100,
    ),
  );
  const progress = CIRCUMFERENCE - (riskPercent / 100) * CIRCUMFERENCE;
  const palette = statusPalette(probability.capacity_status);
  const reserveTarget = probability.required_reserve_mw ?? 30;
  const peakHorizon = formatRiskHorizon(probability.peak_risk_horizon_minutes);

  return (
    <div
      className={`flex h-full min-h-0 w-full min-w-0 flex-col overflow-hidden rounded-2xl border border-cyan-500/15 bg-slate-900/80 p-2.5 shadow-[0_0_34px_rgba(8,145,178,0.08)] ${className}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-cyan-300">
            Generation Need
          </p>
          <h2 className="mt-0.5 text-[0.82rem] font-semibold leading-tight text-white">
            No-action exposure
          </h2>
        </div>
        <span
          className={`max-w-[7rem] shrink-0 rounded-full border px-2 py-1 text-center text-[9px] font-semibold leading-tight ${palette.badge}`}
        >
          {probability.capacity_status}
        </span>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-[minmax(5rem,0.9fr)_minmax(0,1.1fr)] items-center gap-1.5 py-0.5">
        <div className="flex min-w-0 items-center justify-center">
          <div className="relative flex h-[clamp(4.5rem,5.5vw,5.5rem)] w-[clamp(4.5rem,5.5vw,5.5rem)] shrink-0 items-center justify-center 2xl:h-36 2xl:w-36">
            <svg viewBox="0 0 140 140" className="h-full w-full -rotate-90">
              <circle
                cx="70"
                cy="70"
                r={RADIUS}
                className="fill-none stroke-slate-800"
                strokeWidth="13"
              />
              <circle
                cx="70"
                cy="70"
                r={RADIUS}
                className={`fill-none ${palette.ring}`}
                strokeWidth="13"
                strokeLinecap="round"
                strokeDasharray={CIRCUMFERENCE}
                strokeDashoffset={progress}
              />
            </svg>
            <div className="absolute px-2 text-center">
              <p className="text-lg font-semibold leading-none text-white 2xl:text-2xl">
                {available ? `${riskPercent.toFixed(1)}%` : "--"}
              </p>
              <p className="mt-1 text-[8px] uppercase tracking-[0.12em] text-slate-400">
                Maximum need
              </p>
            </div>
          </div>
        </div>

        <div className="grid min-w-0 gap-1">
          <div className="grid grid-cols-1 gap-1">
            <GaugeMetric label="Highest-Risk Time" value={peakHorizon} />
            <GaugeMetric
              label="Reserve Target"
              value={`${reserveTarget.toFixed(0)} MW`}
            />
          </div>
        </div>
      </div>

    </div>
  );
}

function GaugeMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-lg border border-slate-800 bg-slate-950/55 px-2 py-1 text-center 2xl:py-3">
      <p className="truncate text-[8px] uppercase tracking-[0.1em] text-slate-500">
        {label}
      </p>
      <p className="mt-0.5 truncate text-xs font-semibold text-slate-100 2xl:text-sm">
        {value}
      </p>
    </div>
  );
}

function formatRiskHorizon(minutes?: number | null): string {
  if (minutes == null || !Number.isFinite(minutes)) return "--";
  if (minutes < 60) return `+${minutes}m`;
  const hours = minutes / 60;
  return Number.isInteger(hours) ? `+${hours}h` : `+${hours.toFixed(1)}h`;
}
