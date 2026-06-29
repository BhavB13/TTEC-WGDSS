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
interface WeatherMapProps {
  className?: string;
}

const DEFAULT_CENTER: [number, number] = [10.6918, -61.2225];
const DEFAULT_ZOOM = 8;
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

export default function WeatherMap({
  className = "",
}: WeatherMapProps) {
  const [cloudSystemsEnabled, setCloudSystemsEnabled] = useState(true);
  const [hurricaneEnabled, setHurricaneEnabled] = useState(false);

  const cloudSystemsTileUrl = useMemo(
    () => buildGeoColorUrl(CLOUDS_LATEST),
    [],
  );
  const rainfallTileUrl = useMemo(
    () => buildPrecipitationUrl(RAIN_LATEST),
    [],
  );
  const satelliteBaseUrl = useMemo(() => buildSatelliteBaseUrl(), []);

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
          minZoom={6}
          maxZoom={11}
          scrollWheelZoom={false}
          fadeAnimation={false}
          className="h-full w-full"
        >
          <MapResizeSync />
          <MapViewSync />
          <MapTileStabilizer />
          <MapOverlaySync
            onCloudSystemsChange={setCloudSystemsEnabled}
            onHurricaneChange={setHurricaneEnabled}
          />

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

            <LayersControl.Overlay checked={cloudSystemsEnabled} name={CLOUD_SYSTEMS_LAYER_NAME}>
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

        </MapContainer>
      </div>
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
