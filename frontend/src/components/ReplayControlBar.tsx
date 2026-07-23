import type { ReplayStatus } from "../types/dashboard";

interface ReplayControlBarProps {
  status: ReplayStatus;
  sourceTimestamp?: string | null;
  busy?: boolean;
  onControl: (input: {
    action: "play" | "pause" | "reset" | "step" | "configure";
    step_minutes?: number;
    speed_multiplier?: number;
  }) => Promise<void>;
}

export default function ReplayControlBar({
  status,
  sourceTimestamp,
  busy = false,
  onControl,
}: ReplayControlBarProps) {
  const operationalTimestamp =
    status.mode === "historical_replay" && sourceTimestamp
      ? sourceTimestamp
      : status.cursor_at;

  return (
    <section className="replay-control-bar grid min-w-0 gap-1.5 rounded-lg border border-cyan-500/20 bg-slate-950/70 px-2.5 py-1.5 lg:grid-cols-[minmax(15rem,1fr)_auto_auto] lg:items-center">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${status.is_playing ? "animate-pulse bg-emerald-400" : "bg-amber-400"}`} />
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-cyan-300">
            {replayModeLabel(status.mode)}
          </p>
          <span className="rounded border border-slate-700 px-1.5 py-0.5 text-[9px] text-slate-400">
            {status.is_playing ? "PLAYING" : "PAUSED"}
          </span>
        </div>
        <div className="mt-0.5 flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-0.5">
          <p className="text-xs font-semibold tabular-nums text-white">
            <span className="text-[9px] uppercase tracking-[0.12em] text-slate-500">
              Operational time
            </span>{" "}
            {formatReplayTimestamp(operationalTimestamp)}
          </p>
          {status.mode === "historical_replay" && sourceTimestamp ? (
            <p
              className="text-[10px] font-medium tabular-nums text-slate-400"
              title="Internal replay index used to reveal the archived source in sequence"
            >
              Replay index {formatReplayTimestamp(status.cursor_at)}
            </p>
          ) : null}
          <p className="text-[10px] text-slate-400">
            {status.dataset_label} · {status.revealed_records}/{status.total_replay_records} records · {status.progress_percent.toFixed(1)}%
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          disabled={busy}
          onClick={() => void onControl({ action: status.is_playing ? "pause" : "play" })}
          className="min-w-[4.5rem] rounded-lg border border-cyan-400/30 bg-cyan-500/12 px-2.5 py-1.5 text-[10px] font-semibold text-cyan-100 disabled:opacity-50"
        >
          {status.is_playing ? "Pause" : "Play"}
        </button>
        <button
          type="button"
          disabled={busy || status.is_playing}
          onClick={() => void onControl({ action: "step" })}
          className="rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-[10px] font-semibold text-slate-200 disabled:opacity-40"
        >
          Step
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void onControl({ action: "reset" })}
          className="rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-[10px] font-semibold text-slate-300 disabled:opacity-40"
        >
          Sync Now
        </button>
      </div>

      <div className="flex items-center gap-1.5 text-[10px] text-slate-400">
        <label htmlFor="replay-step">Step</label>
        <select
          id="replay-step"
          value={status.step_minutes}
          disabled={busy}
          onChange={(event) => void onControl({ action: "configure", step_minutes: Number(event.target.value) })}
          className="rounded-lg border border-slate-700 bg-slate-900 px-2 py-1.5 text-slate-100"
        >
          <option value={60}>1 hour</option>
          <option value={360}>6 hours</option>
          <option value={1440}>1 day</option>
        </select>
        <label htmlFor="replay-speed">Rate</label>
        <select
          id="replay-speed"
          value={status.speed_multiplier}
          disabled={busy}
          onChange={(event) => void onControl({ action: "configure", speed_multiplier: Number(event.target.value) })}
          className="rounded-lg border border-slate-700 bg-slate-900 px-2 py-1.5 text-slate-100"
        >
          <option value={1}>Real time</option>
          <option value={60}>1 min/s</option>
          <option value={600}>10 min/s</option>
          <option value={3600}>1 hr/s</option>
          <option value={86400}>1 day/s</option>
        </select>
      </div>
    </section>
  );
}

function replayModeLabel(mode: ReplayStatus["mode"]): string {
  if (mode === "historical_replay") {
    return "June SCADA simulated-present";
  }
  if (mode === "live_read_only") {
    return "Live read-only telemetry";
  }
  return "Simulation replay";
}

function formatReplayTimestamp(value: string): string {
  const date = new Date(value);
  return new Intl.DateTimeFormat("en-TT", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "America/Port_of_Spain",
  }).format(date);
}
