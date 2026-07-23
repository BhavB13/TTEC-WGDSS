import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

interface DashboardTimeState {
  selectedDate: string | null;
  setSelectedDate: (selectedDate: string) => void;
  resetToActiveDay: () => void;
}

const STORAGE_KEY = "wgdss-dashboard-selected-day";

const DashboardTimeContext = createContext<DashboardTimeState | null>(null);

export function DashboardTimeProvider({ children }: { children: ReactNode }) {
  const [selectedDate, setSelectedDateState] = useState<string | null>(
    readStoredDate,
  );

  useEffect(() => {
    try {
      if (selectedDate) {
        window.localStorage.setItem(STORAGE_KEY, selectedDate);
      } else {
        window.localStorage.removeItem(STORAGE_KEY);
      }
    } catch {
      // Persistence is optional; navigation still shares in-memory state.
    }
  }, [selectedDate]);

  const value = useMemo<DashboardTimeState>(
    () => ({
      selectedDate,
      setSelectedDate: setSelectedDateState,
      resetToActiveDay: () => setSelectedDateState(null),
    }),
    [selectedDate],
  );

  return (
    <DashboardTimeContext.Provider value={value}>
      {children}
    </DashboardTimeContext.Provider>
  );
}

export function useDashboardTime() {
  const value = useContext(DashboardTimeContext);
  if (!value) {
    throw new Error("useDashboardTime must be used inside DashboardTimeProvider");
  }
  return value;
}

function readStoredDate(): string | null {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return value && /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : null;
  } catch {
    return null;
  }
}
