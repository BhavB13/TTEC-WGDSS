import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import CurrentConditions from "../components/CurrentConditions";
import DemandForecastChart from "../components/DemandForecastChart";
import DayNavigationBar from "../components/DayNavigationBar";
import Header from "../components/Header";
import HistoricalDemandChart from "../components/HistoricalDemandChart";
import LiveScadaTest from "../components/LiveScadaTest";
import SelectedDayChart from "../components/SelectedDayChart";
import ProbabilityGauge from "../components/ProbabilityGauge";
import ReplayControlBar from "../components/ReplayControlBar";
import ReplayLoadChart from "../components/ReplayLoadChart";
import RiskTimelineChart from "../components/RiskTimelineChart";
import ScenarioComparisonChart from "../components/ScenarioComparisonChart";
import WeatherMap from "../components/WeatherMap";
import {
  controlReplay,
  evaluateCapacityPlan,
  getDashboardSnapshot,
  getLiveWeatherDisplay,
} from "../services/api";
import type {
  CalibrationSnapshot,
  CapacityPlan,
  CapacityStartActionInput,
  DashboardSnapshot,
  DemandForecastBundle,
  DemandForecastHorizon,
  ForecastData,
  DaySeriesPoint,
  LoadForecastPoint,
  ModelStatus,
  ScadaStatus,
  ReplayDashboard,
} from "../types/dashboard";
import { getTemperatureMetricLabel } from "../utils/weatherTemperature";
import { useDashboardTime } from "../context/DashboardTimeContext";
import { DashboardTimeProvider } from "../context/DashboardTimeContext";

type LoadState = "loading" | "ready" | "error";
type ThemeMode = "dark" | "light";
type WeatherDisplayMode = "replay" | "live";
type LiveWeatherState = "idle" | "loading" | "ready" | "error";
type DashboardTab =
  | "home"
  | "operations"
  | "weather"
  | "demandForecast"
  | "riskGauge"
  | "operationalGuidance"
  | "analytics"
  | "liveScadaTest";

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
  return (
    <DashboardTimeProvider>
      <DashboardContent />
    </DashboardTimeProvider>
  );
}

