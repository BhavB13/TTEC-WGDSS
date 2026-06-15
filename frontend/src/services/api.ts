import {
  WeatherData,
  ForecastData,
  GridStatus,
  Recommendation,
} from "../types/dashboard";

export async function getCurrentWeather(): Promise<WeatherData> {
  throw new Error("Not implemented");
}

export async function getForecast(): Promise<ForecastData[]> {
  throw new Error("Not implemented");
}

export async function getGridStatus(): Promise<GridStatus> {
  throw new Error("Not implemented");
}

export async function getRecommendation(): Promise<Recommendation> {
  throw new Error("Not implemented");
}