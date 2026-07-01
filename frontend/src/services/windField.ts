export interface WindFieldSample {
  latitude: number;
  longitude: number;
  speedKmh: number;
  directionDegrees: number;
}

const OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast";
const CACHE_TTL_MS = 15 * 60 * 1000;
export const WIND_FIELD_EXTENT = {
  south: 8,
  west: -65,
  north: 14,
  east: -57,
} as const;
const LATITUDES = Array.from({ length: 7 }, (_, index) => 8 + index);
const LONGITUDES = Array.from({ length: 9 }, (_, index) => -65 + index);

let cachedSamples: WindFieldSample[] | null = null;
let cacheExpiresAt = 0;

interface OpenMeteoLocationResponse {
  latitude?: number;
  longitude?: number;
  current?: {
    wind_speed_10m?: number;
    wind_direction_10m?: number;
  };
}

export async function getCurrentWindField(
  signal?: AbortSignal,
): Promise<WindFieldSample[]> {
  if (cachedSamples && Date.now() < cacheExpiresAt) {
    return cachedSamples;
  }

  const coordinates = LATITUDES.flatMap((latitude) =>
    LONGITUDES.map((longitude) => ({ latitude, longitude })),
  );
  const url = new URL(OPEN_METEO_FORECAST_URL);
  url.searchParams.set(
    "latitude",
    coordinates.map(({ latitude }) => latitude).join(","),
  );
  url.searchParams.set(
    "longitude",
    coordinates.map(({ longitude }) => longitude).join(","),
  );
  url.searchParams.set(
    "current",
    "wind_speed_10m,wind_direction_10m",
  );
  url.searchParams.set("wind_speed_unit", "kmh");
  url.searchParams.set("timezone", "America/Port_of_Spain");

  const response = await fetch(url, { signal });
  if (!response.ok) {
    throw new Error(`Open-Meteo wind request failed with ${response.status}`);
  }

  const payload = (await response.json()) as
    | OpenMeteoLocationResponse
    | OpenMeteoLocationResponse[];
  const locations = Array.isArray(payload) ? payload : [payload];
  const samples = locations.flatMap((location) => {
    const latitude = location.latitude;
    const longitude = location.longitude;
    const speedKmh = location.current?.wind_speed_10m;
    const directionDegrees = location.current?.wind_direction_10m;

    if (
      latitude == null ||
      longitude == null ||
      speedKmh == null ||
      directionDegrees == null ||
      !Number.isFinite(latitude) ||
      !Number.isFinite(longitude) ||
      !Number.isFinite(speedKmh) ||
      !Number.isFinite(directionDegrees)
    ) {
      return [];
    }

    return [{ latitude, longitude, speedKmh, directionDegrees }];
  });

  if (samples.length === 0) {
    throw new Error("Open-Meteo returned no usable wind samples");
  }

  cachedSamples = samples;
  cacheExpiresAt = Date.now() + CACHE_TTL_MS;
  return samples;
}
