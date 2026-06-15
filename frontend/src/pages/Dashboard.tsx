import Header from "../components/Header";
import WeatherCard from "../components/WeatherCard";
import GridStatusCard from "../components/GridStatusCard";
import RecommendationCard from "../components/RecommendationCard";
import ForecastTable from "../components/ForecastTable";
import RecommendationHistoryTable from "../components/RecommendationHistoryTable";
import WeatherMap from "../components/WeatherMap";

import {
  mockWeather,
  mockForecast,
  mockGridStatus,
  mockRecommendation,
  mockRecommendationHistory,
} from "../data/mockData";

export default function Dashboard() {
  return (
    <div>
      <Header />

      <WeatherCard weather={mockWeather} />

      <GridStatusCard
        gridStatus={mockGridStatus}
      />

      <RecommendationCard
        recommendation={mockRecommendation}
      />

      <WeatherMap />

      <ForecastTable
        forecast={mockForecast}
      />

      <RecommendationHistoryTable
        history={mockRecommendationHistory}
      />
    </div>
  );
}