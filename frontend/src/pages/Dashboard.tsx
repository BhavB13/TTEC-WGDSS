import Header from "../components/Header";
import WeatherCard from "../components/WeatherCard";
import GridStatusCard from "../components/GridStatusCard";
import RecommendationCard from "../components/RecommendationCard";
import ForecastTable from "../components/ForecastTable";
import WeatherMap from "../components/WeatherMap";

import {
  mockWeather,
  mockForecast,
  mockGridStatus,
  mockRecommendation,
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

      <ForecastTable forecast={mockForecast} />
    </div>
  );
}