import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import CurrentConditions from "../components/CurrentConditions";
import DemandForecastChart from "../components/DemandForecastChart";
import GridStatusCard from "../components/GridStatusCard";
import Header from "../components/Header";
import ProbabilityGauge from "../components/ProbabilityGauge";
import RecommendationCard from "../components/RecommendationCard";
import WeatherMap from "../components/WeatherMap";
import { getDashboardSnapshot } from "../services/api";
import type { DashboardSnapshot, ForecastData } from "../types/dashboard";

type LoadState = "loading" | "ready" | "error";
type DashboardTab = "home" | "operations" | "weather" | "forecast" | "analytics";
type ForecastTab = "demand" | "risk" | "guidance";

export default function Dashboard() {
  const [state, setState] = useState<LoadState>("loading");
  const [snapshot, setSnapshot] = useState<DashboardSnapshot | null>(null);
  const [error, setError] = useState<string>("");
  const [activeTab, setActiveTab] = useState<DashboardTab>("home");
  const [forecastTab, setForecastTab] = useState<ForecastTab>("demand");

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

  const probability = snapshot.probability;
  const recommendation = snapshot.recommendation;

  return (
    <Shell
      lastUpdated={snapshot.weather.timestamp}
      systemStatus={systemStatus}
      gridStatus={snapshot.grid.grid_status}
    >
      <div className="grid h-full min-h-0 w-full min-w-0 gap-3 xl:grid-cols-[clamp(300px,28vw,390px)_minmax(0,1fr)] xl:items-stretch">
        <section className="min-h-0 min-w-0 xl:sticky xl:top-3 xl:self-start xl:h-[calc(100vh-6.25rem)]">
          <WeatherMap
            gridStatus={snapshot.grid}
            rainfallMmHr={snapshot.weather.rainfall_mm_hr}
            className="h-full min-h-0"
          />
        </section>

        <section className="flex min-h-0 w-full min-w-0 flex-col overflow-hidden rounded-2xl border border-cyan-500/15 bg-slate-900/60 p-2.5 shadow-[0_0_40px_rgba(8,145,178,0.06)]">
          <div className="flex h-full min-h-0 w-full min-w-0 flex-col gap-2.5 overflow-hidden">
            <TabBar activeTab={activeTab} onChange={setActiveTab} />

            <div className="min-h-0 flex-1 w-full min-w-0 overflow-hidden">
              {activeTab === "home" ? (
                <WorkspacePage>
                  <HomeTab
                    grid={snapshot.grid}
                    weather={snapshot.weather}
                    probability={probability}
                    recommendation={recommendation}
                    forecastItems={snapshot.forecast.items}
                  />
                </WorkspacePage>
              ) : null}

              {activeTab === "operations" ? (
                <WorkspacePage>
                  <OperationsTab
                    grid={snapshot.grid}
                    probability={probability}
                    recommendation={recommendation}
                    lastUpdated={snapshot.weather.timestamp}
                  />
                </WorkspacePage>
              ) : null}

              {activeTab === "weather" ? (
                <WorkspacePage>
                  <WeatherTab weather={snapshot.weather} forecastItems={snapshot.forecast.items} />
                </WorkspacePage>
              ) : null}

              {activeTab === "forecast" ? (
                <WorkspacePage>
                  <ForecastRiskTab
                    grid={snapshot.grid}
                    probability={probability}
                    recommendation={recommendation}
                    forecastItems={snapshot.forecast.items}
                    forecastTab={forecastTab}
                    onForecastTabChange={setForecastTab}
                  />
                </WorkspacePage>
              ) : null}

              {activeTab === "analytics" ? (
                <WorkspacePage>
                  <AnalyticsTab
                    grid={snapshot.grid}
                    probability={probability}
                    recommendation={recommendation}
                  />
                </WorkspacePage>
              ) : null}
            </div>
          </div>
        </section>
      </div>
    </Shell>
  );
}

