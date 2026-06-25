const STORAGE_KEY = "wgdss_openweather_quota_v1";

export const DAILY_TILE_LIMIT = 500;

type StoredQuota = {
  dateKey: string;
  count: number;
};

export type OpenWeatherQuotaState = {
  dateKey: string;
  count: number;
  remaining: number;
  limitReached: boolean;
};

function getLocalDateKey(date = new Date()): string {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function isBrowser(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

function readStoredQuota(now = new Date()): StoredQuota {
  const dateKey = getLocalDateKey(now);

  if (!isBrowser()) {
    return { dateKey, count: 0 };
  }

  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    writeStoredQuota({ dateKey, count: 0 });
    return { dateKey, count: 0 };
  }

  try {
    const parsed = JSON.parse(raw) as Partial<StoredQuota>;
    if (parsed.dateKey !== dateKey || typeof parsed.count !== "number" || Number.isNaN(parsed.count)) {
      writeStoredQuota({ dateKey, count: 0 });
      return { dateKey, count: 0 };
    }

    return {
      dateKey,
      count: Math.max(0, Math.floor(parsed.count)),
    };
  } catch {
    writeStoredQuota({ dateKey, count: 0 });
    return { dateKey, count: 0 };
  }
}

function writeStoredQuota(state: StoredQuota): void {
  if (!isBrowser()) {
    return;
  }

  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

export function getOpenWeatherQuotaState(now = new Date()): OpenWeatherQuotaState {
  const stored = readStoredQuota(now);
  const remaining = Math.max(0, DAILY_TILE_LIMIT - stored.count);
  return {
    dateKey: stored.dateKey,
    count: stored.count,
    remaining,
    limitReached: stored.count >= DAILY_TILE_LIMIT,
  };
}

export function canUseOpenWeatherCloudLayer(hasApiKey: boolean, now = new Date()): boolean {
  if (!hasApiKey) {
    return false;
  }

  return !getOpenWeatherQuotaState(now).limitReached;
}

export function recordOpenWeatherTileRequest(now = new Date()): OpenWeatherQuotaState {
  const current = readStoredQuota(now);
  const nextCount = Math.min(DAILY_TILE_LIMIT, current.count + 1);
  const nextState: StoredQuota = {
    dateKey: current.dateKey,
    count: nextCount,
  };

  writeStoredQuota(nextState);
  return getOpenWeatherQuotaState(now);
}

export function getOpenWeatherQuotaMessage(state: OpenWeatherQuotaState): string | null {
  if (state.limitReached) {
    return "OpenWeather daily quota reached. Cloud overlay disabled until tomorrow.";
  }

  return null;
}
