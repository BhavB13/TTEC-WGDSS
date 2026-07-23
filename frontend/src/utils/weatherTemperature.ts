import type {
  ForecastData,
  TemperatureAggregation,
  WeatherData,
} from "../types/dashboard";

type TemperatureCarrier = Pick<WeatherData, "temperature_aggregation"> | Pick<
  ForecastData,
  "temperature_aggregation"
>;

export function getTemperatureMetricLabel(
  value: TemperatureCarrier,
  compact = false,
): string {
  const aggregate = value.temperature_aggregation;
  if (!aggregate) {
    return compact ? "Temp" : "Temperature";
  }
  if (aggregate.method === "demand_exposure_weighted_mean") {
    return compact ? "Weighted Temp" : "Weighted Temperature";
  }
  if (aggregate.method === "scada_exported_trinidad_average") {
    return compact ? "SCADA Avg Temp" : "SCADA Average Temperature";
  }
  return compact ? "Avg Temp" : "Average Temperature";
}

export function getTemperatureAggregationSummary(
  aggregate?: TemperatureAggregation | null,
): string | null {
  if (!aggregate) {
    return null;
  }
  if (aggregate.sample_count > 0) {
    if (aggregate.label === "Trinidad and Tobago weighted weather") {
      return `${aggregate.sample_count}/${aggregate.expected_sample_count} weighted T&T weather points`;
    }
    return `${aggregate.sample_count}/${aggregate.expected_sample_count} Trinidad points · ${aggregate.minimum_c.toFixed(
      1,
    )}–${aggregate.maximum_c.toFixed(1)}°C`;
  }
  return aggregate.source_name;
}
