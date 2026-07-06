import { useEffect, useMemo, useState } from "react";
import {
  CircleMarker,
  LayerGroup,
  LayersControl,
  MapContainer,
  Marker,
  Pane,
  Popup,
  Polyline,
  TileLayer,
  Tooltip,
  useMap,
  useMapEvents,
} from "react-leaflet";
import { divIcon } from "leaflet";
import "leaflet/dist/leaflet.css";

import {
  generationStations,
  loadCenters,
  substations,
  transmissionLines,
} from "../data/infrastructureLayers";
import { trinidadAndTobagoBoundary } from "../data/trinidadAndTobagoBoundary";
import { getStormTracking } from "../services/api";
import type { DashboardSnapshot } from "../types/dashboard";
import type { StormSystem, StormTrackingSnapshot } from "../types/storm";
import WindFlowLayer from "./WindFlowLayer";
interface WeatherMapProps {
  className?: string;
  weather: DashboardSnapshot["weather"];
}

const DEFAULT_CENTER: [number, number] = [10.6918, -61.2225];
const WIND_DIRECTION_MARKER_POSITION: [number, number] = [11.28, -61.28];
const DEFAULT_ZOOM = 8;
const ATLANTIC_OVERVIEW_MIN_ZOOM = 3;
const GIBS_GEO_COLOR_LAYER = "GOES-East_ABI_GeoColor";
const GIBS_GEO_COLOR_TILESET = "GoogleMapsCompatible_Level7";
const GIBS_PRECIP_LAYER = "IMERG_Precipitation_Rate_30min";
const GIBS_PRECIP_TILESET = "GoogleMapsCompatible_Level6";
const GIBS_BASE_LAYER = "BlueMarble_ShadedRelief_Bathymetry";
const GIBS_BASE_TILESET = "GoogleMapsCompatible_Level8";
const CLOUD_SYSTEMS_LAYER_NAME = "Cloud Systems";
const CLOUDS_LATEST = "default";
const RAIN_LATEST = "default";
const BASE_TILE_LAYER_OPTIONS = {
  keepBuffer: 6,
  updateInterval: 100,
  updateWhenIdle: false,
  updateWhenZooming: true,
  detectRetina: false,
} as const;
const WEATHER_TILE_LAYER_OPTIONS = {
  keepBuffer: 10,
  updateInterval: 150,
  updateWhenIdle: true,
  updateWhenZooming: false,
  detectRetina: false,
  noWrap: true,
} as const;
function buildGeoColorUrl(timeToken: string): string {
  return `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/${GIBS_GEO_COLOR_LAYER}/default/${timeToken}/${GIBS_GEO_COLOR_TILESET}/{z}/{y}/{x}.png`;
}

function buildPrecipitationUrl(timeToken: string): string {
  return `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/${GIBS_PRECIP_LAYER}/default/${timeToken}/${GIBS_PRECIP_TILESET}/{z}/{y}/{x}.png`;
}

function buildSatelliteBaseUrl(): string {
  return `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/${GIBS_BASE_LAYER}/default/${GIBS_BASE_TILESET}/{z}/{y}/{x}.jpeg`;
}

type PinStyle = "generation" | "substation" | "load";

function pinIcon(label: string, style: PinStyle) {
  const palette: Record<
    PinStyle,
    { background: string; border: string; radius: string; shadow: string }
  > = {
    generation: {
      background: "linear-gradient(180deg, rgba(34,197,94,0.95), rgba(21,128,61,0.9))",
      border: "rgba(187,247,208,0.95)",
      radius: "9999px",
      shadow: "0 0 12px rgba(34,197,94,0.38)",
    },
    substation: {
      background: "linear-gradient(180deg, rgba(245,158,11,0.95), rgba(180,83,9,0.92))",
      border: "rgba(254,215,170,0.95)",
      radius: "10px",
      shadow: "0 0 12px rgba(245,158,11,0.34)",
    },
    load: {
      background: "linear-gradient(180deg, rgba(34,211,238,0.95), rgba(8,145,178,0.92))",
      border: "rgba(207,250,254,0.95)",
      radius: "12px",
      shadow: "0 0 12px rgba(34,211,238,0.34)",
    },
  };

  const colors = palette[style];

  return divIcon({
    className: "",
    html: `
      <div style="
        width: 28px;
        height: 28px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: ${colors.radius};
        border: 2px solid ${colors.border};
        background: ${colors.background};
        box-shadow: ${colors.shadow};
        color: #f8fafc;
        font-size: 11px;
        font-weight: 800;
      ">
        ${label}
      </div>
    `,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
    popupAnchor: [0, -12],
  });
}

