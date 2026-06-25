import type { RecommendationData } from "../types/dashboard";

interface RecommendationCardProps {
  recommendation: RecommendationData;
  className?: string;
}

export default function RecommendationCard({
  recommendation,
  className = "",
}: RecommendationCardProps) {
  return (
    <div className={`w-full min-w-0 rounded-2xl border border-cyan-500/15 bg-slate-900/80 p-3 shadow-[0_0_34px_rgba(8,145,178,0.08)] ${className}`}>
      <div className="mb-2.5 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">
            Recommendation
          </p>
          <h2 className="mt-1 text-[0.98rem] font-semibold leading-tight text-white">
            Operational Guidance
          </h2>
        </div>
        <span
          className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${
            recommendation.risk_level === "HIGH"
              ? "border-rose-500/40 bg-rose-500/10 text-rose-200"
              : recommendation.risk_level === "MEDIUM"
                ? "border-amber-500/40 bg-amber-500/10 text-amber-200"
                : "border-emerald-500/40 bg-emerald-500/10 text-emerald-200"
          }`}
        >
          {recommendation.risk_level}
        </span>
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3 text-center shadow-inner shadow-black/20">
        <p className="text-[10px] uppercase tracking-[0.16em] text-slate-400">
          Action
        </p>
        <p className="mt-2 break-words text-[0.98rem] font-semibold leading-tight text-white">
          {recommendation.recommendation}
        </p>
      </div>

      <div className="mt-2.5 grid gap-2 text-sm sm:grid-cols-2">
        <Metric label="Probability" value={recommendation.probability_score.toFixed(2)} />
        <Metric label="30m Demand" value={`${recommendation.forecast_demand_30m.toFixed(0)} MW`} />
        <Metric label="60m Demand" value={`${recommendation.forecast_demand_60m.toFixed(0)} MW`} />
      </div>

      <div className="mt-2.5">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">
          Reasoning
        </p>
        <ul className="mt-2 space-y-1.5 text-sm text-slate-200">
          {(recommendation.factors.length > 0 ? recommendation.factors : [recommendation.reason]).map((factor, index) => (
            <li
              key={`${factor}-${index}`}
              className="flex gap-3 rounded-xl border border-slate-800 bg-slate-950/60 px-3 py-2"
            >
              <span className="font-semibold text-cyan-300">{index + 1}.</span>
              <span className="flex-1">{factor}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
  compact = false,
}: {
  label: string;
  value: string;
  compact?: boolean;
}) {
  return (
    <div className="flex min-h-[3.75rem] flex-col items-center justify-center rounded-lg border border-slate-800 bg-slate-950/60 px-2.5 py-2 text-center shadow-inner shadow-black/20">
      <p className="text-[10px] uppercase tracking-[0.12em] text-slate-400">{label}</p>
      <p className={`mt-1 font-semibold leading-snug text-white ${compact ? "break-words text-[0.85rem]" : "text-[0.9rem]"}`}>
        {value}
      </p>
    </div>
  );
}
