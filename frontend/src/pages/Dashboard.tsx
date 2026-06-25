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
type DashboardTab =
  | "home"
  | "operations"
  | "weather"
  | "demandForecast"
  | "riskGauge"
  | "operationalGuidance"
  | "analytics";

export default function Dashboard() {
  const [state, setState] = useState<LoadState>("loading");
  const [snapshot, setSnapshot] = useState<DashboardSnapshot | null>(null);
  const [error, setError] = useState<string>("");
  const [activeTab, setActiveTab] = useState<DashboardTab>("home");

  const loadSnapshot = useCallback(
    async (
      options: {
        forceRefresh?: boolean;
        showLoading?: boolean;
      } = {},
    ) => {
      const forceRefresh = options.forceRefresh ?? true;
      const showLoading = options.showLoading ?? true;

      if (showLoading) {
        setState("loading");
      }
      setError("");

      try {
        const data = await getDashboardSnapshot({ forceRefresh });
        setSnapshot(data);
        setState("ready");
      } catch (cause) {
        if (showLoading) {
          setSnapshot(null);
          setError(cause instanceof Error ? cause.message : "Failed to load dashboard snapshot");
          setState("error");
        }
      }
    },
    [],
  );

  useEffect(() => {
    void loadSnapshot({ forceRefresh: true, showLoading: true });
    const refreshInterval = window.setInterval(() => {
      void loadSnapshot({ forceRefresh: true, showLoading: false });
    }, 5 * 60 * 1000);

    return () => window.clearInterval(refreshInterval);
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

              {activeTab === "demandForecast" ? (
                <WorkspacePage>
                  <DemandForecastTab
                    grid={snapshot.grid}
                    probability={probability}
                    recommendation={recommendation}
                    forecastItems={snapshot.forecast.items}
                  />
                </WorkspacePage>
              ) : null}

              {activeTab === "riskGauge" ? (
                <WorkspacePage>
                  <RiskGaugeTab grid={snapshot.grid} probability={probability} />
                </WorkspacePage>
              ) : null}

              {activeTab === "operationalGuidance" ? (
                <WorkspacePage>
                  <OperationalGuidanceTab
                    recommendation={recommendation}
                    forecastItems={snapshot.forecast.items}
                  />
                </WorkspacePage>
              ) : null}

              {activeTab === "analytics" ? (
                <WorkspacePage>
                  <AnalyticsTab
                    grid={snapshot.grid}
                    weather={snapshot.weather}
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
  const tabs: Array<{ id: DashboardTab; label: string; shortLabel: string }> = [
    { id: "home", label: "Home", shortLabel: "Home" },
    { id: "operations", label: "Operations", shortLabel: "Operations" },
    { id: "weather", label: "Weather", shortLabel: "Weather" },
    { id: "demandForecast", label: "Demand Forecast", shortLabel: "Demand" },
    { id: "riskGauge", label: "Risk Gauge", shortLabel: "Risk" },
    { id: "operationalGuidance", label: "Operational Guidance", shortLabel: "Guidance" },
    { id: "analytics", label: "Analytics", shortLabel: "Analytics" },
  ];

  return (
    <div className="w-full min-w-0 overflow-x-auto rounded-2xl border border-slate-800 bg-slate-950/50 p-1.5">
      <div className="grid min-w-[46rem] grid-cols-7 gap-1.5">
      {tabs.map((tab) => {
        const selected = tab.id === activeTab;
        return (
          <button
            key={tab.id}
            type="button"
            onClick={() => onChange(tab.id)}
            title={tab.label}
            aria-label={tab.label}
            className={`min-h-[2.7rem] rounded-xl border px-2 py-2 text-[11px] font-semibold leading-tight transition md:text-xs ${
              selected
                ? "border-cyan-400/30 bg-cyan-500/18 text-cyan-100 shadow-inner shadow-cyan-500/10"
                : "border-slate-700/70 bg-slate-900/65 text-slate-300 hover:border-slate-500 hover:bg-slate-900/90 hover:text-white"
            }`}
          >
            <span className="block text-center">{tab.shortLabel}</span>
          </button>
        );
      })}
      </div>
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

      <div className="flex flex-wrap gap-2">
        <StatusChip label="Weather" value="Live" tone="emerald" />
        <StatusChip label="Forecast" value="Live" tone="cyan" />
        <StatusChip label="Grid" value="Live" tone="amber" />
      </div>

      <div className="grid min-h-0 flex-1 items-stretch gap-2.5 xl:grid-cols-2">
        <WeatherOverviewCard weather={weather} forecastItems={forecastItems} />

        <HomeForecastRiskCard grid={grid} probability={probability} />
      </div>
    </>
  );
}

function HomeForecastRiskCard({
  grid,
  probability,
}: {
  grid: DashboardSnapshot["grid"];
  probability: DashboardSnapshot["probability"];
}) {
  return (
    <div className="home-forecast-card flex h-full min-h-[26rem] w-full min-w-0 flex-col overflow-hidden rounded-2xl border border-cyan-500/15 bg-slate-900/80 p-2.5 shadow-[0_0_34px_rgba(8,145,178,0.08)]">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">
            Demand Forecast
          </p>
          <h2 className="mt-1 text-[0.98rem] font-semibold leading-tight text-white">
            700 to 1500 MW Window
          </h2>
        </div>
        <span className="rounded-full border border-slate-700 bg-slate-950/60 px-2.5 py-1 text-[11px] font-semibold text-slate-200">
          Live
        </span>
      </div>

      <DemandForecastChart
        gridStatus={grid}
        probability={probability}
        showHeader={false}
        showSummary={false}
        className="h-full min-h-[22rem] w-full min-w-0"
      />
    </div>
  );
}

function WeatherOverviewCard({
  weather,
  forecastItems,
}: {
  weather: DashboardSnapshot["weather"];
  forecastItems: ForecastData[];
}) {
  const leadForecast = forecastItems[0];

  return (
    <div className="home-weather-card flex h-full min-h-[26rem] w-full min-w-0 flex-col overflow-hidden rounded-2xl border border-cyan-500/15 bg-slate-900/80 p-2.5 shadow-[0_0_34px_rgba(8,145,178,0.08)]">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">
            Weather Drivers
          </p>
          <h2 className="mt-1 text-lg font-semibold leading-tight text-white">
            Current Weather Conditions
          </h2>
        </div>
        <span
          className={`rounded-full border px-3 py-1.5 text-xs font-semibold ${
            weather.rain_severity === "SEVERE"
              ? "border-rose-500/40 bg-rose-500/10 text-rose-200"
              : weather.rain_severity === "HEAVY"
                ? "border-amber-500/40 bg-amber-500/10 text-amber-200"
                : "border-emerald-500/40 bg-emerald-500/10 text-emerald-200"
          }`}
        >
          {weather.rain_severity}
        </span>
      </div>

      <div className="mt-3 grid min-h-0 flex-1 auto-rows-fr grid-cols-2 gap-2">
        <MiniMetric label="Temperature" value={`${weather.temperature_c.toFixed(1)}°C`} />
        <MiniMetric label="Humidity" value={`${weather.humidity_percent.toFixed(0)}%`} />
        <MiniMetric label="Rainfall" value={`${weather.rainfall_mm_hr.toFixed(1)} mm/hr`} />
        <MiniMetric label="Wind Speed" value={`${weather.wind_speed_kmh.toFixed(1)} km/h`} />
        <MiniMetric label="Cloud Cover" value={`${weather.cloud_cover_percent.toFixed(0)}%`} />
        <MiniMetric label="Heat Index" value={`${weather.heat_index_c.toFixed(1)}°C`} />
        <MiniMetric label="Condition" value={weather.weather_condition} />
        <MiniMetric label="Observed" value={formatTimestamp(weather.timestamp)} />
        <MiniMetric label="Provider" value={weather.provider_name} />
        <MiniMetric
          label="6h Outlook"
          value={leadForecast ? `${leadForecast.temperature_c.toFixed(0)}°C, ${leadForecast.cloud_cover_percent.toFixed(0)}% cloud` : "--"}
        />
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
        <RecommendationCard recommendation={recommendation} className="h-full min-h-0 w-full min-w-0" />

        <GridStatusCard gridStatus={grid} className="h-full min-h-0" />
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
    <div className="grid min-h-0 w-full min-w-0 flex-1 gap-2.5 xl:grid-cols-[minmax(0,0.35fr)_minmax(0,0.65fr)]">
      <CurrentConditions weather={weather} className="h-full min-h-0 w-full min-w-0" />
      <PanelCard title="Next 6 Hours" className="h-full min-h-0 w-full min-w-0">
        <div className="flex h-full min-h-0 flex-col gap-2">
          <div className="grid grid-cols-[1fr_auto_auto_auto] gap-2 border-b border-slate-800 px-3 py-2 text-[11px] uppercase tracking-[0.14em] text-slate-400">
            <span>Time</span>
            <span className="text-right">Temp</span>
            <span className="text-right">Rain</span>
            <span className="text-right">Cloud</span>
          </div>

          <div className="grid min-h-0 flex-1 auto-rows-fr gap-2 overflow-auto sm:grid-cols-2 xl:grid-cols-3">
            {forecastItems.slice(0, 6).map((period) => (
              <ForecastBlock key={period.forecast_timestamp} period={period} />
            ))}
          </div>

          <div className="border-t border-slate-800 px-3 py-2 text-[11px] text-slate-400">
            Live forecast snapshot updated {formatTimestamp(weather.timestamp)}
          </div>
        </div>
      </PanelCard>
    </div>
  );
}

function DemandForecastTab({
  grid,
  probability,
  recommendation,
}: {
  grid: DashboardSnapshot["grid"];
  probability: DashboardSnapshot["probability"];
  recommendation: DashboardSnapshot["recommendation"];
}) {
  return (
    <div className="grid h-full min-h-0 w-full min-w-0 grid-cols-1 gap-2.5 xl:grid-cols-2">
      <DemandForecastChart
        gridStatus={grid}
        probability={probability}
        className="h-full min-h-0 w-full min-w-0"
      />
      <PanelCard title="Demand Snapshot" className="h-full min-h-0 w-full min-w-0">
        <div className="grid h-full gap-2 text-sm text-slate-200">
          <MiniMetric label="Current Demand" value={`${grid.current_demand_mw.toFixed(0)} MW`} />
          <MiniMetric label="Current Generation" value={`${grid.current_generation_mw.toFixed(0)} MW`} />
          <MiniMetric label="Available Capacity" value={`${grid.total_available_capacity_mw.toFixed(0)} MW`} />
          <MiniMetric label="Reserve Margin" value={`${grid.reserve_margin_percent.toFixed(1)}%`} />
          <MiniMetric label="30m Forecast" value={`${probability.forecast_demand_30m.toFixed(0)} MW`} />
          <MiniMetric label="60m Forecast" value={`${probability.forecast_demand_60m.toFixed(0)} MW`} />
          <MiniMetric label="Risk Level" value={probability.risk_level} />
          <MiniMetric label="Action" value={recommendation.recommendation} />
        </div>
      </PanelCard>
    </div>
  );
}

function RiskGaugeTab({
  grid,
  probability,
}: {
  grid: DashboardSnapshot["grid"];
  probability: DashboardSnapshot["probability"];
}) {
  return (
    <div className="grid h-full min-h-0 w-full min-w-0 grid-cols-1 gap-2.5 xl:grid-cols-2">
      <ProbabilityGauge probability={probability} className="h-full min-h-0 w-full min-w-0" />
      <PanelCard title="Risk Context" className="h-full min-h-0 w-full min-w-0">
        <div className="grid h-full gap-2 text-sm text-slate-200">
          <StatusLine label="Risk Level" value={probability.risk_level} />
          <StatusLine label="Score" value={probability.probability_score.toFixed(2)} />
          <StatusLine label="30m Demand" value={`${probability.forecast_demand_30m.toFixed(0)} MW`} />
          <StatusLine label="60m Demand" value={`${probability.forecast_demand_60m.toFixed(0)} MW`} />
          <StatusLine label="Reason" value={probability.reason} />
          <StatusLine label="Sensitivity" value={`${grid.reserve_margin_percent.toFixed(1)}% reserve`} />
        </div>
      </PanelCard>
    </div>
  );
}

function OperationalGuidanceTab({
  recommendation,
  forecastItems,
}: {
  recommendation: DashboardSnapshot["recommendation"];
  forecastItems: ForecastData[];
}) {
  return (
    <div className="grid h-full min-h-0 w-full min-w-0 grid-cols-1 gap-2.5 xl:grid-cols-[minmax(0,0.35fr)_minmax(0,0.65fr)]">
      <RecommendationCard recommendation={recommendation} className="h-full min-h-0 w-full min-w-0" />
      <PanelCard title="Forecast Context" className="h-full min-h-0 w-full min-w-0">
        <div className="flex h-full min-h-0 flex-col gap-2">
          <div className="grid grid-cols-[1fr_auto_auto_auto] gap-2 border-b border-slate-800 px-3 py-2 text-[11px] uppercase tracking-[0.14em] text-slate-400">
            <span>Time</span>
            <span className="text-right">Temp</span>
            <span className="text-right">Rain</span>
            <span className="text-right">Cloud</span>
          </div>
          <div className="grid min-h-0 flex-1 auto-rows-fr gap-2 overflow-auto sm:grid-cols-2 xl:grid-cols-3">
            {forecastItems.slice(0, 6).map((period) => (
              <ForecastBlock key={period.forecast_timestamp} period={period} />
            ))}
          </div>
        </div>
      </PanelCard>
    </div>
  );
}

function AnalyticsTab({
  grid,
  probability,
  recommendation,
  weather,
}: {
  grid: DashboardSnapshot["grid"];
  probability: DashboardSnapshot["probability"];
  recommendation: DashboardSnapshot["recommendation"];
  weather: DashboardSnapshot["weather"];
}) {
  return (
    <div className="flex h-full min-h-0 w-full min-w-0 flex-1 flex-col gap-2.5 overflow-hidden">
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        <MiniMetric label="Demand" value={`${grid.current_demand_mw.toFixed(0)} MW`} />
        <MiniMetric label="Generation" value={`${grid.current_generation_mw.toFixed(0)} MW`} />
        <MiniMetric label="Probability" value={probability.probability_score.toFixed(2)} />
        <MiniMetric label="Action" value={recommendation.recommendation} />
      </div>

      <div className="grid min-h-0 flex-1 gap-2.5 xl:grid-cols-2">
        <GridStatusCard gridStatus={grid} className="h-full min-h-0" />
        <CurrentConditions weather={weather} className="h-full min-h-0 w-full min-w-0" />
        <PanelCard title="Live Snapshot" className="h-full min-h-0 xl:col-span-2">
          <div className="grid gap-2 text-sm text-slate-200 sm:grid-cols-2 xl:grid-cols-4">
            <MiniMetric label="Probability" value={probability.probability_score.toFixed(2)} />
            <MiniMetric label="Risk Level" value={probability.risk_level} />
            <MiniMetric label="Action" value={recommendation.recommendation} />
            <MiniMetric label="Last Updated" value={formatTimestamp(weather.timestamp)} />
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
    <div className={`flex h-full min-h-0 w-full min-w-0 flex-col rounded-2xl border border-cyan-500/15 bg-slate-900/80 p-2.5 shadow-[0_0_34px_rgba(8,145,178,0.08)] ${className}`}>
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">{title}</p>
      <div className="mt-1.5 min-h-0 flex-1">{children}</div>
    </div>
  );
}

function ForecastBlock({ period }: { period: ForecastData }) {
  const time = formatForecastTimestamp(period.forecast_timestamp);

  return (
    <div className="flex min-h-[7.5rem] flex-col rounded-xl border border-slate-800 bg-slate-950/60 p-2 shadow-inner shadow-black/20">
      <div className="flex items-start justify-between gap-2">
        <p className="min-w-0 text-[0.92rem] font-semibold leading-snug text-white">{time}</p>
        <span className="shrink-0 rounded-full border border-slate-700 bg-slate-900/80 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-300">
          {period.rain_severity}
        </span>
      </div>

      <div className="mt-2 grid flex-1 grid-cols-3 gap-1.5 text-[0.88rem]">
        <ForecastDatum label="Temp" value={`${period.temperature_c.toFixed(0)}°C`} />
        <ForecastDatum label="Humidity" value={`${period.humidity_percent.toFixed(0)}%`} />
        <ForecastDatum label="Rain" value={`${period.rainfall_mm_hr.toFixed(1)} mm/hr`} />
        <ForecastDatum label="Cloud" value={`${period.cloud_cover_percent.toFixed(0)}%`} />
        <ForecastDatum label="Wind" value={`${period.wind_speed_kmh.toFixed(0)} km/h`} />
        <ForecastDatum
          label="Chance"
          value={`${period.precipitation_probability_percent.toFixed(0)}%`}
        />
      </div>
    </div>
  );
}

function ForecastDatum({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-lg border border-slate-800 bg-slate-900/70 px-2 py-1">
      <p className="text-[9px] uppercase leading-none tracking-[0.12em] text-slate-400">
        {label}
      </p>
      <p className="mt-1 min-w-0 break-words text-[0.78rem] font-semibold leading-snug text-white">
        {value}
      </p>
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
    <div className="flex h-full min-h-[4.25rem] flex-col justify-between rounded-xl border border-slate-800 bg-slate-950/60 px-3 py-2">
      <p className="text-[11px] uppercase tracking-[0.14em] text-slate-400">{label}</p>
      <p className="mt-1 min-w-0 break-words text-sm font-semibold leading-snug text-white">{value}</p>
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

function formatForecastTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
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
    <div
      title={value}
      className={`flex min-h-[6.5rem] flex-col justify-between rounded-2xl border px-4 py-3 shadow-[0_0_24px_rgba(8,145,178,0.06)] ${toneClasses[tone]}`}
    >
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-300">
        {label}
      </p>
      <p
        className={`mt-2 min-w-0 break-words font-semibold text-white ${
          compactValue ? "truncate text-[0.98rem]" : "break-words text-2xl"
        }`}
      >
        {value}
      </p>
    </div>
  );
}

function StatusChip({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "cyan" | "emerald" | "amber" | "rose" | "slate";
}) {
  const toneClasses: Record<"cyan" | "emerald" | "amber" | "rose" | "slate", string> = {
    cyan: "border-cyan-500/20 bg-cyan-500/10 text-cyan-100",
    emerald: "border-emerald-500/20 bg-emerald-500/10 text-emerald-100",
    amber: "border-amber-500/20 bg-amber-500/10 text-amber-100",
    rose: "border-rose-500/20 bg-rose-500/10 text-rose-100",
    slate: "border-slate-700/80 bg-slate-950/55 text-slate-100",
  };

  return (
    <div className={`rounded-full border px-3 py-1 text-[11px] font-semibold ${toneClasses[tone]}`}>
      <span className="uppercase tracking-[0.18em] text-slate-300">{label}</span>
      <span className="ml-2">{value}</span>
    </div>
  );
}