function Shell({
  children,
  lastUpdated,
  systemStatus,
  gridStatus,
}: {
  children?: ReactNode;
  lastUpdated: string | null;
  systemStatus: string;
  gridStatus?: string;
}) {
  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-[radial-gradient(circle_at_top,_rgba(14,116,144,0.18),_transparent_36%),linear-gradient(180deg,#020617_0%,#020617_100%)] text-slate-100">
      <Header lastUpdated={lastUpdated} systemStatus={systemStatus} gridStatus={gridStatus} />
      <main className="flex w-full min-w-0 flex-1 min-h-0 overflow-hidden px-4 py-2.5 lg:px-6">
        {children}
      </main>
    </div>
  );
}

function TabBar({
  activeTab,
  onChange,
}: {
  activeTab: DashboardTab;
  onChange: (tab: DashboardTab) => void;
}) {
  const tabs: Array<{ id: DashboardTab; label: string }> = [
    { id: "home", label: "Home" },
    { id: "operations", label: "Operations" },
    { id: "weather", label: "Weather" },
    { id: "forecast", label: "Forecast & Risk" },
    { id: "analytics", label: "Analytics" },
  ];

  return (
    <div className="grid w-full min-w-0 grid-cols-2 gap-2 rounded-2xl border border-slate-800 bg-slate-950/50 p-1.5 md:grid-cols-3 xl:grid-cols-5">
      {tabs.map((tab) => {
        const selected = tab.id === activeTab;
        return (
          <button
            key={tab.id}
            type="button"
            onClick={() => onChange(tab.id)}
            className={`rounded-xl px-3 py-2 text-sm font-semibold transition ${
              selected
                ? "bg-cyan-500/15 text-cyan-100 shadow-inner shadow-cyan-500/10"
                : "text-slate-300 hover:bg-slate-900/70 hover:text-white"
            }`}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

function ForecastSubTabBar({
  activeTab,
  onChange,
}: {
  activeTab: ForecastTab;
  onChange: (tab: ForecastTab) => void;
}) {
  const tabs: Array<{ id: ForecastTab; label: string }> = [
    { id: "demand", label: "Demand Forecast" },
    { id: "risk", label: "Risk Gauge" },
    { id: "guidance", label: "Operational Guidance" },
  ];

  return (
    <div className="grid w-full min-w-0 grid-cols-3 gap-2 rounded-2xl border border-slate-800 bg-slate-950/50 p-1.5">
      {tabs.map((tab) => {
        const selected = tab.id === activeTab;
        return (
          <button
            key={tab.id}
            type="button"
            onClick={() => onChange(tab.id)}
            className={`rounded-xl px-2 py-2 text-[11px] font-semibold uppercase tracking-[0.14em] transition sm:text-xs ${
              selected
                ? "bg-cyan-500/15 text-cyan-100 shadow-inner shadow-cyan-500/10"
                : "text-slate-300 hover:bg-slate-900/70 hover:text-white"
            }`}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

function WorkspacePage({ children }: { children: ReactNode }) {
  return <div className="workspace-page">{children}</div>;
}

function HomeTab({
  grid,
  weather,
  probability,
  recommendation,
  forecastItems,
}: {
  grid: DashboardSnapshot["grid"];
  weather: DashboardSnapshot["weather"];
  probability: DashboardSnapshot["probability"];
  recommendation: DashboardSnapshot["recommendation"];
  forecastItems: ForecastData[];
}) {
  return (
    <>
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
        <SummaryTile label="Demand" value={`${grid.current_demand_mw.toFixed(0)} MW`} tone="cyan" />
        <SummaryTile label="Generation" value={`${grid.current_generation_mw.toFixed(0)} MW`} tone="emerald" />
        <SummaryTile label="Reserve Margin" value={`${grid.reserve_margin_percent.toFixed(1)}%`} tone="amber" />
        <SummaryTile label="Probability" value={probability.probability_score.toFixed(2)} tone="rose" />
        <SummaryTile label="Action" value={recommendation.recommendation} tone="slate" compactValue />
      </div>

      <div className="grid min-h-0 flex-1 gap-2.5 xl:grid-cols-[minmax(0,1.35fr)_minmax(320px,0.65fr)]">
        <DecisionCard recommendation={recommendation} probability={probability} />

        <PanelCard title="Operating Drivers" className="h-full min-h-0">
          <div className="grid h-full min-h-0 content-start gap-2 text-sm text-slate-200">
            <MiniMetric label="Grid Status" value={grid.grid_status} />
            <MiniMetric label="Demand Period" value={grid.demand_period} />
            <MiniMetric label="Temperature" value={`${weather.temperature_c.toFixed(1)}°C`} />
            <MiniMetric label="Humidity" value={`${weather.humidity_percent.toFixed(0)}%`} />
            <MiniMetric label="Rainfall" value={`${weather.rainfall_mm_hr.toFixed(1)} mm/hr`} />
            <MiniMetric label="Wind" value={`${weather.wind_speed_kmh.toFixed(1)} km/h`} />
          </div>
        </PanelCard>
      </div>

      <div className="grid gap-2.5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)]">
        <MiniMetric label="30m Demand Forecast" value={`${probability.forecast_demand_30m.toFixed(0)} MW`} />
        <MiniMetric label="60m Demand Forecast" value={`${probability.forecast_demand_60m.toFixed(0)} MW`} />
        <MiniMetric
          label="Next Weather Period"
          value={forecastItems[0] ? `${forecastItems[0].temperature_c.toFixed(0)}°C, ${forecastItems[0].cloud_cover_percent.toFixed(0)}% cloud` : "--"}
        />
      </div>
    </>
  );
}

function DecisionCard({
  recommendation,
  probability,
}: {
  recommendation: DashboardSnapshot["recommendation"];
  probability: DashboardSnapshot["probability"];
}) {
  return (
    <div className="flex h-full min-h-0 w-full min-w-0 flex-col rounded-2xl border border-cyan-500/15 bg-slate-900/80 p-4 shadow-[0_0_34px_rgba(8,145,178,0.08)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">
            Operator Decision
          </p>
          <h2 className="mt-2 text-2xl font-semibold text-white">
            {recommendation.recommendation}
          </h2>
        </div>
        <span
          className={`rounded-full border px-3 py-1.5 text-xs font-semibold ${
            recommendation.risk_level === "HIGH"
              ? "border-rose-500/40 bg-rose-500/10 text-rose-200"
              : recommendation.risk_level === "MEDIUM"
                ? "border-amber-500/40 bg-amber-500/10 text-amber-200"
                : "border-emerald-500/40 bg-emerald-500/10 text-emerald-200"
          }`}
        >
          {recommendation.risk_level}
        </span>
      </div>

      <div className="mt-4 grid gap-2.5 sm:grid-cols-3">
        <MiniMetric label="Probability Score" value={recommendation.probability_score.toFixed(2)} />
        <MiniMetric label="Risk Level" value={probability.risk_level} />
        <MiniMetric label="Reserve Impact" value={probability.reason} />
      </div>

      <div className="mt-4 min-h-0 flex-1 rounded-xl border border-slate-800 bg-slate-950/60 p-3">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">
          Reason
        </p>
        <p className="mt-2 text-sm leading-6 text-slate-100">
          {recommendation.reason}
        </p>
        <ul className="mt-3 grid gap-2 text-sm text-slate-200">
          {(recommendation.factors.slice(0, 3).length > 0
            ? recommendation.factors.slice(0, 3)
            : [recommendation.reason]).map((factor, index) => (
            <li key={`${factor}-${index}`} className="flex gap-2 rounded-lg border border-slate-800 bg-slate-900/70 px-3 py-2">
              <span className="font-semibold text-cyan-300">{index + 1}.</span>
              <span className="min-w-0 flex-1 break-words">{factor}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function OperationsTab({
  grid,
  probability,
  recommendation,
  lastUpdated,
}: {
  grid: DashboardSnapshot["grid"];
  probability: DashboardSnapshot["probability"];
  recommendation: DashboardSnapshot["recommendation"];
  lastUpdated: string | null;
}) {
  return (
    <>
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
        <SummaryTile label="Total Demand" value={`${grid.current_demand_mw.toFixed(0)} MW`} tone="cyan" />
        <SummaryTile
          label="Total Generation"
          value={`${grid.current_generation_mw.toFixed(0)} MW`}
          tone="emerald"
        />
        <SummaryTile
          label="Reserve Margin"
          value={`${grid.reserve_margin_percent.toFixed(1)}%`}
          tone="amber"
        />
        <SummaryTile label="Probability Score" value={probability.probability_score.toFixed(2)} tone="rose" />
        <SummaryTile
          label="Recommended Action"
          value={recommendation.recommendation}
          tone="slate"
          compactValue
        />
      </div>

      <div className="grid min-h-0 flex-1 gap-2.5 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
        <PanelCard title="Operations Summary">
          <div className="grid gap-2 sm:grid-cols-2">
            <MiniMetric label="Grid Status" value={grid.grid_status} />
            <MiniMetric label="Demand Period" value={grid.demand_period} />
            <MiniMetric label="Source" value={grid.source_provider} />
            <MiniMetric label="Last Updated" value={formatTimestamp(lastUpdated)} />
          </div>
        </PanelCard>

        <PanelCard title="Control Strip">
          <div className="space-y-2 text-sm text-slate-200">
            <StatusLine label="Grid Status" value={grid.grid_status} />
            <StatusLine label="Probability" value={probability.probability_score.toFixed(2)} />
            <StatusLine label="Recommendation" value={recommendation.recommendation} />
          </div>
        </PanelCard>
      </div>
    </>
  );
}

function WeatherTab({
  weather,
  forecastItems,
}: {
  weather: DashboardSnapshot["weather"];
  forecastItems: ForecastData[];
}) {
  return (
    <div className="grid min-h-0 w-full min-w-0 flex-1 gap-2.5 xl:grid-cols-2">
      <CurrentConditions weather={weather} className="h-full min-h-0 w-full min-w-0" />
      <PanelCard title="Next 6 Hours" className="h-full min-h-0 w-full min-w-0">
        <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-slate-800 bg-slate-950/60">
          <div className="grid grid-cols-[1fr_auto_auto] gap-2 border-b border-slate-800 px-3 py-2 text-[11px] uppercase tracking-[0.14em] text-slate-400">
            <span>Time</span>
            <span>Temp</span>
            <span>Cloud</span>
          </div>
          <div className="divide-y divide-slate-800 overflow-hidden text-sm text-slate-100">
            {forecastItems.slice(0, 6).map((period) => (
              <ForecastRow key={period.forecast_timestamp} period={period} />
            ))}
          </div>
        </div>
      </PanelCard>
    </div>
  );
}

function ForecastRiskTab({
  grid,
  probability,
  recommendation,
  forecastItems,
  forecastTab,
  onForecastTabChange,
}: {
  grid: DashboardSnapshot["grid"];
  probability: DashboardSnapshot["probability"];
  recommendation: DashboardSnapshot["recommendation"];
  forecastItems: ForecastData[];
  forecastTab: ForecastTab;
  onForecastTabChange: (tab: ForecastTab) => void;
}) {
  return (
    <div className="flex h-full min-h-0 w-full min-w-0 flex-1 flex-col gap-2.5 overflow-hidden">
      <ForecastSubTabBar activeTab={forecastTab} onChange={onForecastTabChange} />

      <div className="min-h-0 flex-1 w-full min-w-0 overflow-hidden">
        {forecastTab === "demand" ? (
          <div className="grid h-full min-h-0 w-full min-w-0 grid-cols-1 gap-2.5 xl:grid-cols-2">
            <DemandForecastChart
              gridStatus={grid}
              probability={probability}
              className="h-full min-h-0 w-full min-w-0"
            />
            <PanelCard title="Demand Snapshot" className="h-full min-h-0 w-full min-w-0">
              <div className="grid gap-2 text-sm text-slate-200">
                <MiniMetric label="Current Demand" value={`${grid.current_demand_mw.toFixed(0)} MW`} />
                <MiniMetric label="30m Forecast" value={`${probability.forecast_demand_30m.toFixed(0)} MW`} />
                <MiniMetric label="60m Forecast" value={`${probability.forecast_demand_60m.toFixed(0)} MW`} />
                <MiniMetric label="Risk Level" value={probability.risk_level} />
              </div>
            </PanelCard>
          </div>
        ) : null}

        {forecastTab === "risk" ? (
          <div className="grid h-full min-h-0 w-full min-w-0 grid-cols-1 gap-2.5 xl:grid-cols-2">
            <ProbabilityGauge probability={probability} className="h-full min-h-0 w-full min-w-0" />
            <PanelCard title="Risk Context" className="h-full min-h-0 w-full min-w-0">
              <div className="space-y-2 text-sm text-slate-200">
                <StatusLine label="Risk Level" value={probability.risk_level} />
                <StatusLine label="Score" value={probability.probability_score.toFixed(2)} />
                <StatusLine label="Reason" value={probability.reason} />
              </div>
            </PanelCard>
          </div>
        ) : null}

        {forecastTab === "guidance" ? (
          <div className="grid h-full min-h-0 w-full min-w-0 grid-cols-1 gap-2.5 xl:grid-cols-2">
            <RecommendationCard recommendation={recommendation} className="h-full min-h-0 w-full min-w-0" />
            <PanelCard title="Forecast Context" className="h-full min-h-0 w-full min-w-0">
              <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-slate-800 bg-slate-950/60">
                <div className="grid grid-cols-[1fr_auto_auto] gap-2 border-b border-slate-800 px-3 py-2 text-[11px] uppercase tracking-[0.14em] text-slate-400">
                  <span>Time</span>
                  <span>Temp</span>
                  <span>Cloud</span>
                </div>
                <div className="divide-y divide-slate-800 overflow-hidden text-sm text-slate-100">
                  {forecastItems.slice(0, 6).map((period) => (
                    <ForecastRow key={period.forecast_timestamp} period={period} />
                  ))}
                </div>
              </div>
            </PanelCard>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function AnalyticsTab({
  grid,
  probability,
  recommendation,
}: {
  grid: DashboardSnapshot["grid"];
  probability: DashboardSnapshot["probability"];
  recommendation: DashboardSnapshot["recommendation"];
}) {
  return (
    <div className="flex h-full min-h-0 w-full min-w-0 flex-1 flex-col gap-2.5 overflow-hidden">
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        <MiniMetric label="Demand" value={`${grid.current_demand_mw.toFixed(0)} MW`} />
        <MiniMetric label="Generation" value={`${grid.current_generation_mw.toFixed(0)} MW`} />
        <MiniMetric label="Probability" value={probability.probability_score.toFixed(2)} />
        <MiniMetric label="Action" value={recommendation.recommendation} />
      </div>

      <div className="grid min-h-0 flex-1 gap-2.5 xl:grid-cols-[minmax(0,1.25fr)_minmax(0,0.75fr)]">
        <PanelCard title="Analytics" className="h-full min-h-0">
          <div className="flex h-full min-h-0 items-start">
            <p className="text-sm text-slate-200">
              Future analytics and historical reporting will appear here.
            </p>
          </div>
        </PanelCard>

        <PanelCard title="Live Snapshot" className="h-full min-h-0">
          <div className="grid gap-2 text-sm text-slate-200">
            <StatusLine label="Grid Status" value={grid.grid_status} />
            <StatusLine label="Reserve Margin" value={`${grid.reserve_margin_percent.toFixed(1)}%`} />
            <StatusLine label="Risk Level" value={probability.risk_level} />
            <StatusLine label="Reason" value={recommendation.reason} />
          </div>
        </PanelCard>
      </div>
    </div>
  );
}

function PanelCard({
  title,
  children,
  className = "",
}: {
  title: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`flex h-full min-h-0 w-full min-w-0 flex-col rounded-2xl border border-cyan-500/15 bg-slate-900/80 p-3 shadow-[0_0_34px_rgba(8,145,178,0.08)] ${className}`}>
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">{title}</p>
      <div className="mt-2 min-h-0 flex-1">{children}</div>
    </div>
  );
}

function ForecastRow({ period }: { period: ForecastData }) {
  const time = new Date(period.forecast_timestamp).toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });

  return (
    <div className="grid grid-cols-[1fr_auto_auto] gap-2 px-3 py-2 text-sm">
      <span className="font-medium text-white">{time}</span>
      <span className="text-slate-200">{period.temperature_c.toFixed(0)}°C</span>
      <span className="text-slate-200">{period.cloud_cover_percent.toFixed(0)}%</span>
    </div>
  );
}

function StatusLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid gap-1 rounded-xl border border-slate-800 bg-slate-950/60 px-3 py-2 sm:grid-cols-[minmax(0,0.45fr)_minmax(0,0.55fr)] sm:items-start">
      <span className="text-slate-400">{label}</span>
      <span className="min-w-0 break-words font-semibold text-white">{value}</span>
    </div>
  );
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/60 px-3 py-2">
      <p className="text-[11px] uppercase tracking-[0.14em] text-slate-400">{label}</p>
      <p className="mt-1 min-w-0 break-words text-sm font-semibold text-white">{value}</p>
    </div>
  );
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

function LoadingState() {
  return (
    <div className="grid h-full min-h-0 w-full min-w-0 gap-3 xl:grid-cols-[clamp(300px,28vw,390px)_minmax(0,1fr)]">
      <SkeletonCard tall />
      <div className="flex min-h-0 flex-col gap-2.5 overflow-hidden rounded-2xl border border-cyan-500/10 bg-slate-900/60 p-2.5">
        <div className="grid grid-cols-2 gap-2 xl:grid-cols-5">
          <SkeletonTile />
          <SkeletonTile />
          <SkeletonTile />
          <SkeletonTile />
          <SkeletonTile />
        </div>
        <SkeletonCard />
      </div>
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
      className={`animate-pulse rounded-2xl border border-cyan-500/10 bg-slate-900/80 p-4 shadow-[0_0_34px_rgba(8,145,178,0.05)] ${className} ${
        tall ? "min-h-[38rem]" : "min-h-[12rem]"
      }`}
    >
      <div className="h-4 w-32 rounded bg-slate-800/70" />
      <div className="mt-4 h-6 w-56 rounded bg-slate-800/70" />
      <div className="mt-6 grid grid-cols-2 gap-3">
        <div className="h-16 rounded-lg bg-slate-800/70" />
        <div className="h-16 rounded-lg bg-slate-800/70" />
        <div className="h-16 rounded-lg bg-slate-800/70" />
        <div className="h-16 rounded-lg bg-slate-800/70" />
      </div>
    </div>
  );
}

function SkeletonTile() {
  return <div className="h-[5rem] rounded-2xl border border-slate-800 bg-slate-900/80" />;
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
      <div className="max-w-lg rounded-2xl border border-rose-500/30 bg-rose-500/10 p-6 text-center shadow-[0_0_30px_rgba(244,63,94,0.12)]">
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

function SummaryTile({
  label,
  value,
  tone,
  compactValue = false,
}: {
  label: string;
  value: string;
  tone: "cyan" | "emerald" | "amber" | "rose" | "slate";
  compactValue?: boolean;
}) {
  const toneClasses: Record<"cyan" | "emerald" | "amber" | "rose" | "slate", string> = {
    cyan: "border-cyan-500/20 bg-cyan-500/10 text-cyan-100",
    emerald: "border-emerald-500/20 bg-emerald-500/10 text-emerald-100",
    amber: "border-amber-500/20 bg-amber-500/10 text-amber-100",
    rose: "border-rose-500/20 bg-rose-500/10 text-rose-100",
    slate: "border-slate-700/80 bg-slate-950/55 text-slate-100",
  };

  return (
    <div className={`rounded-2xl border px-4 py-3 shadow-[0_0_24px_rgba(8,145,178,0.06)] ${toneClasses[tone]}`}>
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-300">
        {label}
      </p>
      <p
        className={`mt-2 min-w-0 break-words font-semibold text-white ${
          compactValue ? "text-lg" : "text-2xl"
        }`}
      >
        {value}
      </p>
    </div>
  );
}
