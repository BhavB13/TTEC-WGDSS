# External Services and Cost Controls

## Active zero-cost services

| Service | Purpose | Authentication | Cost and safeguards |
| --- | --- | --- | --- |
| [Open-Meteo Free API](https://open-meteo.com/en/terms) | Current weather, Best Match forecast, NOAA GFS model stream | None | No billing path. Non-commercial hosted use is limited to 10,000 calls/day. WGDSS caches responses for five minutes and stops at 9,000 calls/day. |
| [MET Norway Locationforecast](https://docs.api.met.no/doc/TermsOfService.html) | Independent hourly forecast comparison | Identifying User-Agent | No API key or payment account. Responses are cached until the provider's `Expires` time and refreshed conditionally. Data is attributed under CC BY 4.0. |
| [NASA GIBS](https://www.earthdata.nasa.gov/engage/open-data-services-software/data-use-policy) | Blue Marble basemap, GOES-East cloud systems, GPM IMERG precipitation | None | NASA Earthdata is free and open. No payment account or metered key is used. |
| [OpenStreetMap standard tiles](https://operations.osmfoundation.org/policies/tiles/) | Optional street basemap | None | No payment account. WGDSS uses the required URL and attribution and does not prefetch or download tiles for offline use. Availability is best-effort. |

The browser dashboard makes no OpenWeatherMap or Esri requests. Their old
configuration and runtime paths were removed to eliminate accidental metered
usage.

### Optional WeatherAPI fallback

WeatherAPI is disabled by default. Its published Free plan is $0, allows
commercial use, includes 100,000 calls/month, and stops serving requests when
the quota is reached. It does not automatically charge overages. WGDSS caches
responses and applies its own 90,000-call monthly ceiling. To use only a free-plan key:

```text
WEATHER_API_KEY=your_free_plan_key
ENABLE_WEATHERAPI_FALLBACK=true
```

Leave both settings at their defaults for a no-account deployment. If enabled,
the UI credits `WeatherAPI` by provider name as required by its free terms.

## Licensing boundary

Open-Meteo's hosted Free API is explicitly limited to non-commercial use.
Therefore the current no-cost ensemble is suitable for development, evaluation,
education, and demonstrations. Before using the hosted endpoint as part of
production utility operations, T&TEC should obtain a licensing determination.
The underlying data is CC BY 4.0, but the hosted service terms are separate.

For a production deployment that must remain free, the practical alternatives
are:

1. Use MET Norway plus a WeatherAPI Free commercial key within its published
   quota.
2. Ingest NOAA GFS open data directly and perform the GRIB processing in WGDSS.
   The data is free, but operating the storage and processing infrastructure is
   not cost-free.

## Optional paid accuracy upgrades

These are not integrated and cannot generate charges:

| Provider | Potential improvement |
| --- | --- |
| [Tomorrow.io Enterprise](https://www.tomorrow.io/weather-api/) | Proprietary satellite assimilation, minutely resolution, operational alerts, weather maps, and SLA options. |
| [Meteomatics Weather API](https://www.meteomatics.com/en/pricing/) | Multi-model mixing, observations, radar/satellite/lightning sources, areal queries, and enterprise support. |
| [Vaisala Xweather](https://www.vaisala.com/en/digital-services) | Hyperlocal observations, global lightning detection, tropical storm products, weather maps, and utility-focused intelligence. |
| [WeatherAPI paid tiers](https://www.weatherapi.com/pricing.aspx) | Higher quota, longer forecast horizons, 15-minute data, and stronger uptime commitments while preserving the existing provider adapter. |

No paid provider should be enabled without an explicit procurement and
configuration decision.
