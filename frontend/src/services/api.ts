import type {
  DashboardSnapshot,
  ForecastData,
  GridStatus,
  ProbabilityData,
  RecommendationData,
  WeatherData,
} from "../types/dashboard";

const API_BASE_URL = (
  (
    import.meta as ImportMeta & {
      env?: Record<string, string | undefined>;
    }
  ).env?.VITE_API_BASE_URL ?? ""
).replace(/\/$/, "");
const DASHBOARD_SNAPSHOT_PATH = "/api/dashboard/snapshot";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), 20_000);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.headers ?? {}),
      },
      signal: init?.signal ?? controller.signal,
    });
  } catch (cause) {
    if (cause instanceof Error && cause.name === "AbortError") {
      throw new Error("Dashboard request timed out after 20 seconds");
    }
    throw cause;
  } finally {
    window.clearTimeout(timeoutId);
  }

  if (!response.ok) {
    const message = await readErrorMessage(response);
    throw new Error(message);
  }

  return (await response.json()) as T;
}

async function readErrorMessage(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail || `Request failed with status ${response.status}`;
  } catch {
    return `Request failed with status ${response.status}`;
  }
}

export async function getDashboardSnapshot(options?: {
  forceRefresh?: boolean;
}): Promise<DashboardSnapshot> {
  const forceRefresh = options?.forceRefresh ?? true;
  const path = forceRefresh
    ? `${DASHBOARD_SNAPSHOT_PATH}?force_refresh=true`
    : DASHBOARD_SNAPSHOT_PATH;
  return requestJson<DashboardSnapshot>(path);
}

export async function getCurrentWeather(): Promise<WeatherData> {
  const snapshot = await getDashboardSnapshot();
  return snapshot.weather;
}

export async function getForecast(): Promise<ForecastData[]> {
  const snapshot = await getDashboardSnapshot();
  return snapshot.forecast.items;
}

export async function getGridStatus(): Promise<GridStatus> {
  const snapshot = await getDashboardSnapshot();
  return snapshot.grid;
}

export async function getRecommendation(): Promise<RecommendationData> {
  const snapshot = await getDashboardSnapshot();
  return snapshot.recommendation;
}

export async function getProbability(): Promise<ProbabilityData> {
  const snapshot = await getDashboardSnapshot();
  return snapshot.probability;
}
