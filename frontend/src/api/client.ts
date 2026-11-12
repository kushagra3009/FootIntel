import type {
  DomesticPerformanceResponse,
  HealthResponse,
  HistoricalTrendsResponse,
  MarketValueSummaryResponse,
  MarketValueTransfersResponse,
  OverviewResponse,
  PlayerComparisonResponse,
  PlayerDetailResponse,
  PlayerSearchResponse,
  PlayerTransferSpellsResponse,
  PlayerValueGainsResponse,
  StatisticalResultsResponse,
  UCLPairedResponse,
  UCLPerformanceResponse,
} from '../types/api';

const RAW_VITE_API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL as string | undefined
)?.trim();

const API_BASE_URL =
  RAW_VITE_API_BASE_URL !== undefined && RAW_VITE_API_BASE_URL !== ''
    ? RAW_VITE_API_BASE_URL.replace(/\/+$/, '')
    : import.meta.env.DEV
    ? 'http://127.0.0.1:8000'
    : '';

const MISSING_PROD_API_URL =
  import.meta.env.PROD && (RAW_VITE_API_BASE_URL === undefined || RAW_VITE_API_BASE_URL === '');

export class ApiClientError extends Error {
  status: number;
  constructor(message: string, status = 0) {
    super(message);
    this.name = 'ApiClientError';
    this.status = status;
  }
}

function buildQuery(params: Record<string, string | number | boolean | undefined | null>): string {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') {
      qs.set(k, String(v));
    }
  }
  const str = qs.toString();
  return str ? `?${str}` : '';
}

async function fetchJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  if (MISSING_PROD_API_URL) {
    throw new ApiClientError(
      'Production build is missing VITE_API_BASE_URL. Rebuild with VITE_API_BASE_URL set to the FastAPI origin (or "/" for a same-origin proxy).',
      0,
    );
  }
  const url = `${API_BASE_URL}${path}`;
  let resp: Response;
  try {
    resp = await fetch(url, { signal });
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') {
      throw err;
    }
    throw new ApiClientError(
      `Cannot connect to FootIntel API at ${API_BASE_URL}. Ensure the FastAPI server is running.`,
      0,
    );
  }

  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      const errBody = (await resp.json()) as { detail?: unknown };
      if (typeof errBody.detail === 'string') {
        detail = errBody.detail;
      } else if (errBody.detail !== undefined) {
        detail = JSON.stringify(errBody.detail);
      }
    } catch {
      // keep default status text
    }
    throw new ApiClientError(detail, resp.status);
  }

  return (await resp.json()) as T;
}

export const api = {
  baseUrl: API_BASE_URL,

  getHealth: (signal?: AbortSignal) => fetchJson<HealthResponse>('/health', signal),

  getOverview: (signal?: AbortSignal) => fetchJson<OverviewResponse>('/api/v1/overview', signal),

  getTrends: (
    params: {
      league_id?: string;
      start_season?: number;
      end_season?: number;
      limit?: number;
      offset?: number;
    } = {},
    signal?: AbortSignal,
  ) => fetchJson<HistoricalTrendsResponse>(`/api/v1/trends${buildQuery(params)}`, signal),

  getDomestic: (
    params: {
      league_id?: string;
      season?: number;
      start_season?: number;
      end_season?: number;
      club_id?: number;
      club_name?: string;
      positive_spend_only?: boolean;
      min_spend_m?: number;
      sort_by?: string;
      sort_order?: 'asc' | 'desc';
      limit?: number;
      offset?: number;
    } = {},
    signal?: AbortSignal,
  ) => fetchJson<DomesticPerformanceResponse>(`/api/v1/domestic${buildQuery(params)}`, signal),

  getUcl: (
    params: {
      season?: number;
      league_id?: string;
      is_top5?: boolean;
      ucl_stage?: string;
      club_id?: number;
      club_name?: string;
      positive_spend_only?: boolean;
      sort_by?: string;
      sort_order?: 'asc' | 'desc';
      limit?: number;
      offset?: number;
    } = {},
    signal?: AbortSignal,
  ) => fetchJson<UCLPerformanceResponse>(`/api/v1/ucl${buildQuery(params)}`, signal),

  getUclPaired: (
    params: {
      season?: number;
      league_name?: string;
      club_id?: number;
      club_name?: string;
      positive_spend_only?: boolean;
      limit?: number;
      offset?: number;
    } = {},
    signal?: AbortSignal,
  ) => fetchJson<UCLPairedResponse>(`/api/v1/ucl/paired${buildQuery(params)}`, signal),

  getMarketValueSummary: (
    params: {
      league_id?: string;
      club_name?: string;
      min_signings?: number;
      sort_by?: string;
      sort_order?: 'asc' | 'desc';
      limit?: number;
      offset?: number;
    } = {},
    signal?: AbortSignal,
  ) =>
    fetchJson<MarketValueSummaryResponse>(
      `/api/v1/market-value/summary${buildQuery(params)}`,
      signal,
    ),

  getMarketValueTransfers: (
    params: {
      season?: number;
      league_id?: string;
      is_top5?: boolean;
      player_name?: string;
      club_name?: string;
      min_fee?: number;
      sort_by?: string;
      sort_order?: 'asc' | 'desc';
      limit?: number;
      offset?: number;
    } = {},
    signal?: AbortSignal,
  ) =>
    fetchJson<MarketValueTransfersResponse>(
      `/api/v1/market-value/transfers${buildQuery(params)}`,
      signal,
    ),

  getPlayerValueGains: (
    params: {
      club_id?: number;
      club_name?: string;
      league_id?: string;
      season?: number;
      player_name?: string;
      sort_by?: string;
      sort_order?: 'asc' | 'desc';
      limit?: number;
      offset?: number;
    } = {},
    signal?: AbortSignal,
  ) =>
    fetchJson<PlayerValueGainsResponse>(
      `/api/v1/market-value/player-gains${buildQuery(params)}`,
      signal,
    ),

  getStatistics: (
    section: 'all' | '6A' | '6B' | '6C' | '6D' | '6E' | '6F' | '07' = 'all',
    signal?: AbortSignal,
  ) => fetchJson<StatisticalResultsResponse>(`/api/v1/statistics${buildQuery({ section })}`, signal),

  searchPlayers: (
    params: {
      q?: string;
      position?: string;
      nationality?: string;
      min_appearances?: number;
      sort_by?: 'market_value' | 'highest_market_value' | 'name' | 'last_season' | 'appearances';
      limit?: number;
      offset?: number;
    } = {},
    signal?: AbortSignal,
  ) => fetchJson<PlayerSearchResponse>(`/api/v1/players/search${buildQuery(params)}`, signal),

  getPlayerDetail: (playerId: number, signal?: AbortSignal) =>
    fetchJson<PlayerDetailResponse>(`/api/v1/players/${playerId}`, signal),

  comparePlayers: (
    params: {
      player_a_id: number;
      player_b_id: number;
      season_a?: number;
      season_b?: number;
    },
    signal?: AbortSignal,
  ) => fetchJson<PlayerComparisonResponse>(`/api/v1/players/compare${buildQuery(params)}`, signal),

  getPlayerTransferSpells: (playerId: number, signal?: AbortSignal) =>
    fetchJson<PlayerTransferSpellsResponse>(`/api/v1/players/${playerId}/transfer-spells`, signal),
};
