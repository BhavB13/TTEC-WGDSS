import type { ProbabilityData } from "../types/dashboard";

interface ProbabilityGaugeProps {
  probability: ProbabilityData;
  className?: string;
}

const RADIUS = 46;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

function riskPalette(riskLevel: ProbabilityData["risk_level"]) {
  switch (riskLevel) {
    case "HIGH":
      return {
        ring: "stroke-rose-400",
        badge: "border-rose-500/40 bg-rose-500/10 text-rose-200",
      };
    case "MEDIUM":
      return {
        ring: "stroke-amber-400",
        badge: "border-amber-500/40 bg-amber-500/10 text-amber-200",
      };
    default:
      return {
        ring: "stroke-emerald-400",
        badge: "border-emerald-500/40 bg-emerald-500/10 text-emerald-200",
      };
  }
}

export default function ProbabilityGauge({
  probability,
  className = "",
}: ProbabilityGaugeProps) {
  const score = Math.max(0, Math.min(1, probability.probability_score));
  const progress = CIRCUMFERENCE - score * CIRCUMFERENCE;
  const palette = riskPalette(probability.risk_level);

  return (
    <div className={`flex h-full w-full min-w-0 flex-col rounded-2xl border border-cyan-500/15 bg-slate-900/80 p-3.5 shadow-[0_0_34px_rgba(8,145,178,0.08)] ${className}`}>
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">
            Probability
          </p>
          <h2 className="mt-1 text-[1.05rem] font-semibold text-white">
            Risk Gauge
          </h2>
        </div>
        <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${palette.badge}`}>
          {probability.risk_level}
        </span>
      </div>

      <div className="flex flex-1 flex-col items-center justify-start gap-2">
        <div className="relative flex h-[clamp(8.5rem,18vw,11rem)] w-[clamp(8.5rem,18vw,11rem)] items-center justify-center">
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
              className={`fill-none stroke-current ${palette.ring}`}
              strokeWidth="14"
              strokeLinecap="round"
              strokeDasharray={CIRCUMFERENCE}
              strokeDashoffset={progress}
            />
          </svg>
          <div className="absolute text-center">
            <p className="text-3xl font-semibold text-white">
              {score.toFixed(2)}
            </p>
            <p className="text-xs uppercase tracking-[0.16em] text-slate-400">
              0.0 - 1.0
            </p>
          </div>
        </div>

        <div className="grid w-full gap-2 text-sm text-slate-300">
          <Stat label="Risk Score" value={score.toFixed(2)} />
          <Stat label="30m Demand" value={`${probability.forecast_demand_30m.toFixed(0)} MW`} />
          <Stat label="60m Demand" value={`${probability.forecast_demand_60m.toFixed(0)} MW`} />
          <Stat label="Short Explanation" value={probability.reason} />
        </div>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="flex min-h-[3.75rem] flex-col justify-center rounded-lg border border-slate-800 bg-slate-950/60 px-2.5 py-2 shadow-inner shadow-black/20">
      <p className="text-xs text-slate-400">{label}</p>
      <p className="mt-1 break-words text-[0.9rem] font-semibold text-white">{value}</p>
    </div>
  );
}
