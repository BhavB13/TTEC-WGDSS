import { useEffect, useMemo, useState } from "react";
import {
  CircleMarker,
  Circle,
  LayerGroup,
  LayersControl,
  MapContainer,
  Marker,
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
import {
  canUseOpenWeatherCloudLayer,
  getOpenWeatherQuotaMessage,
  getOpenWeatherQuotaState,
  recordOpenWeatherTileRequest,
} from "../services/openweatherQuota";
import type { GridStatus } from "../types/dashboard";

interface WeatherMapProps {
  gridStatus: GridStatus;
  rainfallMmHr: number;
  className?: string;
}

type MapPoint = {
  lat: number;
  lon: number;
  label: string;
  value: string;
  status: string;
};

const DEFAULT_CENTER: [number, number] = [10.6918, -61.2225];
const DEFAULT_ZOOM = 8;
const OPENWEATHER_CLOUD_TILE_URL =
  "https://tile.openweathermap.org/map/clouds_new/{z}/{x}/{y}.png?appid={API_KEY}";
const TOBAGO_CENTER: [number, number] = [11.1833, -60.7333];

const generationCoordinates: Record<string, [number, number]> = {
  "Point Lisas": [10.388, -61.5],
  Cove: [10.534, -61.459],
  Penal: [10.166, -61.44],
  "La Brea": [10.236, -61.63],
};

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

function getRainfallCategory(rainfallMmHr: number): {
  label: string;
  color: string;
  fillOpacity: number;
} {
  if (rainfallMmHr <= 0) {
    return { label: "No Rain", color: "#38bdf8", fillOpacity: 0 };
  }

  if (rainfallMmHr <= 2) {
    return { label: "Light Rain", color: "#7dd3fc", fillOpacity: 0.16 };
  }

  if (rainfallMmHr <= 8) {
    return { label: "Moderate Rain", color: "#3b82f6", fillOpacity: 0.2 };
  }

  if (rainfallMmHr <= 15) {
    return { label: "Heavy Rain", color: "#f59e0b", fillOpacity: 0.24 };
  }

  return { label: "Severe Rain", color: "#ef4444", fillOpacity: 0.28 };
}

function getRainfallRadius(rainfallMmHr: number): number {
  if (rainfallMmHr <= 0) {
    return 0;
  }

  if (rainfallMmHr <= 2) {
    return 22000;
  }

  if (rainfallMmHr <= 8) {
    return 32000;
  }

  if (rainfallMmHr <= 15) {
    return 44000;
  }

  return 56000;
}

export default function WeatherMap({
  gridStatus,
  rainfallMmHr,
  className = "",
}: WeatherMapProps) {
  const [cloudEnabled, setCloudEnabled] = useState(false);
  const [cloudNotice, setCloudNotice] = useState<string | null>(null);
  const [cloudQuotaState, setCloudQuotaState] = useState(() => getOpenWeatherQuotaState());
  const [hurricaneEnabled, setHurricaneEnabled] = useState(false);
  const openWeatherApiKey = import.meta.env.VITE_OPENWEATHER_MAP_API_KEY?.trim() ?? "";
  const hasOpenWeatherApiKey = openWeatherApiKey.length > 0;

  const points = useMemo<MapPoint[]>(
    () =>
      gridStatus.generation_units.map((unit) => {
        const [lat, lon] = generationCoordinates[unit.station_name] ?? DEFAULT_CENTER;
        return {
          lat,
          lon,
          label: `${unit.station_name} - ${unit.unit_name}`,
          value: `${unit.current_output_mw.toFixed(0)} MW`,
          status: unit.status,
        };
      }),
    [gridStatus.generation_units],
  );

  const cloudOverlayAllowed = canUseOpenWeatherCloudLayer(hasOpenWeatherApiKey);
  const cloudTileUrl =
    cloudEnabled && cloudOverlayAllowed
      ? OPENWEATHER_CLOUD_TILE_URL.replace("{API_KEY}", openWeatherApiKey)
      : null;
  const rainfallCategory = getRainfallCategory(rainfallMmHr);
  const rainfallRadius = getRainfallRadius(rainfallMmHr);
  const rainfallCenters = rainfallMmHr > 0 ? [DEFAULT_CENTER, TOBAGO_CENTER] : [];

  const quotaMessage = getOpenWeatherQuotaMessage(cloudQuotaState);

  function handleCloudTileLoad() {
    const nextQuota = recordOpenWeatherTileRequest();
    setCloudQuotaState(nextQuota);

    if (nextQuota.limitReached) {
      setCloudEnabled(false);
      setCloudNotice("OpenWeather daily limit reached. Cloud overlay disabled.");
    }
  }

  function handleCloudTileError() {
    setCloudNotice("Cloud overlay unavailable: missing OpenWeatherMap API key");
    setCloudEnabled(false);
  }

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
          Leaflet
        </span>
      </div>

      <div className="relative min-h-0 flex-1 overflow-hidden rounded-xl border border-slate-800 bg-slate-950">
        <div className="pointer-events-none absolute inset-0 z-[400] border border-cyan-400/5 bg-[radial-gradient(circle_at_top,rgba(34,211,238,0.12),transparent_45%)]" />
        <MapContainer
          center={DEFAULT_CENTER}
          zoom={DEFAULT_ZOOM}
          scrollWheelZoom={false}
          className="h-full w-full"
        >
          <MapResizeSync />
          <MapOverlaySync
            hasOpenWeatherApiKey={hasOpenWeatherApiKey}
            quotaReached={quotaMessage !== null}
            onCloudChange={setCloudEnabled}
            onCloudNotice={setCloudNotice}
            onHurricaneChange={setHurricaneEnabled}
          />

          <LayersControl position="topright">
            <LayersControl.BaseLayer name="OpenStreetMap">
              <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
            </LayersControl.BaseLayer>

            <LayersControl.BaseLayer checked name="Esri World Imagery">
              <TileLayer
                attribution="Tiles &copy; Esri"
                url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
              />
            </LayersControl.BaseLayer>

            <LayersControl.Overlay checked={cloudEnabled} name="Cloud Cover">
              <LayerGroup>
                {cloudTileUrl ? (
                  <TileLayer
                    attribution="Cloud data &copy; OpenWeatherMap"
                    opacity={0.85}
                    zIndex={500}
                    pane="overlayPane"
                    url={cloudTileUrl}
                    eventHandlers={{
                      tileload: handleCloudTileLoad,
                      tileerror: handleCloudTileError,
                    }}
                  />
                ) : null}
              </LayerGroup>
            </LayersControl.Overlay>

            <LayersControl.Overlay checked name="Rainfall Intensity">
              <LayerGroup>
                {rainfallCenters.map((center, index) => (
                  <Circle
                    key={`${center[0]}-${center[1]}-${index}`}
                    center={center}
                    radius={rainfallRadius}
                    pathOptions={{
                      color: rainfallCategory.color,
                      weight: 2,
                      opacity: 0.8,
                      fillColor: rainfallCategory.color,
                      fillOpacity: rainfallCategory.fillOpacity,
                    }}
                  >
                    <Popup>
                      <div className="text-sm">
                        <p className="font-semibold">{rainfallCategory.label}</p>
                        <p>{rainfallMmHr.toFixed(1)} mm/hr</p>
                      </div>
                    </Popup>
                  </Circle>
                ))}
              </LayerGroup>
            </LayersControl.Overlay>

            <LayersControl.Overlay checked name="Generation Stations">
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

            <LayersControl.Overlay checked name="Load Centers">
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

            <LayersControl.Overlay checked name="Operations Center">
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
              <LayerGroup />
            </LayersControl.Overlay>
          </LayersControl>

          <div className="pointer-events-none absolute bottom-3 left-3 z-[500] space-y-2">
            <div className="rounded-lg border border-slate-700/80 bg-slate-950/85 px-3 py-2 text-[11px] text-slate-200 shadow-lg shadow-black/25 backdrop-blur">
              <p className="font-semibold text-cyan-200">Legend</p>
              <div className="mt-2 grid gap-1">
                <LegendItem color="#94a3b8" label="No Rain" />
                <LegendItem color="#7dd3fc" label="Light Rain" />
                <LegendItem color="#3b82f6" label="Moderate Rain" />
                <LegendItem color="#f59e0b" label="Heavy Rain" />
                <LegendItem color="#ef4444" label="Severe Rain" />
              </div>
            </div>

            {cloudNotice || (!hasOpenWeatherApiKey || quotaMessage) ? (
              <div className="rounded-lg border border-amber-500/30 bg-amber-500/15 px-3 py-2 text-[11px] font-semibold text-amber-50 shadow-lg shadow-black/25 backdrop-blur">
                {cloudNotice ??
                  (quotaMessage
                    ? "OpenWeather daily limit reached. Cloud overlay disabled."
                    : "Cloud overlay unavailable: missing OpenWeatherMap API key")}
              </div>
            ) : null}

            {hurricaneEnabled ? (
              <div className="rounded-lg border border-slate-700/80 bg-slate-950/85 px-3 py-2 text-[11px] text-slate-200 shadow-lg shadow-black/25 backdrop-blur">
                Reserved for future hurricane tracking integration.
              </div>
            ) : null}
          </div>
        </MapContainer>
      </div>
    </div>
  );
}