const generationIcon = pinIcon("G", "generation");
const substationIcon = pinIcon("S", "substation");
const loadIcon = pinIcon("L", "load");

function getCompassDirection(directionDegrees: number): string {
  const directions = [
    "N",
    "NNE",
    "NE",
    "ENE",
    "E",
    "ESE",
    "SE",
    "SSE",
    "S",
    "SSW",
    "SW",
    "WSW",
    "W",
    "WNW",
    "NW",
    "NNW",
  ];
  const normalizedDirection = ((directionDegrees % 360) + 360) % 360;
  return directions[Math.round(normalizedDirection / 22.5) % directions.length];
}

function windDirectionIcon(
  directionDegrees: number,
  directionLabel: string,
  zoom: number,
) {
  const flowDirection = (directionDegrees + 180) % 360;
  const normalizedZoom = Math.max(3, Math.min(11, zoom));
  const zoomScale = 0.82 + (normalizedZoom - 3) * 0.07;
  const markerSize = Math.round(52 * zoomScale);
  const iconSize = Math.max(36, markerSize);
  const arrowHeight = Math.max(22, Math.round(iconSize * 0.58));
  const arrowWidth = Math.max(4, Math.round(iconSize * 0.08));
  const labelFontSize = Math.max(10, Math.round(11 * zoomScale));
  const labelOffset = Math.max(34, Math.round(iconSize * 0.78));
  const chipPaddingX = Math.max(10, Math.round(12 * zoomScale));
  const chipPaddingY = Math.max(4, Math.round(5 * zoomScale));

  return divIcon({
    className: "",
    html: `
      <div style="
        position: relative;
        width: ${iconSize}px;
        height: ${iconSize}px;
      ">
        <div style="
          position: absolute;
          left: 50%;
          bottom: ${labelOffset}px;
          transform: translateX(-50%);
          padding: ${chipPaddingY}px ${chipPaddingX}px;
          border: 1px solid rgba(165, 243, 252, 0.72);
          border-radius: 9999px;
          background: rgba(2, 12, 27, 0.92);
          box-shadow: 0 0 18px rgba(34, 211, 238, 0.2);
          color: #ecfeff;
          font-size: ${labelFontSize}px;
          font-weight: 700;
          line-height: 1;
          letter-spacing: 0.08em;
          white-space: nowrap;
          text-transform: uppercase;
        ">${directionLabel}</div>
        <div style="
          width: ${iconSize}px;
          height: ${iconSize}px;
          display: flex;
          align-items: center;
          justify-content: center;
          border: 2px solid rgba(165, 243, 252, 0.95);
          border-radius: 9999px;
          background: rgba(8, 47, 73, 0.88);
          box-shadow: 0 0 18px rgba(34, 211, 238, 0.45);
        ">
          <div style="
            width: ${arrowWidth}px;
            height: ${arrowHeight}px;
            position: relative;
            border-radius: 9999px;
            background: #ecfeff;
            transform: rotate(${flowDirection}deg);
            transform-origin: center;
          ">
          <div style="
            position: absolute;
            top: -2px;
            left: 50%;
            width: ${Math.max(10, Math.round(iconSize * 0.22))}px;
            height: ${Math.max(10, Math.round(iconSize * 0.22))}px;
            border-top: ${Math.max(3, Math.round(iconSize * 0.07))}px solid #ecfeff;
            border-left: ${Math.max(3, Math.round(iconSize * 0.07))}px solid #ecfeff;
            transform: translateX(-50%) rotate(45deg);
          "></div>
        </div>
      </div>
    `,
    iconSize: [iconSize, iconSize + labelOffset],
    iconAnchor: [iconSize / 2, iconSize / 2],
    popupAnchor: [0, -Math.round(iconSize * 0.6)],
  });
}

