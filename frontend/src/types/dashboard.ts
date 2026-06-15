export interface WeatherSummary {
  temperature: number;
  windSpeed: number;
  cloudCover: number;
  rainProbability: number;
}

export interface GridStatus {
  currentDemand: number;
  availableGeneration: number;
  reserveMargin: number;
}

export interface Recommendation {
  recommendation: string;
  confidence: number;
  reason: string;
}

export interface ForecastRecord {
  hour: string;
  temperature: number;
  windSpeed: number;
  rainProbability: number;
}

export interface RecommendationHistoryRecord {
  time: string;
  recommendation: string;
  confidence: number;
}