import type { GridStatus } from "../types/dashboard";

interface GridStatusCardProps {
  gridStatus: GridStatus;
  className?: string;
}

export default function GridStatusCard({
  gridStatus,
  className = "",
}: GridStatusCardProps) {
  const generationLabel =
    ["HistoricalScadaReplay", "HistoricalScadaSimulatedReplay"].includes(
      gridStatus.source_provider,
    )
      ? "Generation (TRA)"
      : "Generation";
  const systemSpinMw =
    typeof gridStatus.spinning_reserve_mw === "number" &&
    Number.isFinite(gridStatus.spinning_reserve_mw)
      ? gridStatus.spinning_reserve_mw
      : null;
  return (
    <div className={`flex h-full w-full min-w-0 flex-col rounded-2xl border border-cyan-500/15 bg-slate-900/80 p-3.5 shadow-[0_0_34px_rgba(8,145,178,0.08)] ${className}`}>
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">
            Grid Status
          </p>
          <h2 className="mt-1 text-[0.98rem] font-semibold leading-tight text-white">
            Supply and Demand
          </h2>
        </div>
        <span className="rounded-full border border-slate-700 bg-slate-950/60 px-2.5 py-1 text-[11px] font-medium text-slate-300">
          {gridStatus.grid_status}
        </span>
      </div>

      <div className="grid flex-1 grid-cols-1 gap-2.5 text-sm sm:grid-cols-2">
        <Metric label="Demand" value={`${gridStatus.current_demand_mw.toFixed(0)} MW`} />
        <Metric label={generationLabel} value={`${gridStatus.current_generation_mw.toFixed(0)} MW`} />
        <Metric label="Available Capacity" value={`${gridStatus.total_available_capacity_mw.toFixed(0)} MW`} />
        <Metric
          label="System Spin"
          value={systemSpinMw == null ? "Unavailable" : `${systemSpinMw.toFixed(0)} MW`}
        />
      </div>

      <div className="mt-3 grid gap-2 text-sm text-slate-300 sm:grid-cols-2">
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
    <div className="flex min-h-[4.25rem] flex-col items-center justify-center rounded-lg border border-slate-800 bg-slate-950/60 px-2.5 py-2.5 text-center shadow-inner shadow-black/20">
      <p className="text-[10px] uppercase tracking-[0.12em] text-slate-400">{label}</p>
      <p className="mt-1 text-[0.88rem] font-semibold leading-tight text-white">{value}</p>
    </div>
  );
}
