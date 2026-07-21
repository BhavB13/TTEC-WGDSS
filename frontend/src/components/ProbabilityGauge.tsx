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

  return (
    <div
      className={`flex h-full min-h-0 w-full min-w-0 flex-col overflow-hidden rounded-2xl border border-cyan-500/15 bg-slate-900/80 p-3 shadow-[0_0_34px_rgba(8,145,178,0.08)] ${className}`}
    >
      <div className="mb-1.5 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">
            Capacity Risk
          </p>
          <h2 className="mt-1 text-[0.98rem] font-semibold leading-tight text-white">
            Projected reserve adequacy
          </h2>
        </div>
        <span
          className={`max-w-[9rem] rounded-full border px-2.5 py-1 text-center text-[10px] font-semibold leading-tight ${palette.badge}`}
        >
          {probability.capacity_status}
        </span>
      </div>

      <div className="flex min-h-0 flex-1 flex-col items-center justify-between gap-1.5">
        <div className="relative flex h-[clamp(5.25rem,9vw,6rem)] w-[clamp(5.25rem,9vw,6rem)] shrink-0 items-center justify-center">
          <svg viewBox="0 0 140 140" className="h-full w-full -rotate-90">
            <circle
              cx="70"
              cy="70"
              r={RADIUS}
              className="fill-none stroke-slate-800"
              strokeWidth="14"
            />
            <circle
              cx="70"
              cy="70"
              r={RADIUS}
              className={`fill-none ${palette.ring}`}
              strokeWidth="14"
              strokeLinecap="round"
              strokeDasharray={CIRCUMFERENCE}
              strokeDashoffset={progress}
            />
          </svg>
          <div className="absolute px-2 text-center">
            <p className="text-xl font-semibold text-white">
              {available ? `${riskPercent.toFixed(1)}%` : "--"}
            </p>
            <p className="max-w-[7rem] text-[9px] uppercase tracking-[0.1em] text-slate-400">
              Reserve below {reserveTarget.toFixed(0)} MW
            </p>
          </div>
        </div>

        <div className="grid w-full grid-cols-2 gap-1.5 text-slate-300 sm:grid-cols-4">
          {(["Normal", "Watch", "Prepare Generation", "Add Generation"] as const).map(
            (status) => (
              <RiskBand
                key={status}
                label={status}
                active={probability.capacity_status === status}
              />
            ),
          )}
        </div>
      </div>
    </div>
  );
}

function RiskBand({ label, active }: { label: string; active: boolean }) {
  return (
    <div
      className={`flex min-h-[1.75rem] items-center justify-center rounded-lg border px-1 py-0.5 text-center ${
        active
          ? "border-cyan-400/55 bg-cyan-500/15 text-cyan-50"
          : "border-slate-700/80 bg-slate-950/45 text-slate-400"
      }`}
    >
      <p className="text-[9px] font-semibold uppercase leading-tight tracking-[0.08em]">
        {label}
      </p>
    </div>
  );
}
