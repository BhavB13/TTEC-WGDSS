import type {
  ForecastData,
  TemperatureAggregation,
  WeatherData,
} from "../types/dashboard";

export function getTemperatureMetricLabel(
  _value: Pick<WeatherData, "temperature_aggregation"> | Pick<
    ForecastData,
    "temperature_aggregation"
  >,
  compact = false,
): string {
  return compact ? "Temp" : "Temperature";
}

export function getTemperatureAggregationSummary(
  aggregate?: TemperatureAggregation | null,
): string | null {
  if (!aggregate) {
    return null;
  }
  if (aggregate.sample_count > 0) {
    if (aggregate.label === "Trinidad and Tobago weighted weather") {
      return `${aggregate.sample_count}/${aggregate.expected_sample_count} T&T weather points`;
    }
    return `${aggregate.sample_count}/${aggregate.expected_sample_count} Trinidad points · ${aggregate.minimum_c.toFixed(
      1,
    )}–${aggregate.maximum_c.toFixed(1)}°C`;
  }
  return aggregate.source_name;
}
