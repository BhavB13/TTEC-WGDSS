import { useMemo } from "react";
import { CircleMarker, LayerGroup, LayersControl, MapContainer, Popup, TileLayer } from "react-leaflet";
import "leaflet/dist/leaflet.css";

import type { GridStatus } from "../types/dashboard";

interface WeatherMapProps {
  gridStatus: GridStatus;
  className?: string;
}

type MapPoint = {
  lat: number;
  lon: number;
  label: string;
  value: string;
  status: string;
};

const TRINIDAD_CENTER: [number, number] = [10.6918, -61.2225];

const generationCoordinates: Record<string, [number, number]> = {
  "Point Lisas": [10.388, -61.5],
  Cove: [10.534, -61.459],
  Penal: [10.166, -61.44],
  "La Brea": [10.236, -61.63],
};

export default function WeatherMap({
  gridStatus,
  className = "",
}: WeatherMapProps) {
  const points = useMemo<MapPoint[]>(
    () =>
      gridStatus.generation_units.map((unit) => {
        const [lat, lon] = generationCoordinates[unit.station_name] ?? TRINIDAD_CENTER;
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

  return (
    <div className={`rounded-lg border border-slate-800 bg-slate-900/80 p-4 ${className}`}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-300">
            Weather Map
          </p>
          <h2 className="mt-1 text-lg font-semibold text-white">
            Trinidad Operations View
          </h2>
        </div>
        <span className="rounded-full border border-slate-700 px-3 py-1 text-xs font-medium text-slate-300">
          Leaflet
        </span>
      </div>

      <div className="h-[30rem] overflow-hidden rounded-md border border-slate-800">
        <MapContainer
          center={TRINIDAD_CENTER}
          zoom={9}
          scrollWheelZoom={false}
          className="h-full w-full"
        >
          <LayersControl position="topright">
            <LayersControl.BaseLayer checked name="OpenStreetMap">
              <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
            </LayersControl.BaseLayer>

            <LayersControl.BaseLayer name="Esri World Imagery">
              <TileLayer
                attribution="Tiles &copy; Esri"
                url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
              />
            </LayersControl.BaseLayer>

            <LayersControl.Overlay checked name="Generation Units">
              <LayerGroup>
                {points.map((point) => (
                  <CircleMarker
                    key={point.label}
                    center={[point.lat, point.lon]}
                    radius={8}
                    pathOptions={{
                      color: point.status === "ONLINE" ? "#22c55e" : "#f59e0b",
                      fillColor: point.status === "ONLINE" ? "#22c55e" : "#f59e0b",
                      fillOpacity: 0.7,
                    }}
                  >
                    <Popup>
                      <div className="text-sm">
                        <p className="font-semibold">{point.label}</p>
                        <p>{point.value}</p>
                        <p>Status: {point.status}</p>
                      </div>
                    </Popup>
                  </CircleMarker>
                ))}
              </LayerGroup>
            </LayersControl.Overlay>

            <LayersControl.Overlay name="Operations Center">
              <CircleMarker
                center={TRINIDAD_CENTER}
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
          </LayersControl>
        </MapContainer>
      </div>

      <div className="mt-3 text-xs text-slate-400">
        Ready for future weather overlays and additional grid layers.
      </div>
    </div>
  );
}
