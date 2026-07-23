import { useMemo, useState } from "react";

import { useDashboardTime } from "../context/DashboardTimeContext";
import type { DashboardTimeContext } from "../types/dashboard";

export default function DayNavigationBar({
  context,
}: {
  context: DashboardTimeContext | null;
}) {
  const view = useDashboardTime();
  const [dateError, setDateError] = useState("");
  const dates = context?.available_dates ?? [];
  const available = useMemo(() => new Set(dates), [dates]);
  const min = context?.available_start ?? "2026-06-01";
  const max = context?.available_end ?? context?.active_date ?? "2026-06-30";
  const selected = context?.selected_date ?? view.selectedDate ?? max;
  const selectedIndex = dates.indexOf(selected);

  const moveDay = (offset: number) => {
    const candidate = dates[selectedIndex + offset];
    if (!candidate) return;
    setDateError("");
    view.setSelectedDate(candidate);
  };

  return (
    <section className="mode-bar" aria-label="June replay day navigation">
      <div className="day-navigation-controls">
        <button
          type="button"
          onClick={() => moveDay(-1)}
          disabled={selectedIndex <= 0}
          aria-label="Previous available day"
        >
          ‹
        </button>
        <label>
          <span>June replay date</span>
          <input
            type="date"
            min={min}
            max={max}
            value={selected}
            onChange={(event) => {
              const candidate = event.target.value;
              if (!available.has(candidate)) {
                setDateError("That date is unavailable in the June replay.");
                return;
              }
              setDateError("");
              view.setSelectedDate(candidate);
            }}
          />
        </label>
        <button
          type="button"
          onClick={() => moveDay(1)}
          disabled={selectedIndex < 0 || selectedIndex >= dates.length - 1}
          aria-label="Next available day"
        >
          ›
        </button>
        <button
          type="button"
          disabled={context?.is_active_day ?? true}
          onClick={() => {
            setDateError("");
            view.resetToActiveDay();
          }}
        >
          Return to Active Day
        </button>
      </div>

      <div className={`mode-evidence ${context?.is_active_day ? "present" : "replay-day"}`}>
        <strong>
          {context?.is_active_day
            ? "ACTIVE · SIMULATED PRESENT"
            : "PREVIOUS DAY · JUNE REPLAY"}
        </strong>
        <span>{context?.selected_date ?? "Resolving date"}</span>
        <span>{context ? `${context.granularity} · ${context.record_count} records` : "Resolving records"}</span>
        <span className="mode-source">{context?.source ?? "Resolving source"}</span>
        {dateError || context?.notice ? <em>{dateError || context?.notice}</em> : null}
      </div>
    </section>
  );
}
