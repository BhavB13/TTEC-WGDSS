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
          <h2 className="mt-1 text-[0.98rem] font-semibold leading-tight text-white">
            Risk Gauge
          </h2>
        </div>
        <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${palette.badge}`}>
          {probability.risk_level}
        </span>
      </div>

      <div className="flex min-h-0 flex-1 flex-col items-center justify-evenly gap-4">
        <div className="relative flex h-[clamp(11rem,22vw,15rem)] w-[clamp(11rem,22vw,15rem)] items-center justify-center">
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

        <div className="grid w-full grid-cols-3 gap-2 text-sm text-slate-300">
          <RiskBand label="Low" range="0.00–0.44" tone="emerald" />
          <RiskBand label="Medium" range="0.45–0.69" tone="amber" />
          <RiskBand label="High" range="0.70–1.00" tone="rose" />
        </div>

        <div className="w-full rounded-xl border border-slate-800 bg-slate-950/55 px-3 py-3">
          <div className="relative h-2 overflow-hidden rounded-full bg-gradient-to-r from-emerald-400 via-amber-400 to-rose-400">
            <span
              className="absolute top-1/2 h-5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full border border-white bg-slate-950 shadow-[0_0_10px_rgba(255,255,255,0.5)]"
              style={{ left: `${score * 100}%` }}
            />
          </div>
          <div className="mt-2 flex justify-between text-[9px] uppercase tracking-[0.1em] text-slate-500">
            <span>Low pressure</span>
            <span>Generation action pressure</span>
          </div>
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
    <div className={`flex min-h-[3.75rem] flex-col items-center justify-center rounded-lg border px-2 py-2 text-center ${toneClasses[tone]}`}>
      <p className="text-[10px] font-semibold uppercase tracking-[0.12em]">{label}</p>
      <p className="mt-1 text-[0.72rem] leading-tight text-slate-300">{range}</p>
    </div>
  );
}
