import {
  WeatherSummary,
  GridStatus,
  Recommendation,
  ForecastRecord,
  RecommendationHistoryRecord,
} from "../types/dashboard";

export const weatherSummary: WeatherSummary = {
  temperature: 31,
  windSpeed: 12,
  cloudCover: 70,
  rainProbability: 45,
};

export const gridStatus: GridStatus = {
  currentDemand: 920,
  availableGeneration: 980,
  reserveMargin: 60,
};

export const recommendation: Recommendation = {
  recommendation: "Start Gas Turbine Unit 2",
  confidence: 0.82,
  reason: "Demand expected to increase over the next 2 hours.",
};

export const forecastData: ForecastRecord[] = [
  {
    hour: "12:00",
    temperature: 31,
    windSpeed: 12,
    rainProbability: 40,
  },
  {
    hour: "13:00",
    temperature: 32,
    windSpeed: 14,
    rainProbability: 35,
  },
  {
    hour: "14:00",
    temperature: 32,
    windSpeed: 15,
    rainProbability: 30,
  },
];

export const recommendationHistory: RecommendationHistoryRecord[] = [
  {
    time: "08:00",
    recommendation: "Start GT1",
    confidence: 0.78,
  },
  {
    time: "10:00",
    recommendation: "Maintain Current Generation",
    confidence: 0.65,
  },
];