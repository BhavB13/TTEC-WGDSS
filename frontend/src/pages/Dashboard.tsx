import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import CurrentConditions from "../components/CurrentConditions";
import DemandForecastChart from "../components/DemandForecastChart";
import Header from "../components/Header";
import HistoricalDemandChart from "../components/HistoricalDemandChart";
import ProbabilityGauge from "../components/ProbabilityGauge";
import ReplayControlBar from "../components/ReplayControlBar";
import ReplayLoadChart from "../components/ReplayLoadChart";
import RiskTimelineChart from "../components/RiskTimelineChart";
import ScenarioComparisonChart from "../components/ScenarioComparisonChart";
import WeatherMap from "../components/WeatherMap";
import { controlReplay, getDashboardSnapshot } from "../services/api";
import type {
  CalibrationSnapshot,
  DashboardSnapshot,
  DemandForecastBundle,
  ForecastData,
  ModelStatus,
  ScadaStatus,
  ReplayDashboard,
} from "../types/dashboard";

type LoadState = "loading" | "ready" | "error";
type ThemeMode = "dark" | "light";
type DashboardTab =
  | "home"
  | "operations"
  | "weather"
  | "demandForecast"
  | "riskGauge"
  | "operationalGuidance"
  | "analytics";

const FALLBACK_WEATHER: DashboardSnapshot["weather"] = {
  timestamp: null,
  temperature_c: 0,
  humidity_percent: 0,
  rainfall_mm_hr: 0,
  cloud_cover_percent: 0,
  wind_speed_kmh: 0,
  weather_condition: "Unavailable",
  heat_index_c: 0,
  rain_severity: "DRY",
  wind_direction_deg: null,
  pressure_hpa: null,
  provider_name: "Unavailable",
};

const FALLBACK_GRID: DashboardSnapshot["grid"] = {
  timestamp: null,
  current_demand_mw: 0,
  current_generation_mw: 0,
  total_available_capacity_mw: 0,
  reserve_margin_percent: 0,
  spinning_reserve_mw: null,
  spinning_reserve_source: null,
  grid_status: "Unavailable",
  demand_period: "Unavailable",
  source_provider: "Unavailable",
  generation_units: [],
};

const FALLBACK_PROBABILITY: DashboardSnapshot["probability"] = {
  probability_score: 0,
  capacity_risk_percent: 0,
  risk_level: "UNAVAILABLE",
  capacity_status: "Unavailable",
  forecast_demand_30m: 0,
  forecast_demand_60m: 0,
  forecast_demand_mw: 0,
  forecast_uncertainty_mw: 0,
  forecast_tra_mw: 0,
  projected_reserve_mw: 0,
  reserve_surplus_mw: 0,
  reserve_deficit_mw: 0,
  uncertainty_source: "UNAVAILABLE",
  tra_projection_basis: "UNAVAILABLE",
  factors: [],
  reason: "No live probability data available.",
};

const FALLBACK_RECOMMENDATION: DashboardSnapshot["recommendation"] = {
  ...FALLBACK_PROBABILITY,
  recommendation: "NO ACTION REQUIRED",
};

