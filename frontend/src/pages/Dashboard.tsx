import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import CurrentConditions from "../components/CurrentConditions";
import DemandForecastChart from "../components/DemandForecastChart";
import Header from "../components/Header";
import ProbabilityGauge from "../components/ProbabilityGauge";
import ScenarioComparisonChart from "../components/ScenarioComparisonChart";
import WeatherMap from "../components/WeatherMap";
import { getDashboardSnapshot } from "../services/api";
import type { CalibrationSnapshot, DashboardSnapshot, ForecastData } from "../types/dashboard";

type LoadState = "loading" | "ready" | "error";
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
  grid_status: "Unavailable",
  demand_period: "Unavailable",
  source_provider: "Unavailable",
  generation_units: [],
};

const FALLBACK_PROBABILITY: DashboardSnapshot["probability"] = {
  probability_score: 0,
  risk_level: "LOW",
  forecast_demand_30m: 0,
  forecast_demand_60m: 0,
  factors: [],
  reason: "No live probability data available.",
};

const FALLBACK_RECOMMENDATION: DashboardSnapshot["recommendation"] = {
  ...FALLBACK_PROBABILITY,
  recommendation: "NO ACTION REQUIRED",
};

export default function Dashboard() {
  const [state, setState] = useState<LoadState>("loading");
  const [snapshot, setSnapshot] = useState<DashboardSnapshot | null>(null);
  const [error, setError] = useState<string>("");
  const [refreshError, setRefreshError] = useState<string>("");
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
    const refreshInterval = window.setInterval(() => {
      void loadSnapshot({ forceRefresh: false, showLoading: false });
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

  const weather = snapshot.weather ?? FALLBACK_WEATHER;
  const grid = snapshot.grid ?? FALLBACK_GRID;
  const probability = snapshot.probability ?? FALLBACK_PROBABILITY;
  const recommendation = snapshot.recommendation ?? FALLBACK_RECOMMENDATION;
  const calibration = snapshot.calibration ?? null;
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
  const upcomingForecastItems = getUpcomingForecastItems(forecastItems, new Date(), 6);

  return (
    <Shell
      lastUpdated={weather.timestamp}
      systemStatus={systemStatus}
      gridStatus={grid.grid_status}
      weatherStatus={dataQuality.weather_status}
      forecastStatus={dataQuality.weather_status}
      scenarioLabel={calibration?.selected_scenario_label ?? "Typical Day"}
      dataQuality={dataQuality}
      refreshError={refreshError}
    >
      <div className="grid h-auto min-h-0 w-full min-w-0 gap-3 xl:h-full xl:grid-cols-[clamp(300px,28vw,390px)_minmax(0,1fr)] xl:items-stretch">
        <section className="h-[28rem] min-h-0 min-w-0 xl:sticky xl:top-3 xl:self-start xl:h-[calc(100vh-5.25rem)]">
          <WeatherMap
            className="h-full min-h-0"
            weather={weather}
          />
        </section>

        <section className="flex min-h-[42rem] w-full min-w-0 flex-col overflow-visible rounded-2xl border border-cyan-500/15 bg-slate-900/60 p-2.5 shadow-[0_0_40px_rgba(8,145,178,0.06)] xl:min-h-0 xl:overflow-hidden">
          <div className="flex h-full min-h-0 w-full min-w-0 flex-col gap-2.5 overflow-hidden">
            <TabBar activeTab={activeTab} onChange={setActiveTab} />

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
                  />
                </WorkspacePage>
              ) : null}

              {activeTab === "riskGauge" ? (
                <WorkspacePage>
                  <RiskGaugeTab probability={probability} />
                </WorkspacePage>
              ) : null}

              {activeTab === "operationalGuidance" ? (
                <WorkspacePage>
                  <OperationalGuidanceTab
                    grid={grid}
                    recommendation={recommendation}
                  />
                </WorkspacePage>
              ) : null}

              {activeTab === "analytics" ? (
                <WorkspacePage>
                  <AnalyticsTab
                    calibration={calibration}
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
}) {
  return (
    <div className="flex min-h-dvh flex-col overflow-visible bg-[radial-gradient(circle_at_top,_rgba(14,116,144,0.18),_transparent_36%),linear-gradient(180deg,#020617_0%,#020617_100%)] text-slate-100 xl:h-dvh xl:overflow-hidden">
      <Header
        lastUpdated={lastUpdated}
        systemStatus={systemStatus}
        gridStatus={gridStatus}
        weatherStatus={weatherStatus}
        forecastStatus={forecastStatus}
        scenarioLabel={scenarioLabel}
        dataQuality={dataQuality}
        refreshError={refreshError}
      />
      <main className="flex w-full min-w-0 flex-1 min-h-0 overflow-visible px-4 py-2.5 lg:px-6 xl:overflow-hidden">
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
  calibration,
}: {
  grid: DashboardSnapshot["grid"];
  weather: DashboardSnapshot["weather"];
  probability: DashboardSnapshot["probability"];
  recommendation: DashboardSnapshot["recommendation"];
  forecastItems: ForecastData[];
  calibration: CalibrationSnapshot | null;
}) {
  return (
    <>
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
        <SummaryTile label="Demand" value={`${grid.current_demand_mw.toFixed(0)} MW`} tone="cyan" />
        <SummaryTile label="Generation" value={`${grid.current_generation_mw.toFixed(0)} MW`} tone="emerald" />
        <SummaryTile label="Reserve Margin" value={`${grid.reserve_margin_percent.toFixed(1)}%`} tone="amber" />
        <SummaryTile label="Probability" value={formatProbability(probability)} tone="rose" />
        <SummaryTile label="Action" value={recommendation.recommendation} tone="slate" compactValue />
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
    <div className="home-forecast-card flex h-full min-h-0 w-full min-w-0 flex-col overflow-hidden rounded-2xl border border-cyan-500/15 bg-slate-900/80 p-2.5 shadow-[0_0_34px_rgba(8,145,178,0.08)]">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">
            Demand Forecast
          </p>
          <h2 className="mt-1 text-[0.94rem] font-semibold leading-tight text-white">
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
    <div className="home-weather-card flex h-full min-h-0 w-full min-w-0 flex-col overflow-hidden rounded-2xl border border-cyan-500/15 bg-slate-900/80 p-2.5 shadow-[0_0_34px_rgba(8,145,178,0.08)]">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">
            Weather Drivers
          </p>
          <h2 className="mt-1 text-[0.98rem] font-semibold leading-tight text-white">
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
}: {
  grid: DashboardSnapshot["grid"];
}) {
  const generationBalance =
    grid.current_generation_mw - grid.current_demand_mw;
  const capacityHeadroom =
    grid.total_available_capacity_mw - grid.current_demand_mw;
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
          label="Total Generation"
          value={`${grid.current_generation_mw.toFixed(0)} MW`}
          tone="emerald"
        />
        <SummaryTile
          label="Available Capacity"
          value={`${grid.total_available_capacity_mw.toFixed(0)} MW`}
          tone="cyan"
        />
        <SummaryTile
          label="Reserve Margin"
          value={`${grid.reserve_margin_percent.toFixed(1)}%`}
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
                      <StationDatum label="Output" value={`${station.outputMw.toFixed(0)} MW`} />
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
                label="Capacity Headroom"
                value={formatSignedMegawatts(capacityHeadroom)}
              />
              <MiniMetric
                label="Generation Balance"
                value={formatSignedMegawatts(generationBalance)}
              />
              <MiniMetric label="Demand Period" value={grid.demand_period} />
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
                            label="Output"
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
}: {
  grid: DashboardSnapshot["grid"];
  probability: DashboardSnapshot["probability"];
  calibration: CalibrationSnapshot | null;
}) {
  const demandDelta30 = probability.forecast_demand_30m - grid.current_demand_mw;
  const demandDelta60 = probability.forecast_demand_60m - grid.current_demand_mw;

  return (
    <div className="grid h-full min-h-0 w-full min-w-0 grid-cols-1 gap-2 xl:grid-cols-[minmax(0,1.12fr)_minmax(0,0.88fr)]">
      <DemandForecastChart
        gridStatus={grid}
        probability={probability}
        calibration={calibration}
        className="h-full min-h-0 w-full min-w-0"
      />
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
        </div>
      </PanelCard>
    </div>
  );
}

function RiskGaugeTab({
  probability,
}: {
  probability: DashboardSnapshot["probability"];
}) {
  const factors =
    Array.isArray(probability.factors) && probability.factors.length > 0
      ? probability.factors
      : [probability.reason];
  const driverDirections = factors.map(getRiskDriverDirection);
  const upwardDrivers = driverDirections.filter(
    (direction) => direction === "upward",
  ).length;
  const downwardDrivers = driverDirections.filter(
    (direction) => direction === "downward",
  ).length;
  const highRiskGap = Math.max(0, 0.7 - probability.probability_score);

  return (
    <div className="grid h-full min-h-0 w-full min-w-0 grid-cols-1 gap-2.5 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
      <ProbabilityGauge probability={probability} className="h-full min-h-0 w-full min-w-0" />
      <PanelCard title="Risk Factors" className="h-full min-h-0 w-full min-w-0">
        <div className="grid h-full min-h-0 grid-rows-[minmax(0,1fr)_auto] gap-2">
          <ol className="grid min-h-0 auto-rows-fr gap-2 overflow-auto sm:grid-cols-2">
            {factors.map((factor, index) => {
              const direction = driverDirections[index];
              return (
                <li
                  key={`${factor}-${index}`}
                  className="flex min-h-[6rem] flex-col justify-between rounded-xl border border-slate-800 bg-slate-950/60 p-3 text-sm leading-snug text-slate-200"
                >
                  <div className="flex items-start gap-3">
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-amber-500/30 bg-amber-500/10 text-xs font-semibold text-amber-200">
                      {index + 1}
                    </span>
                    <span className="min-w-0 break-words">{factor}</span>
                  </div>
                  <span
                    className={`mt-3 self-end rounded-full border px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.1em] ${
                      direction === "downward"
                        ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-200"
                        : direction === "upward"
                          ? "border-rose-500/25 bg-rose-500/10 text-rose-200"
                          : "border-slate-700 bg-slate-900 text-slate-300"
                    }`}
                  >
                    {direction === "downward"
                      ? "Reduces risk"
                      : direction === "upward"
                        ? "Raises risk"
                        : "Context"}
                  </span>
                </li>
              );
            })}
          </ol>

          <div className="grid grid-cols-2 gap-2 xl:grid-cols-4">
            <MiniMetric label="Drivers Evaluated" value={`${factors.length}`} />
            <MiniMetric label="Upward Drivers" value={`${upwardDrivers}`} />
            <MiniMetric label="Downward Drivers" value={`${downwardDrivers}`} />
            <MiniMetric
              label="Gap to High Risk"
              value={probability.probability_score >= 0.7 ? "At high risk" : highRiskGap.toFixed(2)}
            />
          </div>
        </div>
      </PanelCard>
    </div>
  );
}

function getRiskDriverDirection(
  factor: string,
): "upward" | "downward" | "neutral" {
  const normalized = factor.toLowerCase();
  if (
    normalized.includes("decrease") ||
    normalized.includes("reduced") ||
    normalized.includes("lower expected")
  ) {
    return "downward";
  }
  if (
    normalized.includes("increase") ||
    normalized.includes("higher") ||
    normalized.includes("below") ||
    normalized.includes("high ")
  ) {
    return "upward";
  }
  return "neutral";
}

function OperationalGuidanceTab({
  grid,
  recommendation,
}: {
  grid: DashboardSnapshot["grid"];
  recommendation: DashboardSnapshot["recommendation"];
}) {
  const headroom30 =
    grid.total_available_capacity_mw - recommendation.forecast_demand_30m;
  const headroom60 =
    grid.total_available_capacity_mw - recommendation.forecast_demand_60m;
  const operatorActions = getOperatorActions(recommendation.recommendation);
  const decisionAvailable = recommendation.risk_level !== "UNAVAILABLE";

  return (
    <div className="grid h-full min-h-0 w-full min-w-0 gap-2.5 overflow-hidden xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div className="grid min-h-0 auto-rows-fr gap-2 overflow-auto rounded-2xl border border-cyan-500/15 bg-slate-900/80 p-2.5 shadow-[0_0_34px_rgba(8,145,178,0.08)] sm:grid-cols-2">
            {operatorActions.map((action, index) => (
              <div
                key={action}
                className="flex min-h-[4rem] items-center gap-3 rounded-xl border border-slate-800 bg-slate-950/60 px-3 py-2.5 shadow-inner shadow-black/20"
              >
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-emerald-500/25 bg-emerald-500/10 text-xs font-semibold text-emerald-200">
                  {index + 1}
                </span>
                <p className="min-w-0 break-words text-[0.8rem] font-medium leading-snug text-slate-100">
                  {action}
                </p>
              </div>
            ))}
      </div>

      <div className="grid min-h-0 grid-cols-2 auto-rows-fr gap-2 rounded-2xl border border-cyan-500/15 bg-slate-900/80 p-2.5 shadow-[0_0_34px_rgba(8,145,178,0.08)]">
            <GuidanceThreshold
              label="Probability"
              value={formatProbability(recommendation)}
              context="High-risk trigger 0.70"
              healthy={decisionAvailable && recommendation.probability_score < 0.7}
            />
            <GuidanceThreshold
              label="Reserve"
              value={`${grid.reserve_margin_percent.toFixed(1)}%`}
              context="Planning floor 15%"
              healthy={grid.reserve_margin_percent >= 15}
            />
            <GuidanceThreshold
              label="30m Headroom"
              value={formatSignedMegawatts(headroom30)}
              context="Available capacity less forecast"
              healthy={headroom30 >= 0}
            />
            <GuidanceThreshold
              label="60m Headroom"
              value={formatSignedMegawatts(headroom60)}
              context="Available capacity less forecast"
              healthy={headroom60 >= 0}
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

function getOperatorActions(recommendation: string): string[] {
  if (recommendation === "DATA UNAVAILABLE") {
    return [
      "Verify weather and grid telemetry health before acting on WGDSS guidance.",
      "Use the last approved dispatch plan and established control-room procedures.",
      "Notify the control-room supervisor that automated guidance is inhibited.",
      "Reassess only after telemetry quality returns to GOOD.",
    ];
  }

  if (recommendation === "START ADDITIONAL TURBINE") {
    return [
      "Initiate the approved turbine start sequence.",
      "Confirm synchronization and expected unit output.",
      "Recalculate reserve margin after the unit is online.",
      "Notify the control-room supervisor of dispatch completion.",
    ];
  }

  if (recommendation === "MONITOR CONDITIONS") {
    return [
      "Maintain current dispatch while monitoring demand movement.",
      "Confirm an additional dispatchable unit remains start-ready.",
      "Review reserve and forecast headroom at the next update.",
      "Escalate if probability reaches 0.70 or reserve falls below 15%.",
    ];
  }

  return [
    "Maintain the current generation commitment.",
    "Continue routine demand and reserve surveillance.",
    "Verify dispatchable units remain available.",
    "Reassess when the next dashboard snapshot arrives.",
  ];
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

function AnalyticsTab({ calibration }: { calibration: CalibrationSnapshot | null }) {
  return (
    <div className="grid h-full min-h-0 w-full min-w-0 gap-2.5 xl:grid-cols-[minmax(260px,0.36fr)_minmax(0,0.64fr)]">
      <PanelCard title="Calibration Summary" className="h-full min-h-0">
        <div className="grid h-full min-h-0 auto-rows-fr grid-cols-2 gap-2">
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
        </div>
      </PanelCard>

      <ScenarioComparisonChart
        scenarios={calibration?.scenarios ?? []}
        selectedScenarioKey={calibration?.selected_scenario_key}
        className="h-full min-h-0 w-full min-w-0"
      />
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

function formatSignedMegawatts(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(0)} MW`;
}

function formatProbability(
  probability: DashboardSnapshot["probability"],
): string {
  return probability.risk_level === "UNAVAILABLE"
    ? "--"
    : probability.probability_score.toFixed(2);
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