function WindDirectionMarker({
  windDirection,
  windSpeedKmh,
  providerName,
}: {
  windDirection: number;
  windSpeedKmh: number;
  providerName: string;
}) {
  const map = useMap();
  const [zoom, setZoom] = useState(() => map.getZoom());
  const directionLabel = `Wind ${getCompassDirection(windDirection)}`;
  const icon = useMemo(
    () => windDirectionIcon(windDirection, directionLabel, zoom),
    [directionLabel, windDirection, zoom],
  );

  useMapEvents({
    zoomend() {
      setZoom(map.getZoom());
    },
  });

  return (
    <Marker position={WIND_DIRECTION_MARKER_POSITION} icon={icon}>
      <Popup>
        <div className="space-y-1 text-sm">
          <p className="font-semibold">Current Wind Direction</p>
          <p>
            From {getCompassDirection(windDirection)} at {windDirection.toFixed(0)}{" "}
            degrees
          </p>
          <p>{windSpeedKmh.toFixed(1)} km/h</p>
          <p className="text-slate-500">Live source: {providerName}</p>
        </div>
      </Popup>
    </Marker>
  );
}

export default function WeatherMap({
  className = "",
  weather,
}: WeatherMapProps) {
  const [hurricaneEnabled, setHurricaneEnabled] = useState(false);
  const [windFlowEnabled, setWindFlowEnabled] = useState(false);
  const [windFlowStatus, setWindFlowStatus] = useState<
    "loading" | "active" | "error"
  >("loading");
  const [stormTracking, setStormTracking] = useState<StormTrackingSnapshot | null>(null);
  const [stormTrackingFailed, setStormTrackingFailed] = useState(false);

  const cloudSystemsTileUrl = useMemo(
    () => buildGeoColorUrl(CLOUDS_LATEST),
    [],
  );
  const rainfallTileUrl = useMemo(
    () => buildPrecipitationUrl(RAIN_LATEST),
    [],
  );
  const satelliteBaseUrl = useMemo(() => buildSatelliteBaseUrl(), []);
  const windDirection =
    weather.wind_direction_deg != null &&
    Number.isFinite(weather.wind_direction_deg)
      ? weather.wind_direction_deg
      : null;
  useEffect(() => {
    if (!hurricaneEnabled) {
      return;
    }

    let cancelled = false;

    const loadStormTracking = async () => {
      setStormTrackingFailed(false);
      try {
        const payload = await getStormTracking({ forceRefresh: true });
        if (!cancelled) {
          setStormTracking(payload);
          setStormTrackingFailed(payload.status === "unavailable");
        }
      } catch {
        if (!cancelled) {
          setStormTracking(null);
          setStormTrackingFailed(true);
        }
      }
    };

    void loadStormTracking();
    const refreshInterval = window.setInterval(() => {
      void loadStormTracking();
    }, 15 * 60 * 1000);

    return () => {
      cancelled = true;
      window.clearInterval(refreshInterval);
    };
  }, [hurricaneEnabled]);

  const activeStorms = stormTracking?.active_storms ?? [];

  return (
    <div className={`flex h-full w-full min-w-0 flex-col rounded-2xl border border-cyan-500/15 bg-slate-900/80 p-2 shadow-[0_0_40px_rgba(8,145,178,0.08)] ${className}`}>
      <div className="mb-1 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">
            Weather Map
          </p>
          <h2 className="mt-1 text-xl font-semibold text-white">
            Trinidad and Tobago Operations Map
          </h2>
        </div>
        <span className="rounded-full border border-slate-700 px-3 py-1 text-xs font-medium text-slate-300">
          {!hurricaneEnabled
            ? "Storm tracking off"
            : stormTrackingFailed
              ? "Storm feed unavailable"
              : stormTracking === null
                ? "Checking NHC storms"
                : activeStorms.length === 0
                  ? "No active NHC storms"
                  : `${activeStorms.length} active storm${activeStorms.length === 1 ? "" : "s"}`}
        </span>
      </div>

      <div className="relative min-h-0 flex-1 overflow-hidden rounded-xl border border-slate-800 bg-slate-950">
        <div className="pointer-events-none absolute inset-0 z-[400] border border-cyan-400/5 bg-[radial-gradient(circle_at_top,rgba(34,211,238,0.12),transparent_45%)]" />
        <MapContainer
          center={DEFAULT_CENTER}
          zoom={DEFAULT_ZOOM}
          minZoom={ATLANTIC_OVERVIEW_MIN_ZOOM}
          maxZoom={11}
          scrollWheelZoom={false}
          fadeAnimation={false}
          className="h-full w-full"
        >
          <MapResizeSync />
          <MapViewSync />
          <MapTileStabilizer />
          <MapOverlaySync
            onHurricaneChange={setHurricaneEnabled}
            onWindFlowChange={setWindFlowEnabled}
          />
          {windFlowEnabled ? (
            <WindFlowLayer onStatusChange={setWindFlowStatus} />
          ) : null}

          <LayersControl position="topright">
            <LayersControl.BaseLayer name="OpenStreetMap">
              <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
                {...BASE_TILE_LAYER_OPTIONS}
              />
            </LayersControl.BaseLayer>

            <LayersControl.BaseLayer checked name="NASA Blue Marble">
              <TileLayer
                attribution="Satellite imagery &copy; NASA Earth Observatory / GIBS"
                url={satelliteBaseUrl}
                maxNativeZoom={8}
                maxZoom={11}
                {...BASE_TILE_LAYER_OPTIONS}
              />
            </LayersControl.BaseLayer>

            <LayersControl.Overlay checked name={CLOUD_SYSTEMS_LAYER_NAME}>
              <LayerGroup>
                {cloudSystemsTileUrl ? (
                  <TileLayer
                    attribution="Cloud imagery &copy; NASA GIBS / NOAA"
                    opacity={0.78}
                    maxNativeZoom={7}
                    maxZoom={11}
                    zIndex={500}
                    pane="overlayPane"
                    url={cloudSystemsTileUrl}
                    {...WEATHER_TILE_LAYER_OPTIONS}
                  />
                ) : null}
              </LayerGroup>
            </LayersControl.Overlay>

            <LayersControl.Overlay checked name="Rainfall Coverage">
              <LayerGroup>
                {rainfallTileUrl ? (
                  <TileLayer
                    attribution="Rain imagery &copy; NASA GIBS / NASA GPM"
                    opacity={0.72}
                    maxNativeZoom={6}
                    maxZoom={11}
                    zIndex={490}
                    pane="overlayPane"
                    url={rainfallTileUrl}
                    {...WEATHER_TILE_LAYER_OPTIONS}
                  />
                ) : null}
              </LayerGroup>
            </LayersControl.Overlay>

            <LayersControl.Overlay checked name="Wind Direction">
              <LayerGroup>
                {windDirection != null ? (
                  <WindDirectionMarker
                    windDirection={windDirection}
                    windSpeedKmh={weather.wind_speed_kmh}
                    providerName={weather.provider_name}
                  />
                ) : null}
              </LayerGroup>
            </LayersControl.Overlay>

            <LayersControl.Overlay name="Wind Flow">
              <LayerGroup />
            </LayersControl.Overlay>

            <LayersControl.Overlay name="Generation Stations">
              <LayerGroup>
                {generationStations.map((station) => (
                  <Marker
                    key={station.id}
                    position={[station.lat, station.lon]}
                    icon={generationIcon}
                  >
                    <Popup>
                      <div className="text-sm">
                        <p className="font-semibold">{station.name}</p>
                        <p>{station.region}</p>
                      </div>
                    </Popup>
                  </Marker>
                ))}
              </LayerGroup>
            </LayersControl.Overlay>

            <LayersControl.Overlay name="Substations">
              <LayerGroup>
                {substations.map((station) => (
                  <Marker
                    key={station.id}
                    position={[station.lat, station.lon]}
                    icon={substationIcon}
                  >
                    <Popup>
                      <div className="text-sm">
                        <p className="font-semibold">{station.name}</p>
                        <p>{station.region}</p>
                      </div>
                    </Popup>
                  </Marker>
                ))}
              </LayerGroup>
            </LayersControl.Overlay>

            <LayersControl.Overlay name="Transmission Lines">
              <LayerGroup>
                {transmissionLines.map((line) => (
                  <Polyline
                    key={line.id}
                    positions={line.coordinates}
                    pathOptions={{
                      color: "#60a5fa",
                      weight: 4,
                      opacity: 0.85,
                      dashArray: "8 8",
                    }}
                  >
                    <Tooltip sticky>{line.name}</Tooltip>
                  </Polyline>
                ))}
              </LayerGroup>
            </LayersControl.Overlay>

            <LayersControl.Overlay name="Load Centers">
              <LayerGroup>
                {loadCenters.map((center) => (
                  <Marker key={center.id} position={[center.lat, center.lon]} icon={loadIcon}>
                    <Popup>
                      <div className="text-sm">
                        <p className="font-semibold">{center.name}</p>
                        <p>{center.region}</p>
                      </div>
                    </Popup>
                  </Marker>
                ))}
              </LayerGroup>
            </LayersControl.Overlay>

            <LayersControl.Overlay name="Operations Center">
              <CircleMarker
                center={DEFAULT_CENTER}
                radius={11}
                pathOptions={{
                  color: "#06b6d4",
                  fillColor: "#06b6d4",
                  fillOpacity: 0.4,
                }}
              >
                <Popup>
                  <div className="text-sm">
                    <p className="font-semibold">T&amp;TEC Operations</p>
                    <p>Trinidad centered default view</p>
                  </div>
                </Popup>
              </CircleMarker>
            </LayersControl.Overlay>

            <LayersControl.Overlay checked={hurricaneEnabled} name="Hurricane / Tropical Storm Tracking">
              <LayerGroup>
                {activeStorms.map((storm) => {
                  const position = getStormPosition(storm);
                  if (!position) {
                    return null;
                  }

                  const palette = getStormPalette(storm.classification);
                  const radius = getStormRadius(storm.intensity_knots);
                  const title = storm.name ?? storm.classification_label ?? "Active Storm";

                  return (
                    <CircleMarker
                      key={storm.id}
                      center={position}
                      radius={radius}
                      pathOptions={{
                        color: palette.stroke,
                        fillColor: palette.fill,
                        fillOpacity: 0.45,
                        weight: 2,
                      }}
                    >
                      <Tooltip sticky>{title}</Tooltip>
                      <Popup>
                        <div className="space-y-2 text-sm">
                          <div>
                            <p className="font-semibold">{title}</p>
                            <p className="text-slate-500">
                              {storm.classification_label ?? storm.classification ?? "Storm"}
                              {storm.basin ? ` · ${storm.basin}` : ""}
                            </p>
                          </div>
                          <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-slate-700">
                            <dt className="font-medium">Intensity</dt>
                            <dd>{storm.intensity_knots != null ? `${storm.intensity_knots.toFixed(0)} kt` : "--"}</dd>
                            <dt className="font-medium">Pressure</dt>
                            <dd>{storm.pressure_mb != null ? `${storm.pressure_mb.toFixed(0)} mb` : "--"}</dd>
                            <dt className="font-medium">Movement</dt>
                            <dd>
                              {storm.movement_direction_deg != null
                                ? `${storm.movement_direction_deg.toFixed(0)}°`
                                : "--"}
                              {storm.movement_speed_mph != null ? ` at ${storm.movement_speed_mph.toFixed(0)} mph` : ""}
                            </dd>
                            <dt className="font-medium">Position</dt>
                            <dd>
                              {storm.latitude ?? "--"} {storm.longitude ?? ""}
                            </dd>
                          </dl>
                          <div className="flex flex-wrap gap-2">
                            {storm.public_advisory?.url ? (
                              <a
                                className="rounded-full border border-cyan-600/30 bg-cyan-500/10 px-2.5 py-1 text-[11px] font-semibold text-cyan-900 hover:bg-cyan-500/20"
                                href={storm.public_advisory.url}
                                target="_blank"
                                rel="noreferrer"
                              >
                                Public Advisory
                              </a>
                            ) : null}
                            {storm.forecast_graphics?.url ? (
                              <a
                                className="rounded-full border border-slate-300 bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-900 hover:bg-slate-200"
                                href={storm.forecast_graphics.url}
                                target="_blank"
                                rel="noreferrer"
                              >
                                Forecast Graphics
                              </a>
                            ) : null}
                          </div>
                        </div>
                      </Popup>
                    </CircleMarker>
                  );
                })}
              </LayerGroup>
            </LayersControl.Overlay>
          </LayersControl>

          <Pane
            name="country-boundary"
            style={{ zIndex: 550, pointerEvents: "none" }}
          >
            {trinidadAndTobagoBoundary.map((ring, index) => (
              <LayerGroup key={`country-boundary-${index}`}>
                <Polyline
                  positions={ring}
                  interactive={false}
                  pathOptions={{
                    color: "#020617",
                    weight: 6,
                    opacity: 0.88,
                    lineCap: "round",
                    lineJoin: "round",
                  }}
                />
                <Polyline
                  positions={ring}
                  interactive={false}
                  pathOptions={{
                    color: "#67e8f9",
                    weight: 2.5,
                    opacity: 1,
                    lineCap: "round",
                    lineJoin: "round",
                  }}
                />
              </LayerGroup>
            ))}
          </Pane>
        </MapContainer>
        {windFlowEnabled ? (
          <div className="pointer-events-none absolute bottom-2 right-2 z-[1000] rounded-md border border-cyan-400/30 bg-slate-950/85 px-2.5 py-1.5 text-[11px] font-semibold text-cyan-100 shadow-lg backdrop-blur">
            {windFlowStatus === "active"
              ? "Live wind flow · Open-Meteo"
              : windFlowStatus === "loading"
                ? "Loading wind flow..."
                : "Wind flow temporarily unavailable"}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function getStormPalette(classification?: string | null) {
  const normalized = (classification ?? "").trim().toUpperCase();
  if (normalized.includes("HURRICANE") || normalized === "HU") {
    return { stroke: "#ef4444", fill: "#f97316" };
  }
  if (normalized.includes("STORM") || normalized === "TS" || normalized === "STS") {
    return { stroke: "#f59e0b", fill: "#fb7185" };
  }
  if (normalized.includes("DEPRESSION") || normalized === "TD") {
    return { stroke: "#60a5fa", fill: "#38bdf8" };
  }
  if (normalized === "PTC") {
    return { stroke: "#a855f7", fill: "#c084fc" };
  }
  return { stroke: "#22d3ee", fill: "#06b6d4" };
}

function getStormRadius(intensityKnots?: number | null) {
  const intensity = intensityKnots ?? 0;
  return Math.max(7, Math.min(18, 7 + intensity / 10));
}

function getStormPosition(storm: StormSystem): [number, number] | null {
  if (storm.latitude_numeric != null && storm.longitude_numeric != null) {
    return [storm.latitude_numeric, storm.longitude_numeric];
  }

  const latitude = parseStormCoordinate(storm.latitude);
  const longitude = parseStormCoordinate(storm.longitude);
  if (latitude == null || longitude == null) {
    return null;
  }

  return [latitude, longitude];
}

function parseStormCoordinate(value?: string | null): number | null {
  if (!value) {
    return null;
  }

  const trimmed = value.trim().toUpperCase();
  const match = trimmed.match(/^([0-9]+(?:\.[0-9]+)?)([NSEW])$/);
  if (!match) {
    const numeric = Number(trimmed);
    return Number.isFinite(numeric) ? numeric : null;
  }

  const magnitude = Number(match[1]);
  if (!Number.isFinite(magnitude)) {
    return null;
  }

  const direction = match[2];
  return direction === "S" || direction === "W" ? -magnitude : magnitude;
}

function MapOverlaySync({
  onHurricaneChange,
  onWindFlowChange,
}: {
  onHurricaneChange: (enabled: boolean) => void;
  onWindFlowChange: (enabled: boolean) => void;
}) {
  useMapEvents({
    overlayadd(event) {
      if (event.name === "Hurricane / Tropical Storm Tracking") {
        onHurricaneChange(true);
      }
      if (event.name === "Wind Flow") {
        onWindFlowChange(true);
      }
    },
    overlayremove(event) {
      if (event.name === "Hurricane / Tropical Storm Tracking") {
        onHurricaneChange(false);
      }
      if (event.name === "Wind Flow") {
        onWindFlowChange(false);
      }
    },
  });

  return null;
}

function MapResizeSync() {
  const map = useMap();

  useEffect(() => {
    const invalidate = () => {
      window.requestAnimationFrame(() => {
        map.invalidateSize();
      });
    };

    invalidate();

    const handleResize = () => invalidate();
    window.addEventListener("resize", handleResize);

    const container = map.getContainer();
    const observer =
      typeof ResizeObserver !== "undefined" ? new ResizeObserver(handleResize) : null;

    observer?.observe(container);

    return () => {
      window.removeEventListener("resize", handleResize);
      observer?.disconnect();
    };
  }, [map]);

  return null;
}

function MapViewSync() {
  const map = useMap();

  useEffect(() => {
    map.setView(DEFAULT_CENTER, DEFAULT_ZOOM, { animate: false });
  }, [map]);

  return null;
}

function MapTileStabilizer() {
  const map = useMap();

  useMapEvents({
    moveend() {
      window.setTimeout(() => map.invalidateSize(), 75);
    },
    zoomend() {
      window.setTimeout(() => map.invalidateSize(), 75);
    },
  });

  return null;
}
