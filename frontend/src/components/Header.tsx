import type { DataQuality } from "../types/dashboard";

interface HeaderProps {
  lastUpdated?: string | null;
  systemStatus?: string;
  gridStatus?: string;
  weatherStatus?: string;
  forecastStatus?: string;
  scenarioLabel?: string;
  dataQuality?: DataQuality | null;
  refreshError?: string;
  theme?: "dark" | "light";
  onThemeChange?: (theme: "dark" | "light") => void;
}

function formatTimestamp(value?: string | null): string {
  if (!value) {
    return "--";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export default function Header({
  lastUpdated,
  systemStatus = "Operational",
  gridStatus,
  weatherStatus,
  forecastStatus,
  scenarioLabel,
  dataQuality,
  refreshError,
  theme = "dark",
  onThemeChange,
}: HeaderProps) {
  return (
    <header className="max-w-full overflow-x-hidden border-b border-cyan-500/10 bg-slate-950/95 px-3 py-1.5 text-slate-100 shadow-[0_0_32px_rgba(8,145,178,0.08)] backdrop-blur lg:px-4">
      <div className="mx-auto grid w-full min-w-0 max-w-[1920px] gap-2 lg:grid-cols-[minmax(20rem,0.85fr)_minmax(0,1.35fr)] lg:items-center">
        <div className="min-w-0">
          <p className="hidden text-[9px] font-semibold uppercase tracking-[0.26em] text-cyan-300 sm:block">
            WGDSS Control Room
          </p>
          <h1 className="mt-0.5 max-w-full whitespace-normal text-lg font-semibold leading-tight text-white sm:text-xl">
            <span className="block sm:inline">T&amp;TEC Weather Grid</span>{" "}
            <span className="block sm:inline">Decision Support System</span>
          </h1>
          <div className="mt-1 flex min-w-0 items-center gap-2">
            {onThemeChange ? (
              <button
                type="button"
                className="shrink-0 rounded-md border border-slate-700 bg-slate-900/70 px-2 py-0.5 text-[9px] font-semibold text-slate-300 hover:border-cyan-400/40 hover:text-cyan-100"
                onClick={() => onThemeChange(theme === "dark" ? "light" : "dark")}
                aria-label={theme === "dark" ? "Use light theme" : "Use dark theme"}
              >
                {theme === "dark" ? "Light theme" : "Dark theme"}
              </button>
            ) : null}
            {refreshError ? (
              <p
                className="min-w-0 truncate text-[9px] font-medium text-amber-300"
                title={refreshError}
              >
                Refresh delayed · showing last successful snapshot
              </p>
            ) : null}
          </div>
        </div>

        <div className="grid min-w-0 grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-5">
          <HeaderMetric
            label="Weather"
            value={weatherStatus ?? dataQuality?.weather_status ?? systemStatus}
            tone={
              dataQuality?.is_stale || dataQuality?.fallback_used ? "amber" : "emerald"
            }
          />
          <HeaderMetric
            label="Forecast"
            value={forecastStatus ?? dataQuality?.weather_status ?? systemStatus}
            tone="cyan"
          />
          <HeaderMetric
            label="Grid Status"
            value={
              dataQuality?.grid_status.startsWith("SIMULATED")
                ? `Simulated · ${gridStatus ?? systemStatus}`
                : (gridStatus ?? systemStatus)
            }
            tone={
              dataQuality?.grid_is_stale ||
              dataQuality?.grid_fallback_used ||
              dataQuality?.decision_status === "INHIBITED"
                ? "amber"
                : "emerald"
            }
          />
          <HeaderMetric
            label="Scenario"
            value={scenarioLabel ?? "Typical Day"}
            tone="slate"
          />
          <HeaderMetric
            label="Last Updated"
            value={formatTimestamp(lastUpdated)}
            tone="slate"
          />
        </div>
      </div>
    </header>
  );
}

function HeaderMetric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "emerald" | "cyan" | "amber" | "slate";
}) {
  const toneClasses: Record<"emerald" | "cyan" | "amber" | "slate", string> = {
    emerald: "border-emerald-500/20 bg-emerald-500/10 text-emerald-100",
    cyan: "border-cyan-500/20 bg-cyan-500/10 text-cyan-100",
    amber: "border-amber-500/20 bg-amber-500/10 text-amber-100",
    slate: "border-slate-700/80 bg-slate-950/60 text-slate-100",
  };

  return (
    <div className={`flex min-h-[3.2rem] min-w-0 flex-col items-center justify-center rounded-lg border px-2 py-1.5 text-center shadow-[0_0_24px_rgba(8,145,178,0.06)] ${toneClasses[tone]}`}>
      <p className="text-[9px] font-semibold uppercase tracking-[0.14em] text-slate-300">
        {label}
      </p>
      <p className="mt-0.5 break-words text-[0.72rem] font-semibold leading-tight text-white sm:text-[0.78rem]">
        {value}
      </p>
    </div>
  );
}
