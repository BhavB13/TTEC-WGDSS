interface HeaderProps {
  lastUpdated?: string | null;
  systemStatus?: string;
  gridStatus?: string;
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
}: HeaderProps) {
  return (
    <header className="border-b border-cyan-500/10 bg-slate-950/95 px-4 py-3 text-slate-100 shadow-[0_0_32px_rgba(8,145,178,0.08)] backdrop-blur">
      <div className="mx-auto grid w-full max-w-[1680px] gap-3 xl:grid-cols-[minmax(0,1.35fr)_minmax(320px,0.65fr)] xl:items-center">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.3em] text-cyan-300">
            WGDSS Control Room
          </p>
          <h1 className="mt-1.5 text-2xl font-semibold text-white sm:text-[1.85rem]">
            T&amp;TEC Weather Grid Decision Support System
          </h1>
        </div>

        <div className="flex min-w-0 flex-wrap items-center gap-2 xl:justify-end">
          <HeaderMetric
            label="Grid Status"
            value={gridStatus ?? systemStatus}
            tone="emerald"
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
    <div className={`min-w-0 rounded-2xl border px-4 py-3 text-center shadow-[0_0_24px_rgba(8,145,178,0.06)] ${toneClasses[tone]}`}>
      <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-300">
        {label}
      </p>
      <p className="mt-2 break-words text-[0.9rem] font-semibold leading-tight text-white sm:text-[0.95rem]">
        {value}
      </p>
    </div>
  );
}
