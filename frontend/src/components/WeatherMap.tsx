import { useEffect, useMemo, useState } from "react";
import {
  CircleMarker,
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
import type { ForecastData, GridStatus } from "../types/dashboard";

interface WeatherMapProps {
  gridStatus: GridStatus;
  rainfallMmHr: number;
  forecastItems?: ForecastData[];
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
const GIBS_GEO_COLOR_LAYER = "GOES-East_ABI_GeoColor";
const GIBS_GEO_COLOR_TILESET = "GoogleMapsCompatible_Level7";
const GIBS_PRECIP_LAYER = "IMERG_Precipitation_Rate_30min";
const GIBS_PRECIP_TILESET = "GoogleMapsCompatible_Level6";
const CLOUD_SYSTEMS_LAYER_NAME = "Cloud Systems";
const CLOUDS_LATEST = "default";
const RAIN_LATEST = "default";
const generationCoordinates: Record<string, [number, number]> = {
  "Point Lisas": [10.388, -61.5],
  Cove: [10.534, -61.459],
  Penal: [10.166, -61.44],
  "La Brea": [10.236, -61.63],
};

type RainfallSeed = {
  center: [number, number];
  spread: number;
  weight: number;
};

const RAINFALL_SEEDS: RainfallSeed[] = [
  { center: [10.52, -61.53], spread: 2.0, weight: 1.08 },
  { center: [10.40, -61.34], spread: 2.35, weight: 1.0 },
  { center: [10.56, -61.10], spread: 2.05, weight: 1.04 },
  { center: [10.22, -61.33], spread: 2.2, weight: 1.12 },
  { center: [10.74, -61.36], spread: 1.9, weight: 0.98 },
  { center: [11.17, -60.73], spread: 1.5, weight: 0.9 },
];

const RAINFALL_BOUNDS: [[number, number], [number, number]] = [
  [9.85, -62.05],
  [11.5, -60.45],
];

function buildGeoColorUrl(timeToken: string): string {
  return `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/${GIBS_GEO_COLOR_LAYER}/default/${timeToken}/${GIBS_GEO_COLOR_TILESET}/{z}/{y}/{x}.png`;
}

function buildPrecipitationUrl(timeToken: string): string {
  return `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/${GIBS_PRECIP_LAYER}/default/${timeToken}/${GIBS_PRECIP_TILESET}/{z}/{y}/{x}.png`;
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

function getRainfallCategory(rainfallMmHr: number): {
  label: string;
  color: string;
  fillOpacity: number;
} {
  if (rainfallMmHr <= 0) {
    return { label: "No Rain", color: "#94a3b8", fillOpacity: 0.05 };
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

function buildRainfallField(rainfallMmHr: number, forecastItems: ForecastData[]) {
  const forecastSlice = forecastItems.slice(0, 6);
  const forecastRain =
    forecastSlice.length > 0
      ? forecastSlice.reduce((sum, item) => sum + item.rainfall_mm_hr, 0) / forecastSlice.length
      : rainfallMmHr;
  const forecastHumidity =
    forecastSlice.length > 0
      ? forecastSlice.reduce((sum, item) => sum + item.humidity_percent, 0) / forecastSlice.length
      : 0;
  const forecastProbability =
    forecastSlice.length > 0
      ? forecastSlice.reduce((sum, item) => sum + item.precipitation_probability_percent, 0) /
        forecastSlice.length
      : 0;

  const baseSignal = Math.max(rainfallMmHr, forecastRain * 0.9, forecastProbability / 16);

  if (baseSignal <= 0) {
    return { label: "No Rain", url: null as string | null };
  }

  const canvas = document.createElement("canvas");
  canvas.width = 768;
  canvas.height = 768;
  const context = canvas.getContext("2d");

  if (!context) {
    return { label: getRainfallCategory(baseSignal).label, url: null as string | null };
  }

  const image = context.createImageData(canvas.width, canvas.height);
  const latitudeSpan = RAINFALL_BOUNDS[1][0] - RAINFALL_BOUNDS[0][0];
  const longitudeSpan = RAINFALL_BOUNDS[1][1] - RAINFALL_BOUNDS[0][1];
  const humidityBoost = Math.max(0.65, Math.min(1.2, forecastHumidity / 100));
  const fieldStrength = Math.max(0.12, Math.min(1.0, baseSignal / 14));
  const drift = 0.02 + fieldStrength * 0.04;
  const motionPhase = ((Math.floor(Date.now() / 120000) % 8) - 4) / 4;

  for (let y = 0; y < canvas.height; y += 1) {
    for (let x = 0; x < canvas.width; x += 1) {
      const lat =
        RAINFALL_BOUNDS[1][0] - (y / (canvas.height - 1)) * latitudeSpan;
      const lon =
        RAINFALL_BOUNDS[0][1] + (x / (canvas.width - 1)) * longitudeSpan;

      let intensity = 0;
      for (const [index, seed] of RAINFALL_SEEDS.entries()) {
        const driftX = motionPhase * drift * (index % 2 === 0 ? 1 : -1);
        const driftY = motionPhase * drift * (index % 3 === 0 ? -1 : 1);
        const deltaLat = (lat - (seed.center[0] + driftY)) / seed.spread;
        const deltaLon = (lon - (seed.center[1] + driftX)) / (seed.spread * 1.2);
        const gaussian = Math.exp(-(deltaLat * deltaLat + deltaLon * deltaLon));
        intensity += gaussian * seed.weight;
      }

      intensity = Math.max(0, Math.min(1, intensity * fieldStrength * humidityBoost));

      const color = interpolateRainfallColor(intensity);
      const pixelIndex = (y * canvas.width + x) * 4;
      image.data[pixelIndex] = color[0];
      image.data[pixelIndex + 1] = color[1];
      image.data[pixelIndex + 2] = color[2];
      image.data[pixelIndex + 3] = color[3];
    }
  }

  context.putImageData(image, 0, 0);

  return {
    label: getRainfallCategory(baseSignal).label,
    url: canvas.toDataURL("image/png"),
  };
}

function interpolateRainfallColor(intensity: number): [number, number, number, number] {
  const stops = [
    { stop: 0, color: [148, 163, 184], alpha: 0 },
    { stop: 0.14, color: [125, 211, 252], alpha: 28 },
    { stop: 0.42, color: [59, 130, 246], alpha: 62 },
    { stop: 0.72, color: [245, 158, 11], alpha: 92 },
    { stop: 1, color: [239, 68, 68], alpha: 124 },
  ] as const;

  const clamped = Math.max(0, Math.min(1, intensity));
  let lower = stops[0];
  let upper = stops[stops.length - 1];

  for (let index = 0; index < stops.length - 1; index += 1) {
    if (clamped >= stops[index].stop && clamped <= stops[index + 1].stop) {
      lower = stops[index];
      upper = stops[index + 1];
      break;
    }
  }

  const span = upper.stop - lower.stop || 1;
  const mix = (clamped - lower.stop) / span;

  const red = Math.round(lower.color[0] + (upper.color[0] - lower.color[0]) * mix);
  const green = Math.round(lower.color[1] + (upper.color[1] - lower.color[1]) * mix);
  const blue = Math.round(lower.color[2] + (upper.color[2] - lower.color[2]) * mix);
  const alpha = Math.round(lower.alpha + (upper.alpha - lower.alpha) * mix);

  return [red, green, blue, alpha];
}

export default function WeatherMap({
  gridStatus,
  rainfallMmHr,
  forecastItems = [],
  className = "",
}: WeatherMapProps) {
  const [cloudSystemsEnabled, setCloudSystemsEnabled] = useState(true);
  const [hurricaneEnabled, setHurricaneEnabled] = useState(false);

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

  const cloudSystemsTileUrl = useMemo(
    () => buildGeoColorUrl(CLOUDS_LATEST),
    [],
  );
  const rainfallTileUrl = useMemo(
    () => buildPrecipitationUrl(RAIN_LATEST),
    [],
  );

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
            onCloudSystemsChange={setCloudSystemsEnabled}
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

            <LayersControl.Overlay checked={cloudSystemsEnabled} name={CLOUD_SYSTEMS_LAYER_NAME}>
              <LayerGroup>
                {cloudSystemsTileUrl ? (
                  <TileLayer
                    attribution="Cloud imagery &copy; NASA GIBS / NOAA"
                    opacity={0.78}
                    maxNativeZoom={7}
                    zIndex={500}
                    pane="overlayPane"
                    url={cloudSystemsTileUrl}
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
                    zIndex={490}
                    pane="overlayPane"
                    url={rainfallTileUrl}
                  />
                ) : null}
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
              <p className="mt-1 text-[11px] text-slate-300">
                Cloud systems and rainfall imagery are live NASA GIBS layers.
              </p>
              <div className="mt-2 grid gap-1">
                <LegendItem color="#93c5fd" label="Cloud Systems" />
                <LegendItem color="#60a5fa" label="Rainfall Coverage" />
              </div>
            </div>

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
  onCloudSystemsChange,
  onHurricaneChange,
}: {
  onCloudSystemsChange: (enabled: boolean) => void;
  onHurricaneChange: (enabled: boolean) => void;
}) {
  useMapEvents({
    overlayadd(event) {
      if (event.name === CLOUD_SYSTEMS_LAYER_NAME) {
        onCloudSystemsChange(true);
      }

      if (event.name === "Hurricane / Tropical Storm Tracking") {
        onHurricaneChange(true);
      }
    },
    overlayremove(event) {
      if (event.name === CLOUD_SYSTEMS_LAYER_NAME) {
        onCloudSystemsChange(false);
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