function DashboardContent() {
  const dashboardTime = useDashboardTime();
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
  const [capacityPlan, setCapacityPlan] = useState<CapacityPlan | null>(null);
  const [capacityPlanBusy, setCapacityPlanBusy] = useState(false);
  const [capacityPlanError, setCapacityPlanError] = useState("");
  const [weatherDisplayMode, setWeatherDisplayMode] =
    useState<WeatherDisplayMode>("replay");
  const [liveWeatherState, setLiveWeatherState] =
    useState<LiveWeatherState>("idle");
  const [liveWeather, setLiveWeather] = useState<{
    weather: DashboardSnapshot["weather"];
    forecast: ForecastData[];
    fetchedAt: string;
  } | null>(null);
  const [liveWeatherError, setLiveWeatherError] = useState("");

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
        const data = await getDashboardSnapshot({
          forceRefresh,
          selectedDate: dashboardTime.selectedDate,
        });
        setSnapshot(data);
        setCapacityPlan(data.capacity_plan ?? null);
        setCapacityPlanError("");
        setRefreshError("");
        setState("ready");
        if (
          dashboardTime.selectedDate &&
          data.time_context.is_active_day
        ) {
          dashboardTime.resetToActiveDay();
        }
      } catch (cause) {
        const message =
          cause instanceof Error
            ? cause.message
            : "Failed to load dashboard snapshot";
        if (
          dashboardTime.selectedDate &&
          message.includes("selected_date")
        ) {
          dashboardTime.resetToActiveDay();
          return;
        }
        if (showLoading) {
          setSnapshot(null);
          setError(message);
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
    [
      dashboardTime.selectedDate,
      dashboardTime.resetToActiveDay,
    ],
  );

  useEffect(() => {
    void loadSnapshot({ forceRefresh: true, showLoading: true });
  }, [loadSnapshot]);

  useEffect(() => {
    setWeatherDisplayMode(
      dashboardTime.selectedDate ? "replay" : "live",
    );
  }, [dashboardTime.selectedDate]);

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

  const handleCapacityPlanEvaluate = useCallback(
    async (actions: CapacityStartActionInput[]) => {
      const snapshotId = snapshot?.snapshot_id;
      if (!snapshotId) {
        setCapacityPlanError("Refresh the dashboard before evaluating a capacity plan.");
        return;
      }
      setCapacityPlanBusy(true);
      setCapacityPlanError("");
      try {
        const result = await evaluateCapacityPlan({
          snapshot_id: snapshotId,
          actions,
        });
        setCapacityPlan(result);
      } catch (cause) {
        setCapacityPlanError(
          cause instanceof Error
            ? cause.message
            : "Capacity-plan evaluation failed",
        );
      } finally {
        setCapacityPlanBusy(false);
      }
    },
    [snapshot?.snapshot_id],
  );

  const handleCapacityPlanReset = useCallback(() => {
    setCapacityPlan(snapshot?.capacity_plan ?? null);
    setCapacityPlanError("");
  }, [snapshot?.capacity_plan]);

  const loadLiveWeather = useCallback(async () => {
    setLiveWeatherState("loading");
    setLiveWeatherError("");
    try {
      const data = await getLiveWeatherDisplay();
      setLiveWeather(data);
      setLiveWeatherState("ready");
    } catch (cause) {
      setLiveWeatherState("error");
      setLiveWeatherError(
        cause instanceof Error ? cause.message : "Live weather is unavailable",
      );
    }
  }, []);

  useEffect(() => {
    if (dashboardTime.selectedDate || weatherDisplayMode !== "live") {
      return undefined;
    }
    void loadLiveWeather();
    const interval = window.setInterval(() => {
      void loadLiveWeather();
    }, 5 * 60 * 1000);
    return () => window.clearInterval(interval);
  }, [dashboardTime.selectedDate, loadLiveWeather, weatherDisplayMode]);

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
  const activeForecastItems =
    snapshot.time_context.is_active_day ? upcomingForecastItems : [];
  const liveUpcomingForecastItems = getUpcomingForecastItems(
    liveWeather?.forecast ?? [],
    new Date(),
    6,
  );
  const hourlyDemandForecast = buildHourlyDemandForecast(
    snapshot.replay?.full_day_load_forecast ?? [],
    demandForecast?.horizons ?? [],
  );

  return (
    <Shell
      lastUpdated={
        snapshot.time_context.is_active_day
          ? scadaStatus?.latest_snapshot ?? weather.timestamp
          : snapshot.time_context.displayed_at ?? weather.timestamp
      }
      systemStatus={systemStatus}
      gridStatus={grid.grid_status}
      weatherStatus={
        snapshot.time_context.is_active_day
          ? dataQuality.weather_status
          : "ARCHIVED"
      }
      forecastStatus={
        snapshot.time_context.is_active_day
          ? dataQuality.weather_status
          : "NOT APPLICABLE"
      }
      scenarioLabel={
        snapshot.time_context.is_active_day && snapshot.replay
            ? "June 2026 Replay"
            : "Previous June Day"
      }
      dataQuality={dataQuality}
      refreshError={refreshError}
      theme={theme}
      onThemeChange={setTheme}
    >
      <div className="dashboard-shell-grid">
        <section className="dashboard-map-column">
          <WeatherMap
            className="h-full min-h-0"
            weather={weather}
            liveSamplingEnabled={snapshot.time_context.is_active_day}
          />
        </section>

        <section className="dashboard-workspace">
          <div className="flex h-full min-h-0 w-full min-w-0 flex-col gap-2 overflow-hidden">
            <DayNavigationBar
              context={snapshot.time_context ?? null}
              provenance={snapshot.inference_provenance ?? null}
            />
            <TabBar activeTab={activeTab} onChange={setActiveTab} />
            {snapshot.replay && snapshot.time_context.is_active_day ? (
              <ReplayControlBar
                status={snapshot.replay.status}
                sourceTimestamp={scadaStatus?.latest_snapshot}
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
                    forecastItems={activeForecastItems}
                    calibration={calibration}
                    theme={theme}
                    timeContext={snapshot.time_context}
                    replay={
                      snapshot.time_context.is_active_day
                        ? snapshot.replay ?? null
                        : null
                    }
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
                    weather={
                      weatherDisplayMode === "live" && liveWeather
                        ? liveWeather.weather
                        : weather
                    }
                    forecastItems={
                      weatherDisplayMode === "live" && liveWeather
                        ? liveUpcomingForecastItems
                        : upcomingForecastItems
                    }
                    qualityStatus={
                      weatherDisplayMode === "live"
                        ? liveWeatherState === "ready"
                          ? "LIVE TEST DATA"
                          : liveWeatherState.toUpperCase()
                        : dataQuality.weather_status
                    }
                    mode={weatherDisplayMode}
                    liveState={liveWeatherState}
                    liveError={liveWeatherError}
                    fetchedAt={liveWeather?.fetchedAt ?? null}
                    onRefresh={loadLiveWeather}
                    hourlyDemandForecast={hourlyDemandForecast}
                    daySeries={snapshot.time_context.series}
                  />
                </WorkspacePage>
              ) : null}

              {activeTab === "demandForecast" ? (
                <WorkspacePage>
                  {!snapshot.time_context.is_active_day ? (
                    <SelectedDayChart
                      context={snapshot.time_context}
                      theme={theme}
                    />
                  ) : (
                    <DemandForecastTab
                      grid={grid}
                      probability={probability}
                      calibration={calibration}
                      demandForecast={demandForecast}
                      theme={theme}
                      replay={snapshot.replay ?? null}
                    />
                  )}
                </WorkspacePage>
              ) : null}

              {activeTab === "riskGauge" ? (
                <WorkspacePage>
                  <RiskGaugeTab
                    probability={probability}
                    capacityPlan={
                      snapshot.time_context.is_active_day ? capacityPlan : null
                    }
                    theme={theme}
                  />
                </WorkspacePage>
              ) : null}

              {activeTab === "operationalGuidance" ? (
                <WorkspacePage>
                  <OperationalGuidanceTab
                    recommendation={recommendation}
                    capacityPlan={
                      snapshot.time_context.is_active_day ? capacityPlan : null
                    }
                    busy={capacityPlanBusy}
                    error={capacityPlanError}
                    onEvaluate={handleCapacityPlanEvaluate}
                    onReset={handleCapacityPlanReset}
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
                    replay={
                      snapshot.time_context.is_active_day
                        ? snapshot.replay ?? null
                        : null
                    }
                  />
                </WorkspacePage>
              ) : null}
              {activeTab === "liveScadaTest" ? (
                <WorkspacePage>
                  <LiveScadaTest />
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
      <main className="flex w-full min-w-0 max-w-full flex-1 min-h-0 overflow-visible px-3 py-2 lg:px-4 xl:overflow-hidden">
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
    { id: "liveScadaTest", label: "Live SCADA Test", shortLabel: "SCADA Test" },
  ];

  return (
    <div className="w-full min-w-0 max-w-full rounded-xl border border-slate-800 bg-slate-950/50 p-1">
      <div className="grid min-w-0 grid-cols-4 gap-1 sm:grid-cols-8">
      {tabs.map((tab) => {
        const selected = tab.id === activeTab;
        return (
          <button
            key={tab.id}
            type="button"
            onClick={() => onChange(tab.id)}
            title={tab.label}
            aria-label={tab.label}
            className={`min-h-[2.25rem] rounded-lg border px-2 py-1.5 text-[10px] font-semibold leading-tight transition md:text-[11px] ${
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
  timeContext,
  replay,
}: {
  grid: DashboardSnapshot["grid"];
  weather: DashboardSnapshot["weather"];
  probability: DashboardSnapshot["probability"];
  recommendation: DashboardSnapshot["recommendation"];
  forecastItems: ForecastData[];
  calibration: CalibrationSnapshot | null;
  theme: ThemeMode;
  timeContext: DashboardSnapshot["time_context"];
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
          <SummaryTile label="Generation Need" value={formatProbability(probability)} tone="rose" />
        </div>

        <div className="home-primary-grid">
          <ReplayLoadChart replay={replay} theme={theme} compact />
          <ReplayWeatherPanel weather={weather} forecastItems={forecastItems} />
        </div>
      </>
    );
  }

  if (!timeContext.is_active_day) {
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
          <SummaryTile label="System Spin" value={formatSystemSpin(grid)} tone="amber" />
          <SummaryTile label="Generation Need" value={formatProbability(probability)} tone="rose" />
        </div>
        <div className="home-primary-grid">
          <SelectedDayChart context={timeContext} theme={theme} />
          <PanelCard title="Selected Day Evidence" className="h-full min-h-0">
            <div className="grid h-full auto-rows-fr gap-2">
              <MiniMetric label="Replay Date" value={timeContext.selected_date} />
              <MiniMetric label="Recorded Through" value={formatTimestamp(timeContext.displayed_at)} />
              <MiniMetric label="Hourly Records" value={`${timeContext.record_count}`} />
              <MiniMetric label="Completeness" value={`${timeContext.completeness_percent.toFixed(0)}%`} />
              <MiniMetric label="Classification" value="Previous-Day Replay" />
              <MiniMetric label="Source" value={timeContext.source} />
            </div>
          </PanelCard>
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
        <SummaryTile label="Generation Need" value={formatProbability(probability)} tone="rose" />
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
          <MiniMetric
            label={getTemperatureMetricLabel(weather, true)}
            value={`${weather.temperature_c.toFixed(1)}°C`}
          />
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
                <th className="px-2 py-1.5 font-medium">
                  {forecastItems[0]
                    ? getTemperatureMetricLabel(forecastItems[0], true)
                    : "Temp"}
                </th>
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
        <MiniMetric label="Generation Need" value={formatProbability(recommendation)} />
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
        <MiniMetric
          label={getTemperatureMetricLabel(weather, true)}
          value={`${weather.temperature_c.toFixed(1)}°C`}
        />
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
  mode,
  liveState,
  liveError,
  fetchedAt,
  onRefresh,
  hourlyDemandForecast,
  daySeries,
}: {
  weather: DashboardSnapshot["weather"];
  forecastItems: ForecastData[];
  qualityStatus: string;
  mode: WeatherDisplayMode;
  liveState: LiveWeatherState;
  liveError: string;
  fetchedAt: string | null;
  onRefresh: () => void;
  hourlyDemandForecast: ReadonlyMap<number, number>;
  daySeries: DaySeriesPoint[];
}) {
  return (
    <div className="flex h-full min-h-0 w-full min-w-0 flex-col gap-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-cyan-500/15 bg-slate-950/55 px-2.5 py-2">
        <div className="flex items-center gap-2">
          <span className={`rounded-lg border px-3 py-1.5 text-xs font-semibold ${
            mode === "live"
              ? "border-emerald-500/30 bg-emerald-500/15 text-emerald-200"
              : "border-cyan-500/30 bg-cyan-500/15 text-cyan-200"
          }`}>
            {mode === "live" ? "Active Weather" : "Previous-Day Weather"}
          </span>
          <span className="text-[10px] uppercase tracking-[0.14em] text-slate-400">
            {mode === "live"
              ? "Current T&T provider network"
              : "Selected June replay day"}
          </span>
        </div>

        {mode === "live" ? (
          <div className="flex items-center gap-2 text-[10px] text-slate-400">
            <span>
              {liveState === "loading"
                ? "Updating live providers..."
                : fetchedAt
                  ? `Fetched ${formatTimestamp(fetchedAt)}`
                  : "Not yet fetched"}
            </span>
            <button
              type="button"
              className="rounded-md border border-cyan-500/30 px-2 py-1 font-semibold text-cyan-200 hover:bg-cyan-500/10 disabled:cursor-wait disabled:opacity-50"
              disabled={liveState === "loading"}
              onClick={onRefresh}
            >
              Refresh
            </button>
          </div>
        ) : null}
      </div>

      {mode === "live" && liveState === "error" && !forecastItems.length ? (
        <div className="flex min-h-0 flex-1 flex-col items-center justify-center rounded-2xl border border-rose-500/25 bg-rose-950/15 px-6 text-center">
          <p className="font-semibold text-rose-200">Live weather is temporarily unavailable.</p>
          <p className="mt-1 text-sm text-slate-400">{liveError}</p>
          <button
            type="button"
            className="mt-3 rounded-lg border border-cyan-500/30 px-3 py-1.5 text-xs font-semibold text-cyan-200 hover:bg-cyan-500/10"
            onClick={onRefresh}
          >
            Retry live weather
          </button>
        </div>
      ) : (
        <div className="grid min-h-0 w-full min-w-0 flex-1 gap-2.5 xl:grid-cols-[minmax(0,0.35fr)_minmax(0,0.65fr)]">
          <CurrentConditions
            weather={weather}
            qualityStatus={qualityStatus}
            className="h-full min-h-0 w-full min-w-0"
          />
          {mode === "replay" ? (
            <SelectedDayWeather series={daySeries} />
          ) : (
          <PanelCard title="Next 6 Hours · Weather + Demand" className="h-full min-h-0 w-full min-w-0">
            <div className="flex h-full min-h-0 flex-col gap-2">
              {forecastItems.length > 0 ? (
                <div className="grid min-h-0 flex-1 auto-rows-fr gap-1.5 overflow-auto">
                  {forecastItems.map((period) => (
                    <GuidanceForecastRow
                      key={period.forecast_timestamp}
                      period={period}
                      demandForecastMw={findHourlyDemandForecast(
                        hourlyDemandForecast,
                        period.forecast_timestamp,
                      )}
                    />
                  ))}
                </div>
              ) : (
                <div className="flex min-h-0 flex-1 items-center justify-center rounded-xl border border-dashed border-slate-700 bg-slate-950/40 px-4 text-center text-sm text-slate-400">
                  {liveState === "loading"
                    ? "Loading live weather consensus..."
                    : "Six-hour weather guidance is temporarily unavailable."}
                </div>
              )}

              <ForecastAttribution
                forecastItems={forecastItems}
                updatedAt={weather.timestamp}
              />
            </div>
          </PanelCard>
          )}
        </div>
      )}
    </div>
  );
}

function SelectedDayWeather({
  series,
}: {
  series: DaySeriesPoint[];
}) {
  const visible = series.slice(-24);
  return (
    <PanelCard title="Selected Day · Recorded Weather" className="h-full min-h-0 w-full min-w-0">
      <div className="flex h-full min-h-0 flex-col">
        <p className="mb-2 text-[10px] text-slate-400">
          Recorded SCADA ambient temperature. Missing weather channels are not
          substituted with present data.
        </p>
        <div className="min-h-0 flex-1 overflow-auto rounded-xl border border-slate-800 bg-slate-950/45">
          <table className="w-full table-fixed text-left text-xs">
            <thead className="sticky top-0 bg-slate-950 text-slate-400">
              <tr>
                <th className="px-3 py-2">Observed at</th>
                <th className="px-3 py-2">Temperature</th>
                <th className="px-3 py-2">Quality</th>
                <th className="px-3 py-2">Coverage</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800 text-slate-200">
              {visible.map((point) => (
                <tr key={point.timestamp}>
                  <td className="px-3 py-2">{formatTimestamp(point.timestamp)}</td>
                  <td className="px-3 py-2">
                    {point.temperature_c == null
                      ? "Gap"
                      : `${point.temperature_c.toFixed(1)}°C`}
                  </td>
                  <td className="px-3 py-2">{point.quality_status}</td>
                  <td className="px-3 py-2">{point.completeness_percent.toFixed(0)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </PanelCard>
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
  capacityPlan,
  theme,
}: {
  probability: DashboardSnapshot["probability"];
  capacityPlan: CapacityPlan | null;
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
  const topDrivers = selectTopRiskDrivers(drivers, 4);
  const visibleDrivers = showAllDrivers ? drivers : topDrivers;
  return (
    <div className="grid h-full min-h-0 w-full min-w-0 grid-rows-2 gap-2.5 overflow-hidden">
      <div className="grid min-h-0 min-w-0 gap-2.5 xl:grid-cols-[minmax(16rem,0.3fr)_minmax(0,0.7fr)]">
        <ProbabilityGauge
          probability={probability}
          className="h-full min-h-0 w-full min-w-0"
        />
        <RiskTimelineChart
          probability={probability}
          capacityPlan={capacityPlan}
          theme={theme}
          className="h-full min-h-0 w-full min-w-0"
        />
      </div>

      <div className="grid min-h-0 min-w-0 gap-2.5 overflow-hidden xl:grid-cols-[minmax(0,1.05fr)_minmax(21rem,0.95fr)]">
        <PanelCard
          title="Generation Need Evidence"
          className="h-full min-h-0 w-full min-w-0"
        >
          <div className="grid h-full min-h-0 grid-cols-2 auto-rows-fr gap-1.5 sm:grid-cols-4">
            <MiniMetric
              label="Maximum Need Without Action"
              value={formatPlanRisk(capacityPlan?.baseline_peak_risk_percent, probability)}
            />
            <MiniMetric
              label="Peak Forecast Demand"
              value={`${probability.forecast_demand_mw.toFixed(1)} MW`}
            />
            <MiniMetric
              label="Observed TRA"
              value={formatOptionalMegawatts(capacityPlan?.current_tra_mw)}
            />
            <MiniMetric
              label="Peak Reserve"
              value={formatOptionalMegawatts(getPeakPlanPoint(capacityPlan)?.baseline_reserve_mw)}
            />
            <MiniMetric
              label="Maximum Need After Plan"
              value={formatOptionalPercent(capacityPlan?.post_plan_peak_risk_percent)}
            />
            <MiniMetric
              label="TRA With Starts"
              value={formatOptionalMegawatts(getPeakPlanPoint(capacityPlan)?.planned_tra_mw)}
            />
            <MiniMetric
              label="Risk Reduction"
              value={formatPercentagePoints(capacityPlan?.risk_reduction_percentage_points)}
            />
            <MiniMetric
              label="TRA Freshness"
              value={formatTraEvidence(capacityPlan)}
            />
          </div>
        </PanelCard>

        <PanelCard title="Risk Drivers" className="h-full min-h-0 w-full min-w-0">
          <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)] gap-1.5">
            <div
              className={`grid gap-1 text-center text-[8px] uppercase tracking-[0.06em] ${
                drivers.length > 2 ? "grid-cols-5" : "grid-cols-4"
              }`}
            >
              <span className="rounded-lg border border-rose-500/25 bg-rose-500/10 px-1.5 py-1 text-rose-200">
                Raising {increasingCount}
              </span>
              <span className="rounded-lg border border-emerald-500/25 bg-emerald-500/10 px-1.5 py-1 text-emerald-200">
                Reducing {reducingCount}
              </span>
              <span className="rounded-lg border border-amber-500/25 bg-amber-500/10 px-1.5 py-1 text-amber-200">
                Warnings {warningCount}
              </span>
              <span className="rounded-lg border border-slate-600/60 bg-slate-800/55 px-1.5 py-1 text-slate-300">
                Context {contextCount}
              </span>
              {drivers.length > 2 ? (
                <button
                  type="button"
                  onClick={() => setShowAllDrivers((current) => !current)}
                  title={showAllDrivers ? "Show priority drivers" : `View all ${drivers.length} drivers`}
                  className="rounded-lg border border-cyan-500/25 bg-cyan-500/10 px-1 py-1 font-semibold text-cyan-100 hover:border-cyan-400/45 hover:bg-cyan-500/15"
                >
                  {showAllDrivers ? "Priority" : `All ${drivers.length}`}
                </button>
              ) : null}
            </div>
            <ol
              className={`grid min-h-0 gap-1.5 overflow-auto pr-0.5 ${
                showAllDrivers
                  ? "auto-rows-min grid-cols-1"
                  : "grid-cols-1 grid-rows-2 2xl:grid-cols-2 2xl:grid-rows-2"
              }`}
            >
              {visibleDrivers.map((driver, index) => (
                <li
                  key={`${driver.category}-${driver.label}-${index}`}
                  className={`min-h-0 items-start gap-2 rounded-lg border border-slate-800 bg-slate-950/55 px-2 py-1.5 text-[0.68rem] leading-snug text-slate-200 ${
                    !showAllDrivers && index >= 2 ? "hidden 2xl:flex" : "flex"
                  }`}
                >
                  <span
                    className={`mt-1 h-2 w-2 shrink-0 rounded-full ${riskDriverDot(driver.direction)}`}
                  />
                  <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                    <span className="hidden text-[8px] uppercase tracking-[0.08em] text-slate-500 2xl:block">
                      {driver.category.replace(/_/g, " ")}
                    </span>
                    <span className="break-words">{driver.label}</span>
                  </span>
                </li>
              ))}
            </ol>
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
  capacityPlan,
  busy,
  error,
  onEvaluate,
  onReset,
}: {
  recommendation: DashboardSnapshot["recommendation"];
  capacityPlan: CapacityPlan | null;
  busy: boolean;
  error: string;
  onEvaluate: (actions: CapacityStartActionInput[]) => Promise<void>;
  onReset: () => void;
}) {
  const [selectedCounts, setSelectedCounts] = useState<Record<string, number>>({});

  useEffect(() => {
    setSelectedCounts(
      Object.fromEntries(
        (capacityPlan?.evaluated_actions ?? []).map((action) => [
          action.block_id,
          action.count,
        ]),
      ),
    );
  }, [capacityPlan]);

  const definitions = capacityPlan?.block_definitions ?? [];
  const evaluatedActions = capacityPlan?.evaluated_actions ?? [];
  const peakPoint = getPeakPlanPoint(capacityPlan);
  const planAvailable = capacityPlan?.status === "AVAILABLE";
  const systemSuggestion =
    capacityPlan?.system_suggestion ??
    recommendation.decision_action ??
    recommendation.recommendation;
  const suggestionBasis =
    capacityPlan?.system_suggestion_basis?.length
      ? capacityPlan.system_suggestion_basis
      : recommendation.factors;
  const firstSuggestedAction = capacityPlan?.recommended_actions[0] ?? null;

  const changeCount = (blockId: string, maximum: number, delta: number) => {
    setSelectedCounts((current) => ({
      ...current,
      [blockId]: Math.max(
        0,
        Math.min(maximum, (current[blockId] ?? 0) + delta),
      ),
    }));
  };

  const evaluateSelection = () => {
    const actions = definitions
      .filter(
        (definition) =>
          definition.enabled &&
          (selectedCounts[definition.block_id] ?? 0) > 0,
      )
      .map((definition) => ({
        block_id: definition.block_id,
        count: selectedCounts[definition.block_id],
      }));
    void onEvaluate(actions);
  };

  return (
    <div className="grid h-full min-h-0 w-full min-w-0 grid-rows-[auto_minmax(0,1fr)] gap-2 overflow-hidden">
      <div className="grid min-w-0 gap-2 rounded-xl border border-cyan-400/30 bg-cyan-500/10 px-3 py-2 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[9px] font-bold uppercase tracking-[0.16em] text-cyan-200">
              Machine-Generated Suggestion
            </p>
            <span className="rounded-full border border-cyan-400/25 bg-slate-950/45 px-2 py-0.5 text-[8px] font-semibold uppercase text-cyan-100">
              Forecast + risk optimizer
            </span>
          </div>
          <p className="mt-0.5 break-words text-[0.8rem] font-semibold leading-snug text-white">
            {systemSuggestion}
          </p>
          <p className="mt-0.5 text-[9px] leading-snug text-slate-300">
            {suggestionBasis.slice(0, 2).join(" · ")}
          </p>
        </div>
        <div className="flex shrink-0 items-center justify-end gap-1.5 text-center">
          {firstSuggestedAction ? (
            <div className="rounded-lg border border-cyan-400/20 bg-slate-950/50 px-2 py-1">
              <p className="text-[8px] uppercase tracking-[0.1em] text-slate-500">
                Start By
              </p>
              <p className="text-[10px] font-semibold text-cyan-100">
                {formatCompactTime(firstSuggestedAction.start_by)}
              </p>
            </div>
          ) : null}
          <div className="rounded-lg border border-amber-400/25 bg-amber-500/10 px-2 py-1">
            <p className="max-w-[10rem] text-[8px] font-bold uppercase leading-snug tracking-[0.08em] text-amber-100">
              {capacityPlan?.advisory_notice ??
                "ADVISORY ONLY - MANUAL OPERATOR ACTION REQUIRED"}
            </p>
          </div>
        </div>
      </div>

      <div className="grid min-h-0 gap-2.5 overflow-hidden xl:grid-cols-[minmax(19rem,0.88fr)_minmax(0,1.12fr)]">
        <PanelCard title="Aggregate Start Blocks" className="min-h-0">
          <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)_auto] gap-2">
            <div className="grid grid-cols-3 gap-1.5">
              <MiniMetric
                label="Current TRA"
                value={formatOptionalMegawatts(capacityPlan?.current_tra_mw)}
              />
              <MiniMetric
                label="Observed"
                value={formatCompactTime(capacityPlan?.current_tra_observed_at)}
              />
              <MiniMetric
                label="TRA Quality"
                value={capacityPlan?.current_tra_quality_status ?? "Unavailable"}
              />
            </div>

            <div className="min-h-0 space-y-1.5 overflow-auto pr-0.5">
              {definitions.map((definition) => {
                const count = selectedCounts[definition.block_id] ?? 0;
                return (
                  <div
                    key={definition.block_id}
                    className={
                      "grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-2 rounded-xl border px-2.5 py-2 " +
                      (definition.enabled
                        ? "border-cyan-500/20 bg-slate-950/60"
                        : "border-slate-800 bg-slate-950/35 opacity-75")
                    }
                  >
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <p className="text-[0.72rem] font-semibold text-white">
                          {definition.label}
                        </p>
                        <span className="rounded-full border border-slate-700 px-1.5 py-0.5 text-[8px] font-semibold text-slate-400">
                          {definition.verification_status}
                        </span>
                      </div>
                      <p className="mt-0.5 text-[9px] leading-snug text-slate-400">
                        {definition.unit_capacity_mw != null ? (
                          <>
                            {definition.unit_capacity_mw.toFixed(0)} MW each ·{" "}
                            {definition.startup_lead_time_minutes} min lead ·{" "}
                            {definition.startable_count} startable
                          </>
                        ) : (
                          <>
                            {definition.startup_lead_time_minutes} min lead ·
                            capacity awaiting approved configuration
                          </>
                        )}
                      </p>
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        aria-label={"Remove one " + definition.label}
                        disabled={!definition.enabled || count <= 0 || busy}
                        onClick={() =>
                          changeCount(
                            definition.block_id,
                            definition.startable_count,
                            -1,
                          )
                        }
                        className="flex h-7 w-7 items-center justify-center rounded-lg border border-slate-700 bg-slate-900 text-sm text-slate-200 disabled:cursor-not-allowed disabled:opacity-35"
                      >
                        -
                      </button>
                      <span className="w-6 text-center text-sm font-semibold tabular-nums text-white">
                        {count}
                      </span>
                      <button
                        type="button"
                        aria-label={"Add one " + definition.label}
                        disabled={
                          !definition.enabled ||
                          count >= definition.startable_count ||
                          busy
                        }
                        onClick={() =>
                          changeCount(
                            definition.block_id,
                            definition.startable_count,
                            1,
                          )
                        }
                        className="flex h-7 w-7 items-center justify-center rounded-lg border border-cyan-500/30 bg-cyan-500/10 text-sm text-cyan-100 disabled:cursor-not-allowed disabled:opacity-35"
                      >
                        +
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>

            <div>
              {error ? (
                <p className="mb-1.5 rounded-lg border border-rose-500/30 bg-rose-500/10 px-2 py-1 text-[9px] text-rose-100">
                  {error}
                </p>
              ) : null}
              <div className="grid grid-cols-2 gap-1.5">
                <button
                  type="button"
                  onClick={evaluateSelection}
                  disabled={!planAvailable || busy}
                  className="rounded-lg border border-cyan-400/35 bg-cyan-500/15 px-2 py-2 text-[10px] font-semibold text-cyan-50 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {busy ? "Evaluating..." : "Evaluate Selection"}
                </button>
                <button
                  type="button"
                  onClick={onReset}
                  disabled={busy}
                  className="rounded-lg border border-slate-700 bg-slate-950/55 px-2 py-2 text-[10px] font-semibold text-slate-300 disabled:opacity-40"
                >
                  Use System Suggestion
                </button>
              </div>
            </div>
          </div>
        </PanelCard>

        <PanelCard title="Capacity Plan Evaluation" className="min-h-0">
          <div className="grid h-full min-h-0 grid-rows-[auto_auto_minmax(0,1fr)] gap-2">
            <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
              <MiniMetric
                label="Need Without Action"
                value={formatPlanRisk(
                  capacityPlan?.baseline_peak_risk_percent,
                  recommendation,
                )}
              />
              <MiniMetric
                label="Post-Plan Risk"
                value={formatOptionalPercent(
                  capacityPlan?.post_plan_peak_risk_percent,
                )}
              />
              <MiniMetric
                label="Proposed TRA"
                value={formatOptionalMegawatts(peakPoint?.planned_tra_mw)}
              />
              <MiniMetric
                label="Unresolved Need"
                value={formatOptionalMegawatts(
                  capacityPlan?.unresolved_capacity_mw,
                )}
              />
            </div>

            <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
              <PlanDatum
                label="Plan Source"
                value={formatEnumLabel(capacityPlan?.action_source ?? "NONE")}
              />
              <PlanDatum
                label="Reserve Target"
                value={formatOptionalMegawatts(capacityPlan?.required_reserve_mw)}
              />
              <PlanDatum
                label="First Unprotected"
                value={formatPlanExposure(capacityPlan)}
              />
              <PlanDatum
                label="Interim Exposure"
                value={
                  capacityPlan?.interim_unmitigated_risk
                    ? "YES - BEFORE START"
                    : "NONE IDENTIFIED"
                }
                warning={Boolean(capacityPlan?.interim_unmitigated_risk)}
              />
            </div>

            <div className="grid min-h-0 gap-2 overflow-hidden lg:grid-cols-[minmax(0,1.1fr)_minmax(15rem,0.9fr)]">
              <div className="min-h-0 overflow-auto rounded-xl border border-slate-800 bg-slate-950/55 p-2">
                <p className="text-[9px] font-semibold uppercase tracking-[0.14em] text-slate-400">
                  Proposed Starts
                </p>
                <div className="mt-1.5 space-y-1.5">
                  {evaluatedActions.length ? (
                    evaluatedActions.map((action) => (
                      <div
                        key={action.block_id}
                        className="rounded-lg border border-slate-800 bg-slate-900/65 px-2 py-1.5"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <p className="text-[0.7rem] font-semibold text-white">
                            {action.count} x {action.block_label}
                          </p>
                          <span
                            className={
                              "text-[8px] font-semibold " +
                              (action.applied_to_projection
                                ? "text-emerald-300"
                                : "text-amber-300")
                            }
                          >
                            {action.action_status.replace(/_/g, " ")}
                          </span>
                        </div>
                        <div className="mt-1 grid grid-cols-3 gap-1 text-center text-[9px] text-slate-400">
                          <span>{action.total_capacity_mw.toFixed(0)} MW</span>
                          <span>
                            Start by {formatCompactTime(action.start_by)}
                          </span>
                          <span>
                            Online {formatCompactTime(action.expected_online_at)}
                          </span>
                        </div>
                      </div>
                    ))
                  ) : (
                    <p className="rounded-lg border border-dashed border-slate-700 px-2 py-3 text-center text-[10px] text-slate-400">
                      No aggregate starts are included in this scenario.
                    </p>
                  )}
                </div>
              </div>

              <div className="min-h-0 overflow-auto rounded-xl border border-slate-800 bg-slate-950/55 p-2">
                <p className="text-[9px] font-semibold uppercase tracking-[0.14em] text-slate-400">
                  Operator Checks
                </p>
                <ul className="mt-1.5 space-y-1 text-[9px] leading-snug text-slate-300">
                  {(capacityPlan?.warnings ?? []).map((warning) => (
                    <li
                      key={warning}
                      className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-2 py-1.5"
                    >
                      {warning}
                    </li>
                  ))}
                  <li className="rounded-lg border border-slate-800 px-2 py-1.5">
                    Starts are hypothetical until the operator acts and SCADA
                    reports the added TRA.
                  </li>
                  <li className="rounded-lg border border-slate-800 px-2 py-1.5">
                    Shutdown planning is intentionally excluded pending approved
                    operating constraints.
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </PanelCard>
      </div>
    </div>
  );
}

function PlanDatum({
  label,
  value,
  warning = false,
}: {
  label: string;
  value: string;
  warning?: boolean;
}) {
  return (
    <div className="min-w-0 rounded-xl border border-slate-800 bg-slate-950/55 px-2 py-1.5 text-center">
      <p className="text-[8px] uppercase tracking-[0.1em] text-slate-500">
        {label}
      </p>
      <p
        className={
          "mt-0.5 break-words text-[10px] font-semibold leading-tight " +
          (warning ? "text-amber-200" : "text-slate-100")
        }
      >
        {value}
      </p>
    </div>
  );
}

function GuidanceForecastRow({
  period,
  demandForecastMw,
}: {
  period: ForecastData;
  demandForecastMw: number | null;
}) {
  const verified = (period.source_count ?? 1) > 1;

  return (
    <div className="grid min-h-[3.75rem] min-w-0 grid-cols-[minmax(6.75rem,1.25fr)_repeat(7,minmax(0,1fr))] items-center gap-1 rounded-xl border border-slate-800 bg-slate-950/60 px-2 py-1.5 shadow-inner shadow-black/20">
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
      <GuidanceDatum
        label="Demand"
        value={
          demandForecastMw == null
            ? "--"
            : `${Math.round(demandForecastMw).toLocaleString()} MW`
        }
        ariaLabel={
          demandForecastMw == null
            ? "Forecast demand unavailable"
            : `Forecast demand ${Math.round(demandForecastMw)} MW`
        }
        emphasis
      />
      <GuidanceDatum
        label={getTemperatureMetricLabel(period, true)}
        value={`${period.temperature_c.toFixed(0)}°C`}
      />
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

function GuidanceDatum({
  label,
  value,
  ariaLabel,
  emphasis = false,
}: {
  label: string;
  value: string;
  ariaLabel?: string;
  emphasis?: boolean;
}) {
  return (
    <div
      className={`min-w-0 border-l px-1 text-center ${
        emphasis
          ? "border-cyan-500/35 bg-cyan-500/[0.04]"
          : "border-slate-800"
      }`}
      aria-label={ariaLabel}
    >
      <p className="text-[8px] uppercase tracking-[0.1em] text-slate-500">{label}</p>
      <p className={`mt-0.5 break-words text-[0.72rem] font-semibold leading-tight ${
        emphasis ? "text-cyan-100" : "text-slate-100"
      }`}>
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
  const sourceWindow = formatSourceWindow(
    scadaStatus?.archive_data_start_at,
    scadaStatus?.archive_data_end_at,
  );

  return (
    <div className="grid h-full min-h-0 w-full min-w-0 gap-2.5 xl:grid-cols-[minmax(260px,0.36fr)_minmax(0,0.64fr)]">
      <div className="grid h-full min-h-0 gap-2.5">
        <PanelCard title={replay ? "Replay Data Provenance" : "Calibration Summary"} className="min-h-0">
          <div className="grid h-full min-h-0 auto-rows-fr grid-cols-2 gap-2">
            {replay ? (
              <>
                <MiniMetric label="Synthetic Context Months" value={`${replay.summary.historical_months}`} />
                <MiniMetric label="Synthetic Context Records" value={replay.summary.historical_record_count.toLocaleString()} />
                <MiniMetric label="Context Average Demand" value={`${replay.summary.historical_average_demand_mw.toFixed(0)} MW`} />
                <MiniMetric label="Context Peak Demand" value={`${replay.summary.historical_peak_demand_mw.toFixed(0)} MW`} />
                <MiniMetric label="SCADA Source Window" value={sourceWindow} />
                <MiniMetric label="Revealed SCADA Hours" value={`${replay.status.revealed_records}/${replay.status.total_replay_records}`} />
                <div className="col-span-2 rounded-lg border border-cyan-500/20 bg-cyan-500/5 px-2 py-1.5 text-center text-[9px] leading-snug text-cyan-100">
                  Display calendar: {replay.summary.replay_month_label}. June values use {scadaStatus?.source_system ?? "historical SCADA exports"} from {sourceWindow}, remapped onto the display calendar. The other months are synthetic context.
                </div>
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
          replay={replay}
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
  replay,
}: {
  demandForecast: DemandForecastBundle | null;
  modelStatus: ModelStatus | null;
  scadaStatus: ScadaStatus | null;
  replay: ReplayDashboard | null;
}) {
  const primaryHorizon = demandForecast?.horizons?.[0] ?? null;
  const accuracyRows = [...(demandForecast?.horizons ?? [])].sort(
    (left, right) => left.horizon_hours - right.horizon_hours,
  );
  const knownGaps = scadaStatus?.known_data_gaps ?? [];
  const topFeatures = Object.entries(modelStatus?.feature_importance ?? {})
    .sort((left, right) => right[1] - left[1])
    .slice(0, 3);
  const hasHorizonMetrics = accuracyRows.some(
    (row) => row.mae != null || row.rmse != null || row.mape != null,
  );

  return (
    <PanelCard title="Forecast Assurance" className="min-h-0">
      <div className="grid h-full min-h-0 grid-rows-[auto_auto_auto_minmax(0,1fr)_auto] gap-1.5">
        <div className="grid grid-cols-2 gap-1.5 lg:grid-cols-3">
          <MiniMetric
            label="Active Model"
            value={modelStatus?.active_model ?? primaryHorizon?.model_name ?? "Unavailable"}
          />
          <MiniMetric
            label="Model Version"
            value={modelStatus?.model_version ?? primaryHorizon?.model_version ?? "Unavailable"}
          />
          <MiniMetric
            label="Validation Status"
            value={modelStatus?.validation_status ?? primaryHorizon?.validation_status ?? "Unavailable"}
          />
          <MiniMetric
            label="1h Point Forecast"
            value={
              primaryHorizon
                ? `${(primaryHorizon.p50_demand_mw ?? primaryHorizon.forecast_demand_mw).toFixed(0)} MW`
                : "Unavailable"
            }
          />
          <MiniMetric
            label="1h Forecast Uncertainty"
            value={
              primaryHorizon
                ? `±${primaryHorizon.forecast_uncertainty_mw.toFixed(0)} MW`
                : "Unavailable"
            }
          />
          <MiniMetric
            label="Replay Data Mode"
            value={scadaStatus?.mode ? formatStatusLabel(scadaStatus.mode) : "Unavailable"}
          />
        </div>

        <div className="rounded-lg border border-slate-800 bg-slate-950/45 px-2 py-1 text-center text-[9px] leading-snug text-slate-400">
          <span className="font-semibold text-slate-200">Source / hour alignment: </span>
          {scadaStatus?.alignment_validation_status
            ? `${scadaStatus.alignment_validation_status} · ${scadaStatus.alignment_mismatch_count ?? 0} mismatch${(scadaStatus.alignment_mismatch_count ?? 0) === 1 ? "" : "es"}`
            : scadaStatus?.archive_validation_status ?? scadaStatus?.quality_status ?? "Unavailable"}
        </div>

        {knownGaps.length ? (
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[9px] leading-snug text-amber-100">
            Historical gap: {knownGaps.join("; ")}. Demand rows remain lower-weight; generation need is unavailable where TRA is absent.
          </div>
        ) : null}

        <div className="min-h-0 overflow-auto rounded-lg border border-slate-800 bg-slate-950/45">
          {hasHorizonMetrics ? (
            <>
              <div className="grid grid-cols-[0.55fr_1.25fr_repeat(3,0.8fr)] gap-1 border-b border-slate-800 px-2 py-1 text-center text-[8px] uppercase tracking-[0.08em] text-slate-500">
                <span>Horizon</span><span>Active model</span><span>MAE</span><span>RMSE</span><span>MAPE</span>
              </div>
              {accuracyRows.map((row) => (
                <div key={row.horizon_hours} className="grid grid-cols-[0.55fr_1.25fr_repeat(3,0.8fr)] items-center gap-1 border-b border-slate-900 px-2 py-1 text-center text-[9px] text-slate-200 last:border-0">
                  <span>+{row.horizon_hours}h</span>
                  <span className="break-words leading-tight" title={row.model_name}>{row.model_name}</span>
                  <span>{row.mae?.toFixed(1) ?? "N/A"}</span>
                  <span>{row.rmse?.toFixed(1) ?? "N/A"}</span>
                  <span>{row.mape != null ? `${row.mape.toFixed(1)}%` : "N/A"}</span>
                </div>
              ))}
            </>
          ) : accuracyRows.length ? (
            <>
              <div className="grid grid-cols-[0.55fr_minmax(7rem,1.5fr)_0.9fr_0.9fr] gap-1 border-b border-slate-800 px-2 py-1 text-center text-[8px] uppercase tracking-[0.08em] text-slate-500">
                <span>Horizon</span><span>Model</span><span>Forecast</span><span>Uncertainty</span>
              </div>
              {accuracyRows.map((row) => (
                <div key={row.horizon_hours} className="grid grid-cols-[0.55fr_minmax(7rem,1.5fr)_0.9fr_0.9fr] items-center gap-1 border-b border-slate-900 px-2 py-1 text-center text-[9px] text-slate-200 last:border-0">
                  <span>+{row.horizon_hours}h</span>
                  <span className="break-words leading-tight" title={row.model_name}>{row.model_name}</span>
                  <span>{row.forecast_demand_mw.toFixed(0)} MW</span>
                  <span>±{row.forecast_uncertainty_mw.toFixed(0)} MW</span>
                </div>
              ))}
            </>
          ) : (
            <p className="p-2 text-center text-[10px] text-slate-500">Horizon metrics unavailable.</p>
          )}
        </div>

        <div className="text-[9px] leading-snug text-slate-500">
          {topFeatures.length
            ? `Top model evidence: ${topFeatures.map(([name, value]) => `${name.replace(/_/g, " ")} ${(value * 100).toFixed(0)}%`).join(" · ")}`
            : modelStatus?.fallback_reason ?? `${replay?.summary.weather_features.length ?? 0} replay features configured; per-feature importance unavailable.`}
          {modelStatus?.trained_through ? ` · Display-clock training cutoff ${formatShortDateTime(modelStatus.trained_through)}` : ""}
          {scadaStatus?.latest_snapshot ? ` · Source snapshot ${formatShortDateTime(scadaStatus.latest_snapshot)}` : ""}
          {scadaStatus?.available_at ? ` · Source finalized ${formatShortDateTime(scadaStatus.available_at)}` : ""}
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
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function formatSourceWindow(
  startValue?: string | null,
  endValue?: string | null,
): string {
  if (!startValue || !endValue) {
    return "Unavailable";
  }
  const start = new Date(startValue);
  const end = new Date(endValue);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
    return "Unavailable";
  }
  const dateFormatter = new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
  });
  return `${dateFormatter.format(start)}-${dateFormatter.format(end)}, ${end.getFullYear()}`;
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

function getPeakPlanPoint(
  capacityPlan: CapacityPlan | null,
): CapacityPlan["profile"][number] | null {
  if (!capacityPlan?.profile.length) {
    return null;
  }
  return capacityPlan.profile.reduce((peak, point) =>
    point.baseline_capacity_risk_percent > peak.baseline_capacity_risk_percent
      ? point
      : peak,
  );
}

function formatPlanRisk(
  value: number | null | undefined,
  fallback: DashboardSnapshot["probability"],
): string {
  return value == null || !Number.isFinite(value)
    ? formatCapacityRisk(fallback)
    : `${value.toFixed(1)}%`;
}

function formatOptionalMegawatts(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value)
    ? "Unavailable"
    : `${value.toFixed(1)} MW`;
}

function formatOptionalPercent(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value)
    ? "Unavailable"
    : `${value.toFixed(1)}%`;
}

function formatPercentagePoints(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value)
    ? "Unavailable"
    : `${value.toFixed(1)} points`;
}

function formatTraEvidence(capacityPlan: CapacityPlan | null): string {
  if (!capacityPlan) {
    return "Unavailable";
  }
  const age =
    capacityPlan.current_tra_age_seconds == null
      ? ""
      : ` · ${Math.round(capacityPlan.current_tra_age_seconds)}s old`;
  return `${capacityPlan.current_tra_quality_status}${age}`;
}

function formatCompactTime(value?: string | null): string {
  if (!value) {
    return "--";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en-TT", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
    timeZone: "America/Port_of_Spain",
  }).format(date);
}

function formatPlanExposure(capacityPlan: CapacityPlan | null): string {
  if (!capacityPlan) {
    return "Unavailable";
  }
  if (capacityPlan.first_unprotected_horizon_minutes == null) {
    return "None in horizon";
  }
  return `+${capacityPlan.first_unprotected_horizon_minutes} min · ${formatCompactTime(
    capacityPlan.first_unprotected_at,
  )}`;
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

function buildHourlyDemandForecast(
  fullDayForecast: LoadForecastPoint[],
  horizonForecasts: DemandForecastHorizon[],
): ReadonlyMap<number, number> {
  const byHour = new Map<number, number>();

  for (const point of fullDayForecast) {
    const hour = timestampHour(point.timestamp);
    if (hour != null && Number.isFinite(point.forecast_demand_mw)) {
      byHour.set(hour, point.forecast_demand_mw);
    }
  }

  // Specific horizon results are generated directly for their target time and
  // take precedence over the broader full-day curve when both are available.
  for (const horizon of horizonForecasts) {
    const hour = timestampHour(horizon.forecast_timestamp);
    if (hour != null && Number.isFinite(horizon.forecast_demand_mw)) {
      byHour.set(hour, horizon.forecast_demand_mw);
    }
  }

  return byHour;
}

function findHourlyDemandForecast(
  forecasts: ReadonlyMap<number, number>,
  timestamp: string,
): number | null {
  const hour = timestampHour(timestamp);
  if (hour == null) return null;
  const exact = forecasts.get(hour);
  if (exact != null) return exact;

  // Present weather uses today's provider timestamps while the simulated-live
  // demand curve uses the June replay date. Match civil hour only as an
  // explicitly labelled display join; model features remain timestamp-aligned
  // in the backend.
  const targetHour = new Date(timestamp).getHours();
  for (const [candidate, value] of forecasts) {
    if (new Date(candidate * 60 * 60 * 1000).getHours() === targetHour) {
      return value;
    }
  }
  return null;
}

function timestampHour(timestamp: string): number | null {
  const milliseconds = new Date(timestamp).getTime();
  return Number.isNaN(milliseconds)
    ? null
    : Math.floor(milliseconds / (60 * 60 * 1000));
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
