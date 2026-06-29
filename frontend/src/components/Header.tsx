import type { DataQuality } from "../types/dashboard";

interface HeaderProps {
  lastUpdated?: string | null;
  systemStatus?: string;
  gridStatus?: string;
  dataQuality?: DataQuality | null;
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
  dataQuality,
}: HeaderProps) {
  return (
    <header className="border-b border-cyan-500/10 bg-slate-950/95 px-4 py-2 text-slate-100 shadow-[0_0_32px_rgba(8,145,178,0.08)] backdrop-blur">
      <div className="mx-auto grid w-full max-w-[1680px] gap-2 xl:grid-cols-[minmax(0,1fr)_minmax(500px,0.9fr)] xl:items-center">
        <div className="min-w-0">
          <p className="hidden text-[11px] font-semibold uppercase tracking-[0.3em] text-cyan-300 sm:block">
            WGDSS Control Room
          </p>
          <h1 className="mt-1 max-w-full whitespace-normal text-xl font-semibold leading-tight text-white sm:text-[1.45rem]">
            <span className="block sm:inline">T&amp;TEC Weather Grid</span>{" "}
            <span className="block sm:inline">Decision Support System</span>
          </h1>
        </div>

        <div className="grid min-w-0 grid-cols-1 gap-2 sm:grid-cols-3">
          <HeaderMetric
            label="Grid Status"
            value={gridStatus ?? systemStatus}
            tone="emerald"
          />
          {dataQuality ? (
            <HeaderMetric
              label="Data Quality"
              value={`${dataQuality.weather_status} / ${dataQuality.grid_status}`}
              tone={dataQuality.overall_status === "GOOD" ? "cyan" : "amber"}
            />
          ) : null}
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
    <div className={`flex min-h-[3.75rem] min-w-0 flex-col items-center justify-center rounded-xl border px-3 py-2 text-center shadow-[0_0_24px_rgba(8,145,178,0.06)] ${toneClasses[tone]}`}>
      <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-300">
        {label}
      </p>
      <p className="mt-1 break-words text-[0.82rem] font-semibold leading-tight text-white sm:text-[0.88rem]">
        {value}
      </p>
    </div>
  );
}
