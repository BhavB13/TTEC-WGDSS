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
    <div className={`rounded-lg border border-slate-800 bg-slate-900/80 p-4 ${className}`}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-300">
            Recommendation
          </p>
          <h2 className="mt-1 text-lg font-semibold text-white">
            Operational Guidance
          </h2>
        </div>
        <span
          className={`rounded-full border px-3 py-1 text-xs font-semibold ${
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

      <div className="rounded-md border border-slate-800 bg-slate-950/60 p-4">
        <p className="text-xs uppercase tracking-[0.16em] text-slate-400">
          Action
        </p>
        <p className="mt-2 text-xl font-semibold text-white">
          {recommendation.recommendation}
        </p>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <Metric label="Probability" value={recommendation.probability_score.toFixed(2)} />
        <Metric label="30m Demand" value={`${recommendation.forecast_demand_30m.toFixed(0)} MW`} />
        <Metric label="60m Demand" value={`${recommendation.forecast_demand_60m.toFixed(0)} MW`} />
        <Metric label="Reason" value={recommendation.reason} compact />
      </div>

      <div className="mt-4">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">
          Explainability Factors
        </p>
        <ul className="mt-2 space-y-2 text-sm text-slate-200">
          {recommendation.factors.length > 0 ? (
            recommendation.factors.map((factor) => (
              <li
                key={factor}
                className="rounded-md border border-slate-800 bg-slate-950/60 px-3 py-2"
              >
                {factor}
              </li>
            ))
          ) : (
            <li className="rounded-md border border-slate-800 bg-slate-950/60 px-3 py-2 text-slate-400">
              No additional factors reported.
            </li>
          )}
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
    <div className="rounded-md border border-slate-800 bg-slate-950/60 px-3 py-2">
      <p className="text-xs text-slate-400">{label}</p>
      <p
        className={`mt-1 font-semibold text-white ${
          compact ? "break-words text-sm" : "text-base"
        }`}
      >
        {value}
      </p>
    </div>
  );
}
