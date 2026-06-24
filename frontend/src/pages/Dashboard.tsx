import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import CurrentConditions from "../components/CurrentConditions";
import DemandForecastChart from "../components/DemandForecastChart";
import ForecastTable from "../components/ForecastTable";
import GridStatusCard from "../components/GridStatusCard";
import Header from "../components/Header";
import ProbabilityGauge from "../components/ProbabilityGauge";
import RecommendationCard from "../components/RecommendationCard";
import WeatherMap from "../components/WeatherMap";
import { getDashboardSnapshot } from "../services/api";
import type { DashboardSnapshot } from "../types/dashboard";

type LoadState = "loading" | "ready" | "error";

export default function Dashboard() {
  const [state, setState] = useState<LoadState>("loading");
  const [snapshot, setSnapshot] = useState<DashboardSnapshot | null>(null);
  const [error, setError] = useState<string>("");

  const loadSnapshot = useCallback(async () => {
    setState("loading");
    setError("");
    try {
      const data = await getDashboardSnapshot();
      setSnapshot(data);
      setState("ready");
    } catch (cause) {
      setSnapshot(null);
      setError(cause instanceof Error ? cause.message : "Failed to load dashboard snapshot");
      setState("error");
    }
  }, []);

  useEffect(() => {
    void loadSnapshot();
  }, [loadSnapshot]);

  const systemStatus = useMemo(() => {
    if (!snapshot) {
      return state === "loading" ? "Loading" : "Unavailable";
    }
    return snapshot.grid.grid_status;
  }, [snapshot, state]);

  if (state === "loading") {
    return (
      <Shell lastUpdated={null} systemStatus="Loading">
        <LoadingState />
      </Shell>
    );
  }

  if (state === "error" || !snapshot) {
    return (
      <Shell lastUpdated={null} systemStatus="Unavailable">
        <ErrorState message={error} onRetry={loadSnapshot} />
      </Shell>
    );
  }

  return (
    <Shell
      lastUpdated={snapshot.weather.timestamp}
      systemStatus={systemStatus}
    >
      <div className="grid gap-4 xl:grid-cols-12">
        <CurrentConditions
          weather={snapshot.weather}
          className="xl:col-span-4"
        />

        <ProbabilityGauge
          probability={snapshot.probability}
          className="xl:col-span-4"
        />

        <RecommendationCard
          recommendation={snapshot.recommendation}
          className="xl:col-span-4"
        />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-12">
        <WeatherMap
          gridStatus={snapshot.grid}
          className="xl:col-span-7"
        />

        <DemandForecastChart
          gridStatus={snapshot.grid}
          probability={snapshot.probability}
          className="xl:col-span-5"
        />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-12">
        <GridStatusCard
          gridStatus={snapshot.grid}
          className="xl:col-span-6"
        />

        <ForecastTable
          forecast={snapshot.forecast.items}
          className="xl:col-span-6"
        />
      </div>
    </Shell>
  );
}

function Shell({
  children,
  lastUpdated,
  systemStatus,
}: {
  children: ReactNode;
  lastUpdated: string | null;
  systemStatus: string;
}) {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <Header lastUpdated={lastUpdated} systemStatus={systemStatus} />
      <main className="mx-auto flex w-full max-w-7xl flex-col gap-4 px-4 py-4">
        {children}
      </main>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="grid gap-4 xl:grid-cols-12">
      <SkeletonCard className="xl:col-span-4" />
      <SkeletonCard className="xl:col-span-4" />
      <SkeletonCard className="xl:col-span-4" />
      <SkeletonCard className="xl:col-span-7" tall />
      <SkeletonCard className="xl:col-span-5" tall />
      <SkeletonCard className="xl:col-span-6" />
      <SkeletonCard className="xl:col-span-6" />
    </div>
  );
}

function SkeletonCard({
  className = "",
  tall = false,
}: {
  className?: string;
  tall?: boolean;
}) {
  return (
    <div
      className={`animate-pulse rounded-lg border border-slate-800 bg-slate-900/80 p-4 ${className} ${
        tall ? "min-h-[30rem]" : "min-h-[14rem]"
      }`}
    >
      <div className="h-4 w-32 rounded bg-slate-800" />
      <div className="mt-4 h-6 w-56 rounded bg-slate-800" />
      <div className="mt-6 grid grid-cols-2 gap-3">
        <div className="h-16 rounded bg-slate-800" />
        <div className="h-16 rounded bg-slate-800" />
        <div className="h-16 rounded bg-slate-800" />
        <div className="h-16 rounded bg-slate-800" />
      </div>
    </div>
  );
}

function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="grid place-items-center py-16">
      <div className="max-w-lg rounded-lg border border-rose-500/30 bg-rose-500/10 p-6 text-center">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-rose-200">
          Unable to load dashboard
        </p>
        <h2 className="mt-2 text-xl font-semibold text-white">
          The live snapshot request failed.
        </h2>
        <p className="mt-3 break-words text-sm text-rose-100/90">
          {message || "An unexpected error occurred while loading the dashboard."}
        </p>
        <button
          type="button"
          onClick={onRetry}
          className="mt-6 rounded-md bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400"
        >
          Retry
        </button>
      </div>
    </div>
  );
}
