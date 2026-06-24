interface HeaderProps {
  lastUpdated?: string | null;
  systemStatus?: string;
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
}: HeaderProps) {
  return (
    <header className="border-b border-slate-800 bg-slate-950/95 px-4 py-4 text-slate-100 backdrop-blur">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-300">
            T&TEC
          </p>
          <h1 className="mt-1 text-xl font-semibold text-white sm:text-2xl">
            Weather-Based Generation Decision Support System
          </h1>
        </div>

        <div className="grid gap-1 text-sm text-slate-300 sm:text-right">
          <p>
            System Status:{" "}
            <span className="font-semibold text-emerald-300">{systemStatus}</span>
          </p>
          <p>Last Updated: {formatTimestamp(lastUpdated)}</p>
        </div>
      </div>
    </header>
  );
}
