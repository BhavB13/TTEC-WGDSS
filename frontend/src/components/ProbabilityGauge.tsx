import type { ProbabilityData } from "../types/dashboard";

interface ProbabilityGaugeProps {
  probability: ProbabilityData;
  className?: string;
}

const RADIUS = 46;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

function riskPalette(riskLevel: ProbabilityData["risk_level"]) {
  switch (riskLevel) {
    case "UNAVAILABLE":
      return {
        ring: "stroke-slate-500",
        badge: "border-slate-500/40 bg-slate-500/10 text-slate-200",
      };
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
  const available = probability.risk_level !== "UNAVAILABLE";
  const progress = CIRCUMFERENCE - score * CIRCUMFERENCE;
  const palette = riskPalette(probability.risk_level);

  return (
    <div className={`flex h-full min-h-0 w-full min-w-0 flex-col overflow-hidden rounded-2xl border border-cyan-500/15 bg-slate-900/80 p-3 shadow-[0_0_34px_rgba(8,145,178,0.08)] ${className}`}>
      <div className="mb-1.5 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">
            Probability
          </p>
          <h2 className="mt-1 text-[0.98rem] font-semibold leading-tight text-white">
            Risk Gauge
          </h2>
        </div>
        <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${palette.badge}`}>
          {probability.risk_level}
        </span>
      </div>

      <div className="flex min-h-0 flex-1 flex-col items-center justify-between gap-1.5">
        <div className="relative flex h-[clamp(6.25rem,11vw,7.25rem)] w-[clamp(6.25rem,11vw,7.25rem)] shrink-0 items-center justify-center">
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
            <p className="text-xl font-semibold text-white">
              {available ? `${(score * 100).toFixed(1)}%` : "--"}
            </p>
            <p className="max-w-[7rem] text-[9px] uppercase tracking-[0.12em] text-slate-400">
              Reserve shortfall probability
            </p>
          </div>
        </div>

        <div className="grid w-full grid-cols-3 gap-1.5 text-sm text-slate-300">
          <RiskBand label="Low" range="0–29%" tone="emerald" />
          <RiskBand label="Medium" range="30–65%" tone="amber" />
          <RiskBand label="High" range="66–100%" tone="rose" />
        </div>
      </div>
    </div>
  );
}

function RiskBand({
  label,
  range,
  tone,
}: {
  label: string;
  range: string;
  tone: "emerald" | "amber" | "rose";
}) {
  const toneClasses = {
    emerald: "border-emerald-500/25 bg-emerald-500/10 text-emerald-100",
    amber: "border-amber-500/25 bg-amber-500/10 text-amber-100",
    rose: "border-rose-500/25 bg-rose-500/10 text-rose-100",
  };

  return (
    <div className={`flex min-h-[2.15rem] flex-col items-center justify-center rounded-lg border px-1 py-1 text-center ${toneClasses[tone]}`}>
      <p className="text-[10px] font-semibold uppercase tracking-[0.12em]">{label}</p>
      <p className="mt-0.5 text-[0.65rem] leading-tight text-slate-300">{range}</p>
    </div>
  );
}
