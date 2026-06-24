import type { GridStatus } from "../types/dashboard";

interface GridStatusCardProps {
  gridStatus: GridStatus;
  className?: string;
}

export default function GridStatusCard({
  gridStatus,
  className = "",
}: GridStatusCardProps) {
  return (
    <div className={`rounded-lg border border-slate-800 bg-slate-900/80 p-4 ${className}`}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-300">
            Grid Status
          </p>
          <h2 className="mt-1 text-lg font-semibold text-white">
            Supply and Demand
          </h2>
        </div>
        <span className="rounded-full border border-slate-700 px-3 py-1 text-xs font-medium text-slate-300">
          {gridStatus.grid_status}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3 text-sm">
        <Metric label="Demand" value={`${gridStatus.current_demand_mw.toFixed(0)} MW`} />
        <Metric label="Generation" value={`${gridStatus.current_generation_mw.toFixed(0)} MW`} />
        <Metric label="Available Capacity" value={`${gridStatus.total_available_capacity_mw.toFixed(0)} MW`} />
        <Metric label="Reserve Margin" value={`${gridStatus.reserve_margin_percent.toFixed(1)}%`} />
      </div>

      <div className="mt-4 grid gap-2 text-sm text-slate-300 sm:grid-cols-2">
        <p>
          Demand Period: <span className="font-medium text-white">{gridStatus.demand_period}</span>
        </p>
        <p>
          Source: <span className="font-medium text-white">{gridStatus.source_provider}</span>
        </p>
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/60 px-3 py-2">
      <p className="text-xs text-slate-400">{label}</p>
      <p className="mt-1 text-sm font-semibold text-white">{value}</p>
    </div>
  );
}