export default function Dashboard() {
  const [state, setState] = useState<LoadState>("loading");
  const [theme, setTheme] = useState<ThemeMode>(() => {
    try {
      return window.localStorage.getItem("wgdss-theme") === "light"
        ? "light"
        : "dark";
    } catch {
      return "dark";
    }
  });
  const [snapshot, setSnapshot] = useState<DashboardSnapshot | null>(null);
  const [error, setError] = useState<string>("");
  const [refreshError, setRefreshError] = useState<string>("");
  const [activeTab, setActiveTab] = useState<DashboardTab>("home");
  const [replayBusy, setReplayBusy] = useState(false);

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
        setRefreshError("");
        setState("ready");
      } catch (cause) {
        if (showLoading) {
          setSnapshot(null);
          setError(cause instanceof Error ? cause.message : "Failed to load dashboard snapshot");
          setState("error");
        } else {
          setRefreshError(
            cause instanceof Error
              ? cause.message
              : "Background dashboard refresh failed",
          );
        }
      }
    },
    [],
  );

  useEffect(() => {
    void loadSnapshot({ forceRefresh: true, showLoading: true });
  }, [loadSnapshot]);

  useEffect(() => {
    const refreshInterval = window.setInterval(() => {
      void loadSnapshot({ forceRefresh: false, showLoading: false });
    }, snapshot?.replay ? 5_000 : 5 * 60 * 1000);
    return () => window.clearInterval(refreshInterval);
  }, [loadSnapshot, snapshot?.replay]);

  const handleReplayControl = useCallback(
    async (input: Parameters<typeof controlReplay>[0]) => {
      setReplayBusy(true);
      try {
        await controlReplay(input);
        await loadSnapshot({ forceRefresh: false, showLoading: false });
      } finally {
        setReplayBusy(false);
      }
    },
    [loadSnapshot],
  );

  useEffect(() => {
    try {
      window.localStorage.setItem("wgdss-theme", theme);
    } catch {
      // Theme preference is optional; the dashboard remains usable without storage.
    }
  }, [theme]);

  const systemStatus = useMemo(() => {
    if (!snapshot) {
      return state === "loading" ? "Loading" : "Unavailable";
    }
    return snapshot.grid.grid_status;
  }, [snapshot, state]);

  if (state === "loading") {
    return (
      <Shell
        lastUpdated={null}
        systemStatus="Loading"
        theme={theme}
        onThemeChange={setTheme}
      >
        <LoadingState />
      </Shell>
    );
  }

  if (state === "error" || !snapshot) {
    return (
      <Shell
        lastUpdated={null}
        systemStatus="Unavailable"
        theme={theme}
        onThemeChange={setTheme}
      >
        <ErrorState message={error} onRetry={loadSnapshot} />
      </Shell>
    );
  }

  const weather = snapshot.weather ?? FALLBACK_WEATHER;
  const grid = snapshot.grid ?? FALLBACK_GRID;
  const probability = snapshot.probability ?? FALLBACK_PROBABILITY;
  const recommendation = snapshot.recommendation ?? FALLBACK_RECOMMENDATION;
  const calibration = snapshot.calibration ?? null;
  const demandForecast = snapshot.demand_forecast ?? null;
  const modelStatus = snapshot.model_status ?? null;
  const scadaStatus = snapshot.scada_status ?? null;
  const dataQuality = snapshot.data_quality ?? {
    overall_status: "DEGRADED",
    weather_status: "UNKNOWN",
    grid_status: grid.source_provider.includes("Mock") ? "SIMULATED" : "UNKNOWN",
    calibration_status: calibration ? "CALIBRATED" : "UNAVAILABLE",
    weather_source: weather.provider_name,
    grid_source: grid.source_provider,
    is_stale: false,
    fallback_used: false,
    notes: ["Data-quality metadata was not supplied by the API"],
  };
  const forecastItems = Array.isArray(snapshot.forecast?.items)
    ? snapshot.forecast.items
    : [];
  const forecastReference = snapshot.replay?.status.cursor_at
    ? new Date(snapshot.replay.status.cursor_at)
    : new Date();
  const upcomingForecastItems = getUpcomingForecastItems(forecastItems, forecastReference, 6);

  return (
    <Shell
      lastUpdated={weather.timestamp}
      systemStatus={systemStatus}
      gridStatus={grid.grid_status}
      weatherStatus={dataQuality.weather_status}
      forecastStatus={dataQuality.weather_status}
      scenarioLabel={snapshot.replay?.summary.replay_month_label ?? calibration?.selected_scenario_label ?? "Typical Day"}
      dataQuality={dataQuality}
      refreshError={refreshError}
      theme={theme}
      onThemeChange={setTheme}
    >
      <div className="grid h-auto min-h-0 w-full min-w-0 max-w-full gap-3 xl:h-full xl:grid-cols-[clamp(300px,28vw,390px)_minmax(0,1fr)] xl:items-stretch">
        <section className="h-[28rem] min-h-0 min-w-0 xl:h-full xl:self-stretch">
          <WeatherMap
            className="h-full min-h-0"
            weather={weather}
          />
        </section>

        <section className="flex min-h-[42rem] w-full min-w-0 max-w-full flex-col overflow-visible rounded-2xl border border-cyan-500/15 bg-slate-900/60 p-2.5 shadow-[0_0_40px_rgba(8,145,178,0.06)] xl:min-h-0 xl:overflow-hidden">
          <div className="flex h-full min-h-0 w-full min-w-0 flex-col gap-2.5 overflow-hidden">
            <TabBar activeTab={activeTab} onChange={setActiveTab} />
            {snapshot.replay ? (
              <ReplayControlBar
                status={snapshot.replay.status}
                busy={replayBusy}
                onControl={handleReplayControl}
              />
            ) : null}

            <div className="min-h-0 flex-1 w-full min-w-0 overflow-visible xl:overflow-hidden">
              {activeTab === "home" ? (
                <WorkspacePage>
                  <HomeTab
                    grid={grid}
                    weather={weather}
                    probability={probability}
                    recommendation={recommendation}
                    forecastItems={upcomingForecastItems}
                    calibration={calibration}
                    theme={theme}
                    replay={snapshot.replay ?? null}
                  />
                </WorkspacePage>
              ) : null}

              {activeTab === "operations" ? (
                <WorkspacePage>
                  <OperationsTab
                    grid={grid}
                  />
                </WorkspacePage>
              ) : null}

              {activeTab === "weather" ? (
                <WorkspacePage>
                  <WeatherTab
                    weather={weather}
                    forecastItems={upcomingForecastItems}
                    qualityStatus={dataQuality.weather_status}
                  />
                </WorkspacePage>
              ) : null}

              {activeTab === "demandForecast" ? (
                <WorkspacePage>
                  <DemandForecastTab
                    grid={grid}
                    probability={probability}
                    calibration={calibration}
                    demandForecast={demandForecast}
                    theme={theme}
                    replay={snapshot.replay ?? null}
                  />
                </WorkspacePage>
              ) : null}

              {activeTab === "riskGauge" ? (
                <WorkspacePage>
                  <RiskGaugeTab probability={probability} theme={theme} />
                </WorkspacePage>
              ) : null}

              {activeTab === "operationalGuidance" ? (
                <WorkspacePage>
                  <OperationalGuidanceTab
                    recommendation={recommendation}
                  />
                </WorkspacePage>
              ) : null}

              {activeTab === "analytics" ? (
                <WorkspacePage>
                  <AnalyticsTab
                    calibration={calibration}
                    demandForecast={demandForecast}
                    modelStatus={modelStatus}
                    scadaStatus={scadaStatus}
                    theme={theme}
                    replay={snapshot.replay ?? null}
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
  weatherStatus,
  forecastStatus,
  scenarioLabel,
  dataQuality,
  refreshError,
  theme,
  onThemeChange,
}: {
  children?: ReactNode;
  lastUpdated: string | null;
  systemStatus: string;
  gridStatus?: string;
  weatherStatus?: string;
  forecastStatus?: string;
  scenarioLabel?: string;
  dataQuality?: DashboardSnapshot["data_quality"] | null;
  refreshError?: string;
  theme: ThemeMode;
  onThemeChange: (theme: ThemeMode) => void;
}) {
  return (
    <div className={`theme-${theme} flex min-h-dvh w-full max-w-full flex-col overflow-x-hidden overflow-y-visible bg-[radial-gradient(circle_at_top,_rgba(14,116,144,0.18),_transparent_36%),linear-gradient(180deg,#020617_0%,#020617_100%)] text-slate-100 xl:h-dvh xl:overflow-hidden`}>
      <Header
        lastUpdated={lastUpdated}
        systemStatus={systemStatus}
        gridStatus={gridStatus}
        weatherStatus={weatherStatus}
        forecastStatus={forecastStatus}
        scenarioLabel={scenarioLabel}
        dataQuality={dataQuality}
        refreshError={refreshError}
        theme={theme}
        onThemeChange={onThemeChange}
      />
      <main className="flex w-full min-w-0 max-w-full flex-1 min-h-0 overflow-visible px-4 py-2.5 lg:px-6 xl:overflow-hidden">
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
    { id: "home", label: "Operator Overview", shortLabel: "Overview" },
    { id: "operations", label: "Grid Operations", shortLabel: "Grid Ops" },
    { id: "weather", label: "Weather", shortLabel: "Weather" },
    { id: "demandForecast", label: "Demand Forecast", shortLabel: "Demand" },
    { id: "riskGauge", label: "Risk Gauge", shortLabel: "Risk" },
    { id: "operationalGuidance", label: "Operational Guidance", shortLabel: "Guidance" },
    { id: "analytics", label: "Analytics", shortLabel: "Analytics" },
  ];

  return (
    <div className="w-full min-w-0 max-w-full rounded-2xl border border-slate-800 bg-slate-950/50 p-1.5">
      <div className="grid min-w-0 grid-cols-4 gap-1.5 sm:grid-cols-7">
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
  calibration,
  theme,
  replay,
}: {
  grid: DashboardSnapshot["grid"];
  weather: DashboardSnapshot["weather"];
  probability: DashboardSnapshot["probability"];
  recommendation: DashboardSnapshot["recommendation"];
  forecastItems: ForecastData[];
  calibration: CalibrationSnapshot | null;
  theme: ThemeMode;
  replay: ReplayDashboard | null;
}) {
  if (replay) {
    return (
      <>
        <div className="grid gap-2 sm:grid-cols-3 xl:grid-cols-5">
          <SummaryTile label="Demand" value={`${grid.current_demand_mw.toFixed(0)} MW`} tone="cyan" />
          <SummaryTile
            label={generationMetricLabel(grid)}
            value={`${grid.current_generation_mw.toFixed(0)} MW`}
            tone="emerald"
          />
          <SummaryTile label="Available" value={`${grid.total_available_capacity_mw.toFixed(0)} MW`} tone="cyan" />
          <SummaryTile
            label="System Spin"
            value={formatSystemSpin(grid)}
            tone="amber"
          />
          <SummaryTile label="Capacity Risk" value={formatProbability(probability)} tone="rose" />
        </div>

        <div className="grid min-h-0 flex-1 gap-2.5 xl:grid-cols-[minmax(0,1.42fr)_minmax(18rem,0.58fr)]">
          <ReplayLoadChart replay={replay} theme={theme} compact />
          <ReplayWeatherPanel weather={weather} forecastItems={forecastItems} />
        </div>
      </>
    );
  }

  return (
    <>
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryTile label="Demand" value={`${grid.current_demand_mw.toFixed(0)} MW`} tone="cyan" />
        <SummaryTile
          label={generationMetricLabel(grid)}
          value={`${grid.current_generation_mw.toFixed(0)} MW`}
          tone="emerald"
        />
        <SummaryTile
          label="System Spin"
          value={formatSystemSpin(grid)}
          tone="amber"
        />
        <SummaryTile label="Capacity Risk" value={formatProbability(probability)} tone="rose" />
      </div>

      <div className="grid min-h-0 flex-1 items-stretch gap-2.5 xl:grid-cols-[minmax(0,1.22fr)_minmax(18rem,0.78fr)]">
        <DecisionBrief
          recommendation={recommendation}
        />
        <div className="grid min-h-0 gap-2.5 xl:grid-rows-2">
          <HomeForecastRiskCard grid={grid} probability={probability} theme={theme} />
          <WeatherOverviewCard weather={weather} forecastItems={forecastItems} />
        </div>
      </div>
    </>
  );
}

function ReplayWeatherPanel({
  weather,
  forecastItems,
}: {
  weather: DashboardSnapshot["weather"];
  forecastItems: ForecastData[];
}) {
  return (
    <PanelCard title="Weather · Current + 6 Hours" className="h-full min-h-0">
      <div className="flex h-full min-h-0 flex-col gap-2">
        <div className="grid grid-cols-3 gap-1.5">
          <MiniMetric label="Temperature" value={`${weather.temperature_c.toFixed(1)}°C`} />
          <MiniMetric label="Humidity" value={`${weather.humidity_percent.toFixed(0)}%`} />
          <MiniMetric label="Rain" value={`${weather.rainfall_mm_hr.toFixed(1)} mm/h`} />
          <MiniMetric label="Wind" value={`${weather.wind_speed_kmh.toFixed(0)} km/h`} />
          <MiniMetric label="Cloud" value={`${weather.cloud_cover_percent.toFixed(0)}%`} />
          <MiniMetric label="Pressure" value={weather.pressure_hpa != null ? `${weather.pressure_hpa.toFixed(0)} hPa` : "--"} />
        </div>
        <div className="min-h-0 flex-1 overflow-auto rounded-xl border border-slate-800 bg-slate-950/45">
          <table className="w-full table-fixed text-left text-[10px] tabular-nums">
            <thead className="sticky top-0 bg-slate-950 text-slate-400">
              <tr>
                <th className="px-2 py-1.5 font-medium">Time</th>
                <th className="px-2 py-1.5 font-medium">Temp</th>
                <th className="px-2 py-1.5 font-medium">Rain</th>
                <th className="px-2 py-1.5 font-medium">Cloud</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800 text-slate-200">
              {forecastItems.slice(0, 6).map((period) => (
                <tr key={period.forecast_timestamp}>
                  <td className="px-2 py-1.5">{formatHourOnly(period.forecast_timestamp)}</td>
                  <td className="px-2 py-1.5">{period.temperature_c.toFixed(1)}°</td>
                  <td className="px-2 py-1.5">{period.rainfall_mm_hr.toFixed(1)}</td>
                  <td className="px-2 py-1.5">{period.cloud_cover_percent.toFixed(0)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </PanelCard>
  );
}

function DecisionBrief({
  recommendation,
}: {
  recommendation: DashboardSnapshot["recommendation"];
}) {
  const factors = recommendation.factors.length > 0
    ? recommendation.factors.slice(0, 4)
    : [recommendation.reason];
  const actionTone =
    recommendation.capacity_status === "Add Generation"
      ? "border-rose-400/35 bg-rose-500/10 text-rose-100"
      : recommendation.capacity_status === "Prepare Generation"
        ? "border-orange-400/35 bg-orange-500/10 text-orange-100"
        : recommendation.capacity_status === "Watch"
        ? "border-amber-400/35 bg-amber-500/10 text-amber-100"
        : recommendation.capacity_status === "Unavailable"
          ? "border-slate-600 bg-slate-800/60 text-slate-200"
          : "border-emerald-400/35 bg-emerald-500/10 text-emerald-100";

  return (
    <section className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden rounded-2xl border border-cyan-500/20 bg-slate-900/85 p-3 shadow-[0_0_38px_rgba(8,145,178,0.1)]">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">
            Operator Decision
          </p>
          <h2 className="mt-1 text-lg font-semibold leading-tight text-white">
            Recommended Operating Posture
          </h2>
        </div>
        <span className={`shrink-0 rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] ${actionTone}`}>
          {recommendation.capacity_status}
        </span>
      </div>

      <div className={`mt-3 rounded-xl border p-4 text-center shadow-inner shadow-black/20 ${actionTone}`}>
        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-300">
          Recommended Action
        </p>
        <p className="mt-2 break-words text-xl font-semibold leading-tight text-white">
          {recommendation.recommendation}
        </p>
      </div>

      <div className="mt-3 grid grid-cols-3 gap-2">
        <MiniMetric label="Capacity Risk" value={formatProbability(recommendation)} />
        <MiniMetric label="30m Demand" value={`${recommendation.forecast_demand_30m.toFixed(0)} MW`} />
        <MiniMetric label="Projected Reserve" value={`${recommendation.projected_reserve_mw.toFixed(0)} MW`} />
      </div>

      <div className="mt-3 min-h-0 flex-1 overflow-auto">
        <p className="px-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400">
          Decision Basis
        </p>
        <ol className="mt-2 grid gap-1.5">
          {factors.map((factor, index) => (
            <li
              key={`${factor}-${index}`}
              className="grid min-w-0 grid-cols-[1.6rem_minmax(0,1fr)] items-start gap-2 rounded-lg border border-slate-800 bg-slate-950/55 px-2.5 py-2 text-sm leading-snug text-slate-200"
            >
              <span className="flex h-6 w-6 items-center justify-center rounded-full border border-cyan-500/30 bg-cyan-500/10 text-[10px] font-semibold text-cyan-200">
                {index + 1}
              </span>
              <span className="min-w-0 break-words">{factor}</span>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

function HomeForecastRiskCard({
  grid,
  probability,
  theme,
}: {
  grid: DashboardSnapshot["grid"];
  probability: DashboardSnapshot["probability"];
  theme: ThemeMode;
}) {
  const demandChange60 =
    probability.forecast_demand_60m - grid.current_demand_mw;
  const headroom60 =
    grid.total_available_capacity_mw - probability.forecast_demand_60m;

  return (
    <div className="home-forecast-card flex h-full min-h-0 w-full min-w-0 flex-col overflow-hidden rounded-2xl border border-cyan-500/15 bg-slate-900/80 p-2.5 shadow-[0_0_34px_rgba(8,145,178,0.08)]">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">
            Demand Outlook
          </p>
          <h2 className="mt-1 text-[0.94rem] font-semibold leading-tight text-white">
            Next 60 Minutes
          </h2>
        </div>
        <span className="rounded-full border border-slate-700 bg-slate-950/60 px-2.5 py-1 text-[11px] font-semibold text-slate-200">
          Live
        </span>
      </div>

      <div className="min-h-[10.5rem] flex-1">
        <DemandForecastChart
          gridStatus={grid}
          probability={probability}
          view="nearTerm"
          theme={theme}
          showHeader={false}
          showSummary={false}
          className="h-full min-h-[10.5rem] w-full min-w-0 p-1.5"
        />
      </div>

      <div className="mt-2 grid grid-cols-2 gap-1.5 sm:grid-cols-4">
        <MiniMetric label="Now" value={`${grid.current_demand_mw.toFixed(0)} MW`} />
        <MiniMetric
          label="30 Minute"
          value={`${probability.forecast_demand_30m.toFixed(0)} MW`}
        />
        <MiniMetric
          label="60 Minute"
          value={`${probability.forecast_demand_60m.toFixed(0)} MW`}
        />
        <MiniMetric label="60m Headroom" value={formatSignedMegawatts(headroom60)} />
      </div>

      <div className="mt-1.5 flex items-center justify-between gap-2 px-1 text-[10px] text-slate-400">
        <span>{grid.demand_period} demand period</span>
        <span className={demandChange60 > 0 ? "text-amber-200" : "text-emerald-200"}>
          {formatSignedMegawatts(demandChange60)} by 60m
        </span>
      </div>
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
    <div className="home-weather-card flex h-full min-h-0 w-full min-w-0 flex-col overflow-hidden rounded-2xl border border-cyan-500/15 bg-slate-900/80 p-2.5 shadow-[0_0_34px_rgba(8,145,178,0.08)]">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">
            Weather Drivers
          </p>
          <h2 className="mt-1 text-[0.98rem] font-semibold leading-tight text-white">
            Demand-Relevant Conditions
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

      <div className="mt-2 grid min-h-0 flex-1 auto-rows-fr grid-cols-2 gap-1.5">
        <MiniMetric label="Temperature" value={`${weather.temperature_c.toFixed(1)}°C`} />
        <MiniMetric label="Humidity" value={`${weather.humidity_percent.toFixed(0)}%`} />
        <MiniMetric label="Rainfall" value={`${weather.rainfall_mm_hr.toFixed(1)} mm/hr`} />
        <MiniMetric label="Wind Speed" value={`${weather.wind_speed_kmh.toFixed(1)} km/h`} />
        <MiniMetric
          label="Next Outlook"
          value={leadForecast ? `${leadForecast.temperature_c.toFixed(0)}°C, ${leadForecast.cloud_cover_percent.toFixed(0)}% cloud` : "--"}
        />
        <MiniMetric label="Condition" value={weather.weather_condition} />
      </div>
    </div>
  );
}

function OperationsTab({
  grid,
}: {
  grid: DashboardSnapshot["grid"];
}) {
  const generationBalance =
    grid.current_generation_mw - grid.current_demand_mw;
  const usesTraGeneration = isHistoricalScadaReplay(grid);
  const systemSpinMw = getSystemSpinMw(grid);
  const spinAdjustmentMw =
    systemSpinMw == null ? null : systemSpinMw - generationBalance;
  const generationUnits = Array.isArray(grid.generation_units)
    ? grid.generation_units
    : [];
  const stationDispatch = Array.from(
    generationUnits.reduce(
      (stations, unit) => {
        const existing = stations.get(unit.station_name) ?? {
          stationName: unit.station_name,
          outputMw: 0,
          availableMw: 0,
          onlineUnits: 0,
          totalUnits: 0,
        };
        existing.outputMw += unit.current_output_mw;
        existing.availableMw += unit.available_capacity_mw;
        existing.totalUnits += 1;
        if (unit.status.toUpperCase() === "ONLINE") {
          existing.onlineUnits += 1;
        }
        stations.set(unit.station_name, existing);
        return stations;
      },
      new Map<
        string,
        {
          stationName: string;
          outputMw: number;
          availableMw: number;
          onlineUnits: number;
          totalUnits: number;
        }
      >(),
    ).values(),
  );

  return (
    <>
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
        <SummaryTile label="Total Demand" value={`${grid.current_demand_mw.toFixed(0)} MW`} tone="cyan" />
        <SummaryTile
          label={usesTraGeneration ? "Total Generation (TRA)" : "Total Generation"}
          value={`${grid.current_generation_mw.toFixed(0)} MW`}
          tone="emerald"
        />
        <SummaryTile
          label="Available Capacity"
          value={`${grid.total_available_capacity_mw.toFixed(0)} MW`}
          tone="cyan"
        />
        <SummaryTile
          label="System Spin"
          value={formatSystemSpin(grid)}
          tone="amber"
        />
        <SummaryTile
          label="Grid Status"
          value={grid.grid_status}
          tone={grid.grid_status === "NORMAL" ? "emerald" : "rose"}
          compactValue
        />
      </div>

      <div className="grid min-h-0 flex-1 gap-2.5 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <PanelCard
          title="Station Dispatch"
          className="h-full min-h-0 w-full min-w-0"
        >
          <div className="grid h-full min-h-0 auto-rows-fr gap-2 overflow-auto">
            {stationDispatch.length > 0 ? (
              stationDispatch.map((station) => {
                const utilization =
                  station.availableMw > 0
                    ? (station.outputMw / station.availableMw) * 100
                    : 0;
                const stationHeadroom =
                  station.availableMw - station.outputMw;
                return (
                  <div
                    key={station.stationName}
                    className="grid min-h-[6.5rem] min-w-0 grid-rows-[auto_auto_auto] content-center gap-3 rounded-xl border border-slate-800 bg-slate-950/60 p-3 shadow-inner shadow-black/20"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="min-w-0 break-words text-sm font-semibold text-white">
                        {station.stationName}
                      </p>
                      <span className="shrink-0 rounded-full border border-emerald-500/25 bg-emerald-500/10 px-2 py-0.5 text-[9px] font-semibold text-emerald-200">
                        {station.onlineUnits}/{station.totalUnits} online
                      </span>
                    </div>
                    <div className="grid grid-cols-4 gap-2 text-center">
                      <StationDatum
                        label={usesTraGeneration ? "TRA Share" : "Output"}
                        value={`${station.outputMw.toFixed(0)} MW`}
                      />
                      <StationDatum label="Available" value={`${station.availableMw.toFixed(0)} MW`} />
                      <StationDatum label="Headroom" value={`${stationHeadroom.toFixed(0)} MW`} />
                      <StationDatum label="Utilization" value={`${utilization.toFixed(0)}%`} />
                    </div>
                    <UtilizationBar value={utilization} />
                  </div>
                );
              })
            ) : (
              <div className="flex min-h-[8rem] items-center justify-center rounded-xl border border-dashed border-slate-700 px-4 text-center text-sm text-slate-400 sm:col-span-2">
                Station dispatch data is unavailable.
              </div>
            )}
          </div>
        </PanelCard>

        <PanelCard
          title="Unit Readiness"
          className="h-full min-h-0 w-full min-w-0"
        >
          <div className="flex h-full min-h-0 flex-col gap-2">
            <div className="grid grid-cols-3 gap-2">
              <MiniMetric
                label={usesTraGeneration ? "TRA-Demand Gap" : "Generation-Demand Gap"}
                value={formatSignedMegawatts(generationBalance)}
              />
              <MiniMetric
                label="Corrected System Spin"
                value={formatSystemSpin(grid)}
              />
              <MiniMetric
                label="Spin Adjustment"
                value={
                  spinAdjustmentMw == null
                    ? "Unavailable"
                    : formatSignedMegawatts(spinAdjustmentMw)
                }
              />
            </div>

            <div className="min-h-0 flex-1 overflow-auto rounded-xl border border-slate-800 bg-slate-950/45">
              {generationUnits.length > 0 ? (
                <div className="grid h-full min-h-0 auto-rows-fr divide-y divide-slate-800">
                  {generationUnits.map((unit) => {
                    const utilization =
                      unit.available_capacity_mw > 0
                        ? (unit.current_output_mw / unit.available_capacity_mw) * 100
                        : 0;
                    const headroom =
                      unit.available_capacity_mw - unit.current_output_mw;

                    return (
                      <div
                        key={`${unit.station_name}-${unit.unit_name}`}
                        className="grid min-h-[5rem] min-w-0 grid-cols-[minmax(0,1fr)_minmax(14rem,0.8fr)] items-center gap-4 px-3 py-2"
                      >
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <p className="truncate text-[0.78rem] font-semibold text-white">
                              {unit.station_name} · {unit.unit_name}
                            </p>
                            <span
                              className={`shrink-0 rounded-full border px-2 py-0.5 text-[8px] font-semibold uppercase tracking-[0.08em] ${
                                unit.is_dispatchable
                                  ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-200"
                                  : "border-slate-700 bg-slate-900 text-slate-400"
                              }`}
                            >
                              {unit.is_dispatchable ? "Dispatchable" : "Fixed"}
                            </span>
                          </div>
                          <p className="mt-1 text-[9px] uppercase tracking-[0.1em] text-slate-500">
                            {unit.fuel_type} · {unit.status}
                          </p>
                          <div className="mt-2">
                            <UtilizationBar value={utilization} />
                          </div>
                        </div>

                        <div className="grid grid-cols-3 gap-2 text-center">
                          <StationDatum
                            label={usesTraGeneration ? "TRA Share" : "Output"}
                            value={`${unit.current_output_mw.toFixed(0)} MW`}
                          />
                          <StationDatum
                            label="Headroom"
                            value={`${headroom.toFixed(0)} MW`}
                          />
                          <StationDatum
                            label="Loading"
                            value={`${utilization.toFixed(0)}%`}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="flex h-full min-h-[5rem] items-center justify-center px-4 text-center text-sm text-slate-400">
                  Unit-level dispatch data is unavailable.
                </div>
              )}
            </div>

            <p className="truncate px-1 text-center text-[10px] text-slate-500">
              Source: {grid.source_provider}
            </p>
          </div>
        </PanelCard>
      </div>
    </>
  );
}

function WeatherTab({
  weather,
  forecastItems,
  qualityStatus,
}: {
  weather: DashboardSnapshot["weather"];
  forecastItems: ForecastData[];
  qualityStatus: string;
}) {
  return (
    <div className="grid min-h-0 w-full min-w-0 flex-1 gap-2.5 xl:grid-cols-[minmax(0,0.35fr)_minmax(0,0.65fr)]">
      <CurrentConditions
        weather={weather}
        qualityStatus={qualityStatus}
        className="h-full min-h-0 w-full min-w-0"
      />
      <PanelCard title="Next 6 Hours" className="h-full min-h-0 w-full min-w-0">
        <div className="flex h-full min-h-0 flex-col gap-2">
          {forecastItems.length > 0 ? (
            <div className="grid min-h-0 flex-1 auto-rows-fr gap-1.5 overflow-auto">
              {forecastItems.map((period) => (
                <GuidanceForecastRow
                  key={period.forecast_timestamp}
                  period={period}
                />
              ))}
            </div>
          ) : (
            <div className="flex min-h-0 flex-1 items-center justify-center rounded-xl border border-dashed border-slate-700 bg-slate-950/40 px-4 text-center text-sm text-slate-400">
              Six-hour weather guidance is temporarily unavailable.
            </div>
          )}

          <ForecastAttribution
            forecastItems={forecastItems}
            updatedAt={weather.timestamp}
          />
        </div>
      </PanelCard>
    </div>
  );
}

function DemandForecastTab({
  grid,
  probability,
  calibration,
  demandForecast,
  theme,
  replay,
}: {
  grid: DashboardSnapshot["grid"];
  probability: DashboardSnapshot["probability"];
  calibration: CalibrationSnapshot | null;
  demandForecast: DemandForecastBundle | null;
  theme: ThemeMode;
  replay: ReplayDashboard | null;
}) {
  const demandDelta30 = probability.forecast_demand_30m - grid.current_demand_mw;
  const demandDelta60 = probability.forecast_demand_60m - grid.current_demand_mw;

  return (
    <div className="grid h-full min-h-0 w-full min-w-0 grid-cols-1 gap-2 xl:grid-cols-[minmax(0,1fr)_clamp(15rem,25%,18rem)]">
      {replay ? (
        <ReplayLoadChart replay={replay} theme={theme} />
      ) : (
        <DemandForecastChart
          gridStatus={grid}
          probability={probability}
          calibration={calibration}
          modelForecast={demandForecast}
          theme={theme}
          className="h-full min-h-0 w-full min-w-0"
        />
      )}
      <PanelCard title="Demand Snapshot" className="h-full min-h-0 w-full min-w-0">
        <div className="grid h-full grid-cols-2 gap-1.5 text-sm text-slate-200">
          <MiniMetric label="Current Demand" value={`${grid.current_demand_mw.toFixed(0)} MW`} />
          <MiniMetric label="30m Forecast" value={`${probability.forecast_demand_30m.toFixed(0)} MW`} />
          <MiniMetric label="30m Change" value={formatSignedMegawatts(demandDelta30)} />
          <MiniMetric label="60m Forecast" value={`${probability.forecast_demand_60m.toFixed(0)} MW`} />
          <MiniMetric label="60m Change" value={formatSignedMegawatts(demandDelta60)} />
          <MiniMetric
            label="Profile Scenario"
            value={calibration?.selected_scenario_label ?? "Typical Day"}
          />
          <MiniMetric
            label="Profile Demand"
            value={
              calibration?.selected_demand_mw != null
                ? `${calibration.selected_demand_mw.toFixed(0)} MW`
                : "Unavailable"
            }
          />
          <MiniMetric
            label="Next Profile Hour"
            value={
              calibration?.selected_next_demand_mw != null
                ? `${calibration.selected_next_demand_mw.toFixed(0)} MW`
                : "Unavailable"
            }
          />
          {replay ? (
            <>
              <MiniMetric
                label="Historical Average"
                value={`${replay.summary.historical_average_demand_mw.toFixed(0)} MW`}
              />
              <MiniMetric
                label="Forecast Day Peak"
                value={`${replay.summary.current_day_peak_forecast_mw.toFixed(0)} MW`}
              />
            </>
          ) : null}
        </div>
      </PanelCard>
    </div>
  );
}

function RiskGaugeTab({
  probability,
  theme,
}: {
  probability: DashboardSnapshot["probability"];
  theme: ThemeMode;
}) {
  const [showAllDrivers, setShowAllDrivers] = useState(false);
  const fallbackFactors =
    Array.isArray(probability.factors) && probability.factors.length > 0
      ? probability.factors
      : [probability.reason];
  const drivers = probability.drivers?.length
    ? probability.drivers
    : fallbackFactors.map((label) => ({
        label,
        direction: legacyRiskDirection(label),
        category: "LEGACY",
      }));
  const increasingCount = drivers.filter(
    (driver) => driver.direction === "INCREASES_RISK",
  ).length;
  const reducingCount = drivers.filter(
    (driver) => driver.direction === "REDUCES_RISK",
  ).length;
  const warningCount = drivers.filter(
    (driver) => driver.direction === "QUALITY_WARNING",
  ).length;
  const contextCount = drivers.filter(
    (driver) => driver.direction === "CONTEXT",
  ).length;
  const topDrivers = selectTopRiskDrivers(drivers, 5);
  const visibleDrivers = showAllDrivers ? drivers : topDrivers;
  return (
    <div className="grid h-full min-h-0 w-full min-w-0 grid-rows-[minmax(0,1.08fr)_minmax(0,0.92fr)] gap-2.5 overflow-hidden">
      <div className="grid min-h-0 min-w-0 gap-2.5 xl:grid-cols-[minmax(17rem,0.36fr)_minmax(0,0.64fr)]">
        <ProbabilityGauge
          probability={probability}
          className="h-full min-h-0 w-full min-w-0"
        />
        <RiskTimelineChart
          probability={probability}
          theme={theme}
          className="h-full min-h-0 w-full min-w-0"
        />
      </div>

      <div className="grid min-h-0 min-w-0 gap-2.5 overflow-hidden xl:grid-cols-[minmax(0,1.08fr)_minmax(20rem,0.92fr)]">
        <PanelCard
          title="Capacity Risk Evidence"
          className="h-full min-h-0 w-full min-w-0"
        >
          <div className="grid h-full min-h-0 grid-cols-2 auto-rows-fr gap-1.5 sm:grid-cols-4">
            <MiniMetric
              label="Capacity Risk"
              value={formatCapacityRisk(probability)}
            />
            <MiniMetric
              label="Forecast Demand"
              value={`${probability.forecast_demand_mw.toFixed(1)} MW`}
            />
            <MiniMetric
              label="Forecast TRA"
              value={`${probability.forecast_tra_mw.toFixed(1)} MW`}
            />
            <MiniMetric
              label="Projected Reserve"
              value={`${probability.projected_reserve_mw.toFixed(1)} MW`}
            />
            <MiniMetric
              label="Required Reserve"
              value={`${(probability.required_reserve_mw ?? 30).toFixed(1)} MW`}
            />
            <MiniMetric
              label="Reserve Balance"
              value={formatReserveBalance(probability)}
            />
            <MiniMetric
              label="First Insufficiency"
              value={formatReserveInsufficiency(probability)}
            />
            <MiniMetric
              label="Forecast Error Sigma"
              value={`${probability.forecast_uncertainty_mw.toFixed(1)} MW`}
            />
          </div>
        </PanelCard>

        <PanelCard title="Risk Drivers" className="h-full min-h-0 w-full min-w-0">
          <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)_auto] gap-1.5">
            <div className="grid grid-cols-4 gap-1 text-center text-[8px] uppercase tracking-[0.06em]">
              <span className="rounded-lg border border-rose-500/25 bg-rose-500/10 px-1.5 py-1 text-rose-200">
                {increasingCount} raising
              </span>
              <span className="rounded-lg border border-emerald-500/25 bg-emerald-500/10 px-1.5 py-1 text-emerald-200">
                {reducingCount} reducing
              </span>
              <span className="rounded-lg border border-amber-500/25 bg-amber-500/10 px-1.5 py-1 text-amber-200">
                {warningCount} warnings
              </span>
              <span className="rounded-lg border border-slate-600/60 bg-slate-800/55 px-1.5 py-1 text-slate-300">
                {contextCount} context
              </span>
            </div>
            <ol className="min-h-0 space-y-1 overflow-auto pr-0.5">
              {visibleDrivers.map((driver, index) => (
                <li
                  key={`${driver.category}-${driver.label}-${index}`}
                  className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-950/55 px-2 py-1.5 text-[0.68rem] leading-snug text-slate-200"
                >
                  <span
                    className={`h-2 w-2 shrink-0 rounded-full ${riskDriverDot(driver.direction)}`}
                  />
                  <span className="min-w-0 flex-1 break-words">{driver.label}</span>
                  <span className="shrink-0 text-[8px] uppercase tracking-[0.08em] text-slate-500">
                    {driver.category.replace(/_/g, " ")}
                  </span>
                </li>
              ))}
            </ol>
            {drivers.length > 5 ? (
              <button
                type="button"
                onClick={() => setShowAllDrivers((current) => !current)}
                className="justify-self-end rounded-lg border border-cyan-500/25 bg-cyan-500/10 px-2.5 py-1 text-[10px] font-semibold text-cyan-100 hover:border-cyan-400/45 hover:bg-cyan-500/15"
              >
                {showAllDrivers ? "Show top 5" : `View all ${drivers.length}`}
              </button>
            ) : (
              <span className="text-right text-[9px] text-slate-500">
                {probability.formula_version ?? "Operating risk evidence"}
              </span>
            )}
          </div>
        </PanelCard>
      </div>
    </div>
  );
}

function legacyRiskDirection(
  factor: string,
): "INCREASES_RISK" | "REDUCES_RISK" | "CONTEXT" {
  const normalized = factor.toLowerCase();
  if (
    normalized.includes("decrease") ||
    normalized.includes("reduced") ||
    normalized.includes("lower expected")
  ) {
    return "REDUCES_RISK";
  }
  if (
    normalized.includes("increase") ||
    normalized.includes("higher") ||
    normalized.includes("below") ||
    normalized.includes("high ")
  ) {
    return "INCREASES_RISK";
  }
  return "CONTEXT";
}

function selectTopRiskDrivers(
  drivers: NonNullable<DashboardSnapshot["probability"]["drivers"]>,
  limit: number,
) {
  const selected: typeof drivers = [];
  const addFirst = (direction: string) => {
    const match = drivers.find(
      (driver) =>
        driver.direction === direction && !selected.includes(driver),
    );
    if (match) selected.push(match);
  };

  addFirst("INCREASES_RISK");
  addFirst("REDUCES_RISK");
  addFirst("QUALITY_WARNING");
  for (const driver of drivers) {
    if (selected.length >= limit) break;
    if (!selected.includes(driver)) selected.push(driver);
  }
  return selected;
}

function riskDriverDot(direction: string): string {
  if (direction === "INCREASES_RISK") return "bg-rose-400";
  if (direction === "REDUCES_RISK") return "bg-emerald-400";
  if (direction === "QUALITY_WARNING") return "bg-amber-400";
  return "bg-slate-400";
}

function formatCapacityRisk(
  probability: DashboardSnapshot["probability"],
): string {
  if (
    probability.risk_level === "UNAVAILABLE" ||
    probability.capacity_status === "Unavailable"
  ) {
    return "Unavailable";
  }
  return `${probability.capacity_risk_percent.toFixed(1)}%`;
}

function formatReserveBalance(
  probability: DashboardSnapshot["probability"],
): string {
  if (probability.reserve_surplus_mw >= 0) {
    return `+${probability.reserve_surplus_mw.toFixed(1)} MW`;
  }
  return `-${probability.reserve_deficit_mw.toFixed(1)} MW`;
}

function formatReserveInsufficiency(
  probability: DashboardSnapshot["probability"],
): string {
  if (probability.reserve_insufficient_at) {
    return formatShortDateTime(probability.reserve_insufficient_at);
  }
  const minutes = probability.reserve_insufficient_horizon_minutes;
  if (minutes == null) return "Not in horizon";
  return minutes < 60 ? `In ${minutes} min` : `In ${minutes / 60} hr`;
}

function formatEnumLabel(value: string): string {
  return value.replace(/_/g, " ");
}

function OperationalGuidanceTab({
  recommendation,
}: {
  recommendation: DashboardSnapshot["recommendation"];
}) {
  const factors = recommendation.factors.slice(0, 6);
  const decisionAvailable = recommendation.risk_level !== "UNAVAILABLE";
  const dispatchAction = recommendation.decision_action ?? recommendation.recommendation;
  const reserveTarget = recommendation.required_reserve_mw ?? 30;
  const reserveHealthy = recommendation.reserve_surplus_mw >= 0;

  return (
    <div className="grid h-full min-h-0 w-full min-w-0 gap-2.5 overflow-hidden xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div className="flex min-h-0 flex-col gap-2 overflow-hidden rounded-2xl border border-cyan-500/15 bg-slate-900/80 p-2.5 shadow-[0_0_34px_rgba(8,145,178,0.08)]">
        <div className={`rounded-xl border px-4 py-3 text-center ${decisionAvailable ? "border-cyan-400/30 bg-cyan-500/10" : "border-slate-700 bg-slate-950/60"}`}>
          <p className="text-[9px] font-semibold uppercase tracking-[0.16em] text-slate-400">Dispatch Decision</p>
          <p className="mt-1 break-words text-lg font-semibold text-white">{dispatchAction}</p>
          <p className="mt-1 text-[10px] text-cyan-100">{recommendation.generator_set ?? "No generator set selected"}</p>
        </div>
        <ol className="grid min-h-0 flex-1 auto-rows-fr gap-1.5 overflow-auto sm:grid-cols-2">
          {factors.map((factor, index) => (
            <li key={`${factor}-${index}`} className="flex min-h-[3.5rem] items-center gap-2 rounded-xl border border-slate-800 bg-slate-950/60 px-2.5 py-2 text-[0.72rem] leading-snug text-slate-200">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-cyan-500/30 bg-cyan-500/10 text-[9px] font-semibold text-cyan-200">{index + 1}</span>
              <span className="min-w-0 break-words">{factor}</span>
            </li>
          ))}
        </ol>
      </div>

      <div className="grid min-h-0 grid-cols-2 auto-rows-fr gap-2 rounded-2xl border border-cyan-500/15 bg-slate-900/80 p-2.5 shadow-[0_0_34px_rgba(8,145,178,0.08)]">
            <GuidanceThreshold
              label="Projected Reserve"
              value={`${recommendation.projected_reserve_mw.toFixed(1)} MW`}
              context={`Forecast TRA ${recommendation.forecast_tra_mw.toFixed(1)} minus demand ${recommendation.forecast_demand_mw.toFixed(1)} MW`}
              healthy={decisionAvailable && reserveHealthy}
            />
            <GuidanceThreshold
              label="Required Reserve"
              value={`${reserveTarget.toFixed(1)} MW`}
              context="Configured operating reserve target"
              healthy={decisionAvailable}
            />
            <GuidanceThreshold
              label="Reserve Balance"
              value={formatReserveBalance(recommendation)}
              context={reserveHealthy ? "Surplus above target" : "Deficit below target"}
              healthy={decisionAvailable && reserveHealthy}
            />
            <GuidanceThreshold
              label="Capacity Risk"
              value={formatCapacityRisk(recommendation)}
              context={`${recommendation.capacity_status} - ${formatReserveInsufficiency(recommendation)}`}
              healthy={recommendation.capacity_status === "Normal"}
            />
      </div>
    </div>
  );
}

function GuidanceThreshold({
  label,
  value,
  context,
  healthy,
}: {
  label: string;
  value: string;
  context: string;
  healthy: boolean;
}) {
  return (
    <div
      className={`flex min-w-0 flex-col items-center justify-center rounded-xl border px-2 py-2 text-center ${
        healthy
          ? "border-emerald-500/20 bg-emerald-500/10"
          : "border-rose-500/25 bg-rose-500/10"
      }`}
    >
      <p className="text-[9px] uppercase tracking-[0.1em] text-slate-400">{label}</p>
      <p className={`mt-1 text-sm font-semibold ${healthy ? "text-emerald-100" : "text-rose-100"}`}>
        {value}
      </p>
      <p className="mt-1 break-words text-[9px] leading-tight text-slate-500">
        {context}
      </p>
    </div>
  );
}

function GuidanceForecastRow({ period }: { period: ForecastData }) {
  const verified = (period.source_count ?? 1) > 1;

  return (
    <div className="grid min-h-[3.75rem] min-w-0 grid-cols-[minmax(7.5rem,1.35fr)_repeat(6,minmax(0,1fr))] items-center gap-1.5 rounded-xl border border-slate-800 bg-slate-950/60 px-2.5 py-1.5 shadow-inner shadow-black/20">
      <div className="min-w-0">
        <p className="truncate text-[0.8rem] font-semibold text-white">
          {formatGuidanceForecastTimestamp(period.forecast_timestamp)}
        </p>
        <p
          className={`mt-0.5 text-[9px] font-semibold uppercase tracking-[0.1em] ${
            verified ? "text-emerald-300" : "text-amber-300"
          }`}
          title={period.source_names?.join(" + ") ?? period.provider_name}
        >
          {verified ? `${period.source_count} sources` : "single source"}
        </p>
      </div>
      <GuidanceDatum label="Temp" value={`${period.temperature_c.toFixed(0)}°C`} />
      <GuidanceDatum label="Humidity" value={`${period.humidity_percent.toFixed(0)}%`} />
      <GuidanceDatum label="Rain" value={`${period.rainfall_mm_hr.toFixed(1)} mm/h`} />
      <GuidanceDatum label="Cloud" value={`${period.cloud_cover_percent.toFixed(0)}%`} />
      <GuidanceDatum label="Wind" value={`${period.wind_speed_kmh.toFixed(0)} km/h`} />
      <GuidanceDatum
        label="Chance"
        value={`${period.precipitation_probability_percent.toFixed(0)}%`}
      />
    </div>
  );
}

function GuidanceDatum({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 border-l border-slate-800 px-1 text-center">
      <p className="text-[8px] uppercase tracking-[0.1em] text-slate-500">{label}</p>
      <p className="mt-0.5 break-words text-[0.72rem] font-semibold leading-tight text-slate-100">
        {value}
      </p>
    </div>
  );
}

function StationDatum({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="text-[8px] uppercase tracking-[0.1em] text-slate-500">{label}</p>
      <p className="mt-1 break-words text-[0.72rem] font-semibold leading-tight text-slate-100">
        {value}
      </p>
    </div>
  );
}

function UtilizationBar({ value }: { value: number }) {
  const boundedValue = Math.max(0, Math.min(100, value));
  const tone =
    boundedValue >= 90
      ? "bg-amber-400"
      : boundedValue >= 70
        ? "bg-cyan-400"
        : "bg-emerald-400";

  return (
    <div className="h-1.5 overflow-hidden rounded-full bg-slate-800">
      <div
        className={`h-full rounded-full transition-[width] duration-300 ${tone}`}
        style={{ width: `${boundedValue}%` }}
      />
    </div>
  );
}

function AnalyticsTab({
  calibration,
  demandForecast,
  modelStatus,
  scadaStatus,
  theme,
  replay,
}: {
  calibration: CalibrationSnapshot | null;
  demandForecast: DemandForecastBundle | null;
  modelStatus: ModelStatus | null;
  scadaStatus: ScadaStatus | null;
  theme: ThemeMode;
  replay: ReplayDashboard | null;
}) {
  return (
    <div className="grid h-full min-h-0 w-full min-w-0 gap-2.5 xl:grid-cols-[minmax(260px,0.36fr)_minmax(0,0.64fr)]">
      <div className="grid h-full min-h-0 gap-2.5">
        <PanelCard title={replay ? "Historical Dataset" : "Calibration Summary"} className="min-h-0">
          <div className="grid h-full min-h-0 auto-rows-fr grid-cols-2 gap-2">
            {replay ? (
              <>
                <MiniMetric label="Historical Months" value={`${replay.summary.historical_months}`} />
                <MiniMetric label="Historical Records" value={replay.summary.historical_record_count.toLocaleString()} />
                <MiniMetric label="Average Demand" value={`${replay.summary.historical_average_demand_mw.toFixed(0)} MW`} />
                <MiniMetric label="Historical Peak" value={`${replay.summary.historical_peak_demand_mw.toFixed(0)} MW`} />
                <MiniMetric label="Replay Window" value={replay.summary.replay_month_label} />
                <MiniMetric label="Revealed Records" value={`${replay.status.revealed_records}/${replay.status.total_replay_records}`} />
              </>
            ) : (
              <>
                <MiniMetric
                  label="Selected Scenario"
                  value={calibration?.selected_scenario_label ?? "Typical Day"}
                />
                <MiniMetric
                  label="SCADA Temp"
                  value={
                    calibration?.selected_temperature_c != null
                      ? `${calibration.selected_temperature_c.toFixed(1)}°C`
                      : "Unavailable"
                  }
                />
                <MiniMetric
            label="Profile Demand"
            value={
              calibration?.selected_demand_mw != null
                ? `${calibration.selected_demand_mw.toFixed(0)} MW`
                : "Unavailable"
            }
          />
          <MiniMetric
            label="Spinning Reserve"
            value={
              calibration?.selected_spin_mw != null
                ? `${calibration.selected_spin_mw.toFixed(0)} MW`
                : "Unavailable"
            }
          />
          <MiniMetric
            label="Selection Confidence"
            value={
              calibration?.selection_confidence != null
                ? `${(calibration.selection_confidence * 100).toFixed(0)}%`
                : "Unavailable"
            }
          />
          <MiniMetric
            label="Source"
            value={calibration?.source_archive?.split("\\").pop()?.split("/").pop() ?? "Unavailable"}
                />
          <div className="col-span-2 min-h-0">
            <MiniMetric
              label="Selection"
              value={calibration?.selection_reason ?? "Calibration data unavailable"}
            />
          </div>
              </>
            )}
          </div>
        </PanelCard>

        <ModelStatusPanel
          demandForecast={demandForecast}
          modelStatus={modelStatus}
          scadaStatus={scadaStatus}
        />
      </div>

      {replay ? (
        <HistoricalDemandChart replay={replay} theme={theme} />
      ) : (
        <ScenarioComparisonChart
          scenarios={calibration?.scenarios ?? []}
          selectedScenarioKey={calibration?.selected_scenario_key}
          theme={theme}
          className="h-full min-h-0 w-full min-w-0"
        />
      )}
    </div>
  );
}

function ModelStatusPanel({
  demandForecast,
  modelStatus,
  scadaStatus,
}: {
  demandForecast: DemandForecastBundle | null;
  modelStatus: ModelStatus | null;
  scadaStatus: ScadaStatus | null;
}) {
  const primaryHorizon = demandForecast?.horizons?.[0] ?? null;
  const accuracyRows = [...(demandForecast?.horizons ?? [])].sort(
    (left, right) => left.horizon_hours - right.horizon_hours,
  );
  const knownGaps = scadaStatus?.known_data_gaps ?? [];
  const topFeatures = Object.entries(modelStatus?.feature_importance ?? {})
    .sort((left, right) => right[1] - left[1])
    .slice(0, 3);

  return (
    <PanelCard title="Forecast Assurance" className="min-h-0">
      <div className="grid h-full min-h-0 grid-rows-[auto_auto_minmax(0,1fr)_auto] gap-1.5">
        <div className="grid grid-cols-2 gap-1.5">
          <MiniMetric
            label="Model / Version"
            value={modelStatus?.model_version ?? modelStatus?.active_model ?? "Unavailable"}
          />
          <MiniMetric
            label="Data Mode"
            value={scadaStatus?.mode ? formatStatusLabel(scadaStatus.mode) : "Unavailable"}
          />
          <MiniMetric
            label="1h P50 / P10-P90"
            value={
              primaryHorizon
                ? `${(primaryHorizon.p50_demand_mw ?? primaryHorizon.forecast_demand_mw).toFixed(0)} MW · ${(primaryHorizon.p10_demand_mw ?? primaryHorizon.confidence_lower_mw ?? 0).toFixed(0)}-${(primaryHorizon.p90_demand_mw ?? primaryHorizon.confidence_upper_mw ?? 0).toFixed(0)}`
                : "Unavailable"
            }
          />
          <MiniMetric
            label="Source / Hour Alignment"
            value={
              scadaStatus?.alignment_validation_status
                ? `${scadaStatus.alignment_validation_status} · ${scadaStatus.alignment_mismatch_count ?? 0} mismatch${(scadaStatus.alignment_mismatch_count ?? 0) === 1 ? "" : "es"}`
                : scadaStatus?.archive_validation_status ?? scadaStatus?.quality_status ?? "Unavailable"
            }
          />
        </div>

        {knownGaps.length ? (
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[9px] leading-snug text-amber-100">
            Historical gap: {knownGaps.join("; ")}. Demand rows remain lower-weight; capacity risk is unavailable where TRA is absent.
          </div>
        ) : null}

        <div className="min-h-0 overflow-auto rounded-lg border border-slate-800 bg-slate-950/45">
          <div className="grid grid-cols-[0.55fr_1.25fr_repeat(3,0.8fr)] gap-1 border-b border-slate-800 px-2 py-1 text-center text-[8px] uppercase tracking-[0.08em] text-slate-500">
            <span>Horizon</span><span>Active</span><span>MAE</span><span>RMSE</span><span>MAPE</span>
          </div>
          {accuracyRows.length ? accuracyRows.map((row) => (
            <div key={row.horizon_hours} className="grid grid-cols-[0.55fr_1.25fr_repeat(3,0.8fr)] gap-1 border-b border-slate-900 px-2 py-1 text-center text-[9px] text-slate-200 last:border-0">
              <span>+{row.horizon_hours}h</span>
              <span className="truncate" title={row.model_name}>{row.model_name}</span>
              <span>{row.mae?.toFixed(1) ?? "--"}</span>
              <span>{row.rmse?.toFixed(1) ?? "--"}</span>
              <span>{row.mape?.toFixed(1) ?? "--"}%</span>
            </div>
          )) : (
            <p className="p-2 text-center text-[10px] text-slate-500">Horizon metrics unavailable.</p>
          )}
        </div>

        <div className="text-[9px] leading-snug text-slate-500">
          {topFeatures.length
            ? `Top model evidence: ${topFeatures.map(([name, value]) => `${name.replace(/_/g, " ")} ${(value * 100).toFixed(0)}%`).join(" · ")}`
            : modelStatus?.fallback_reason ?? "Feature evidence unavailable."}
          {scadaStatus?.latest_snapshot ? ` · Snapshot ${formatShortDateTime(scadaStatus.latest_snapshot)}` : ""}
          {scadaStatus?.available_at ? ` · Finalized ${formatShortDateTime(scadaStatus.available_at)}` : ""}
        </div>
      </div>
    </PanelCard>
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
      {title ? (
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">
          {title}
        </p>
      ) : null}
      <div className={`${title ? "mt-1.5" : ""} min-h-0 flex-1`}>{children}</div>
    </div>
  );
}

function ForecastAttribution({
  forecastItems,
  updatedAt,
}: {
  forecastItems: ForecastData[];
  updatedAt?: string | null;
}) {
  const names = forecastItems[0]?.source_names?.length
    ? forecastItems[0].source_names.join(" + ")
    : forecastItems[0]?.provider_name ?? "Weather providers";

  return (
    <div className="border-t border-slate-800 px-3 py-1.5 text-center text-[10px] leading-snug text-slate-500">
      <span>{names}</span>
      {updatedAt ? <span> · Updated {formatTimestamp(updatedAt)}</span> : null}
      <span> · </span>
      <a
        className="hover:text-cyan-300"
        href="https://creativecommons.org/licenses/by/4.0/"
        target="_blank"
        rel="noreferrer"
      >
        CC BY 4.0
      </a>
    </div>
  );
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex h-full min-h-[3.5rem] flex-col items-center justify-center rounded-xl border border-slate-800 bg-slate-950/60 px-2.5 py-1.5 text-center">
      <p className="text-[9px] uppercase tracking-[0.12em] text-slate-400">{label}</p>
      <p className="mt-0.5 min-w-0 break-words text-[0.8rem] font-semibold leading-snug text-white">{value}</p>
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

function formatHourOnly(value: string): string {
  return new Intl.DateTimeFormat("en-TT", {
    hour: "numeric",
    hour12: true,
    timeZone: "America/Port_of_Spain",
  }).format(new Date(value));
}

function formatShortDateTime(value?: string | null): string {
  if (!value) {
    return "--";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function formatStatusLabel(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

function formatSignedMegawatts(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(0)} MW`;
}

function isHistoricalScadaReplay(
  grid: DashboardSnapshot["grid"],
): boolean {
  return ["HistoricalScadaReplay", "HistoricalScadaSimulatedReplay"].includes(
    grid.source_provider,
  );
}

function generationMetricLabel(grid: DashboardSnapshot["grid"]): string {
  return isHistoricalScadaReplay(grid) ? "Generation (TRA)" : "Generation";
}

function getSystemSpinMw(grid: DashboardSnapshot["grid"]): number | null {
  const reportedSpin = grid.spinning_reserve_mw;
  if (
    typeof reportedSpin === "number" &&
    Number.isFinite(reportedSpin) &&
    reportedSpin >= 0
  ) {
    return reportedSpin;
  }
  return null;
}

function formatSystemSpin(grid: DashboardSnapshot["grid"]): string {
  const systemSpinMw = getSystemSpinMw(grid);
  return systemSpinMw == null ? "Unavailable" : `${systemSpinMw.toFixed(0)} MW`;
}

function formatProbability(
  probability: DashboardSnapshot["probability"],
): string {
  return probability.risk_level === "UNAVAILABLE" ||
    probability.capacity_status === "Unavailable"
    ? "--"
    : `${probability.capacity_risk_percent.toFixed(1)}%`;
}

function formatGuidanceForecastTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/Port_of_Spain",
    timeZoneName: "short",
  }).format(date);
}

function getUpcomingForecastItems(
  forecastItems: ForecastData[],
  referenceTime: Date = new Date(),
  count = 6,
): ForecastData[] {
  const now = referenceTime.getTime();
  const sortedItems = [...forecastItems].sort(
    (left, right) =>
      new Date(left.forecast_timestamp).getTime() - new Date(right.forecast_timestamp).getTime(),
  );

  const upcomingItems = sortedItems.filter((item) => {
    const timestamp = new Date(item.forecast_timestamp).getTime();
    return !Number.isNaN(timestamp) && timestamp > now;
  });

  if (upcomingItems.length >= count) {
    return upcomingItems.slice(0, count);
  }

  return sortedItems.slice(0, count);
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
      className={`flex min-h-[4.75rem] flex-col items-center justify-center rounded-2xl border px-3 py-2 text-center shadow-[0_0_24px_rgba(8,145,178,0.06)] ${toneClasses[tone]}`}
    >
      <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-300">
        {label}
      </p>
      <p
        className={`mt-1.5 min-w-0 break-words font-semibold leading-tight text-white ${
          compactValue ? "text-[0.82rem] leading-snug" : "text-[1.15rem] xl:text-[1.25rem]"
        }`}
      >
        {value}
      </p>
    </div>
  );
}
