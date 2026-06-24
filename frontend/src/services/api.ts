import type {
  DashboardSnapshot,
  ForecastData,
  GridStatus,
  ProbabilityData,
  RecommendationData,
  WeatherData,
} from "../types/dashboard";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "";
const DASHBOARD_SNAPSHOT_PATH = "/api/dashboard/snapshot";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      Accept: "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

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

export async function getDashboardSnapshot(): Promise<DashboardSnapshot> {
  return requestJson<DashboardSnapshot>(DASHBOARD_SNAPSHOT_PATH);
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