function LegendItem({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />
      <span>{label}</span>
    </div>
  );
}

function MapOverlaySync({
  hasOpenWeatherApiKey,
  quotaReached,
  onCloudChange,
  onCloudNotice,
  onHurricaneChange,
}: {
  hasOpenWeatherApiKey: boolean;
  quotaReached: boolean;
  onCloudChange: (enabled: boolean) => void;
  onCloudNotice: (message: string | null) => void;
  onHurricaneChange: (enabled: boolean) => void;
}) {
  useMapEvents({
    overlayadd(event) {
      if (event.name === "Cloud Cover") {
        if (!hasOpenWeatherApiKey) {
          onCloudNotice("Cloud overlay unavailable: missing OpenWeatherMap API key");
          onCloudChange(false);
          return;
        }

        if (quotaReached) {
          onCloudNotice("OpenWeather daily limit reached. Cloud overlay disabled.");
          onCloudChange(false);
          return;
        }

        onCloudNotice(null);
        onCloudChange(true);
      }

      if (event.name === "Hurricane / Tropical Storm Tracking") {
        onHurricaneChange(true);
      }
    },
    overlayremove(event) {
      if (event.name === "Cloud Cover") {
        onCloudChange(false);
      }

      if (event.name === "Hurricane / Tropical Storm Tracking") {
        onHurricaneChange(false);
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
