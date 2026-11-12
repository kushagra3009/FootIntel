import { useCallback, useEffect, useMemo, useState } from 'react';
import { RotateCcw } from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { api } from '../api/client';
import type {
  DomesticClubSeasonRow,
  FeeVsMVTransferRow,
  HistoricalTrendsResponse,
} from '../types/api';
import {
  formatEurMillions,
  formatInteger,
  LEAGUE_COLOR_MAP,
  TOP5_LEAGUE_OPTIONS,
} from '../utils/formatters';
import { ChartCard } from '../components/common/ChartCard';
import { KpiCard } from '../components/common/KpiCard';
import { EmptyState, ErrorState, LoadingState, WarningBanner } from '../components/common/StatePanel';

const SEASONS = Array.from({ length: 14 }, (_, i) => 2012 + i);

interface TransferMarketData {
  trends: HistoricalTrendsResponse;
  clubRows: DomesticClubSeasonRow[];
  transferSample: FeeVsMVTransferRow[];
  transferSampleTotal: number;
}

export function TransferMarketSection() {
  const [leagueId, setLeagueId] = useState<string>('');
  const [startSeason, setStartSeason] = useState<number>(2012);
  const [endSeason, setEndSeason] = useState<number>(2025);
  const [data, setData] = useState<TransferMarketData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      const trends = await api.getTrends(
        {
          league_id: leagueId || undefined,
          start_season: startSeason,
          end_season: endSeason,
          limit: 200,
        },
        signal,
      );

      // Fetch all matching club-season rows (max 1,366 -> at most 3 pages of 500)
      const firstDom = await api.getDomestic(
        {
          league_id: leagueId || undefined,
          start_season: startSeason,
          end_season: endSeason,
          positive_spend_only: true,
          limit: 500,
          offset: 0,
        },
        signal,
      );
      const extraPages: Promise<typeof firstDom>[] = [];
      for (let off = 500; off < firstDom.pagination.total; off += 500) {
        extraPages.push(
          api.getDomestic(
            {
              league_id: leagueId || undefined,
              start_season: startSeason,
              end_season: endSeason,
              positive_spend_only: true,
              limit: 500,
              offset: off,
            },
            signal,
          ),
        );
      }
      const restDom = await Promise.all(extraPages);
      const clubRows = [firstDom, ...restDom].flatMap((d) => d.observations);

      // Fetch Top-5 transfer sample (filtered by exact season if single season, else top 500 across window)
      const transferPage1 = await api.getMarketValueTransfers(
        {
          season: startSeason === endSeason ? startSeason : undefined,
          league_id: leagueId || undefined,
          is_top5: true,
          sort_by: 'transfer_fee',
          sort_order: 'desc',
          limit: 250,
          offset: 0,
        },
        signal,
      );
      const transferPage2 =
        transferPage1.pagination.total > 250
          ? await api.getMarketValueTransfers(
              {
                season: startSeason === endSeason ? startSeason : undefined,
                league_id: leagueId || undefined,
                is_top5: true,
                sort_by: 'transfer_fee',
                sort_order: 'desc',
                limit: 250,
                offset: 250,
              },
              signal,
            )
          : null;

      const transferSample = [
        ...transferPage1.transfers,
        ...(transferPage2 ? transferPage2.transfers : []),
      ].filter((t) => t.game_season >= startSeason && t.game_season <= endSeason);

      setData({
        trends,
        clubRows,
        transferSample,
        transferSampleTotal: transferPage1.pagination.total,
      });
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        setError((err as Error).message);
      }
    } finally {
      setLoading(false);
    }
  }, [leagueId, startSeason, endSeason]);

  useEffect(() => {
    const ctrl = new AbortController();
    void load(ctrl.signal);
    return () => ctrl.abort();
  }, [load]);

  const seasonLeaguePivot = useMemo(() => {
    if (!data) return [];
    const bySeason = new Map<string, Record<string, string | number>>();
    for (const row of data.trends.by_league) {
      const existing = bySeason.get(row.transfer_season) ?? {
        season: row.transfer_season,
        gameSeason: row.game_season,
      };
      existing[row.league_name] = Number(row.total_spending_m.toFixed(1));
      bySeason.set(row.transfer_season, existing);
    }
    return Array.from(bySeason.values()).sort(
      (a, b) => Number(a.gameSeason) - Number(b.gameSeason),
    );
  }, [data]);

  const topSpendingClubs = useMemo(() => {
    if (!data) return [];
    const map = new Map<
      number,
      { clubId: number; name: string; league: string; grossM: number; netM: number; seasons: number }
    >();
    for (const row of data.clubRows) {
      const cur = map.get(row.club_id) ?? {
        clubId: row.club_id,
        name: row.name,
        league: row.league_name,
        grossM: 0,
        netM: 0,
        seasons: 0,
      };
      cur.grossM += row.gross_spend_m;
      cur.netM += row.net_spend_m;
      cur.seasons += 1;
      map.set(row.club_id, cur);
    }
    return Array.from(map.values())
      .sort((a, b) => b.grossM - a.grossM)
      .slice(0, 12)
      .map((c) => ({
        ...c,
        grossM: Number(c.grossM.toFixed(1)),
        netM: Number(c.netM.toFixed(1)),
      }));
  }, [data]);

  const feeDistribution = useMemo(() => {
    if (!data) return [];
    const buckets = [
      { label: '< €1M', min: 0, max: 1e6, count: 0 },
      { label: '€1M–5M', min: 1e6, max: 5e6, count: 0 },
      { label: '€5M–15M', min: 5e6, max: 15e6, count: 0 },
      { label: '€15M–30M', min: 15e6, max: 30e6, count: 0 },
      { label: '€30M–60M', min: 30e6, max: 60e6, count: 0 },
      { label: '€60M+', min: 60e6, max: Infinity, count: 0 },
    ];
    for (const t of data.transferSample) {
      const b = buckets.find((x) => t.transfer_fee >= x.min && t.transfer_fee < x.max);
      if (b) b.count += 1;
    }
    return buckets;
  }, [data]);

  const filteredSpendM = useMemo(() => {
    if (!data) return 0;
    return data.trends.by_league.reduce((acc, r) => acc + r.total_spending_m, 0);
  }, [data]);

  const filteredPaidCount = useMemo(() => {
    if (!data) return 0;
    return data.trends.by_league.reduce((acc, r) => acc + r.paid_transfers, 0);
  }, [data]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div className="filter-bar" role="region" aria-label="Transfer market filters">
        <div className="filter-field">
          <label className="filter-label" htmlFor="tm-league">League</label>
          <select
            id="tm-league"
            className="control-select"
            value={leagueId}
            onChange={(e) => setLeagueId(e.target.value)}
          >
            <option value="">All Big 5 Leagues</option>
            {TOP5_LEAGUE_OPTIONS.map((l) => (
              <option key={l.id} value={l.id}>{l.name}</option>
            ))}
          </select>
        </div>

        <div className="filter-field">
          <label className="filter-label" htmlFor="tm-start">Start Season</label>
          <select
            id="tm-start"
            className="control-select"
            value={startSeason}
            onChange={(e) => {
              const v = Number(e.target.value);
              setStartSeason(v);
              if (v > endSeason) setEndSeason(v);
            }}
          >
            {SEASONS.map((y) => (
              <option key={y} value={y}>{y}/{String((y + 1) % 100).padStart(2, '0')}</option>
            ))}
          </select>
        </div>

        <div className="filter-field">
          <label className="filter-label" htmlFor="tm-end">End Season</label>
          <select
            id="tm-end"
            className="control-select"
            value={endSeason}
            onChange={(e) => {
              const v = Number(e.target.value);
              setEndSeason(v);
              if (v < startSeason) setStartSeason(v);
            }}
          >
            {SEASONS.map((y) => (
              <option key={y} value={y}>{y}/{String((y + 1) % 100).padStart(2, '0')}</option>
            ))}
          </select>
        </div>

        <div style={{ marginLeft: 'auto', alignSelf: 'flex-end' }}>
          <button
            type="button"
            className="btn"
            onClick={() => {
              setLeagueId('');
              setStartSeason(2012);
              setEndSeason(2025);
            }}
          >
            <RotateCcw size={14} /> Reset Filters
          </button>
        </div>
      </div>

      {loading && <LoadingState message="Loading transfer market trends..." />}
      {!loading && error && <ErrorState message={error} onRetry={() => void load()} />}
      {!loading && !error && data && (
        <>
          <WarningBanner tone="warning" title="Historical Data Coverage Warning">
            {data.trends.coverage_warning.summary} {data.trends.coverage_warning.implication}
          </WarningBanner>

          <div className="kpi-grid">
            <KpiCard
              label="Filtered Gross Spend"
              value={formatEurMillions(filteredSpendM)}
              sublabel={`${leagueId ? TOP5_LEAGUE_OPTIONS.find((l) => l.id === leagueId)?.name : 'All Top-5'} • ${startSeason}–${endSeason}`}
            />
            <KpiCard
              label="Paid Transfers (Filtered)"
              value={formatInteger(filteredPaidCount)}
              sublabel={`Across ${data.trends.by_league.length} league-seasons`}
              badge="transfer_fee > 0"
              badgeTone="sky"
            />
            <KpiCard
              label="Weighted Mean Fee"
              value={filteredPaidCount > 0 ? `€${(filteredSpendM / filteredPaidCount).toFixed(2)}M` : '—'}
              sublabel="Filtered gross spend ÷ paid deals"
            />
            <KpiCard
              label="Top-Spending Club (Window)"
              value={topSpendingClubs[0]?.name ?? '—'}
              sublabel={topSpendingClubs[0] ? formatEurMillions(topSpendingClubs[0].grossM) : 'No spend data'}
              badge={topSpendingClubs[0]?.league}
            />
          </div>

          <div className="chart-grid-2">
            <ChartCard
              title="Season-Wise Transfer Spending & Average Fee"
              subtitle="Aggregate Top-5 gross spend (€B) alongside weighted average fee (€M)"
              note="Shaded band indicates seasons where <85% of active Top-5 players appear in transfers."
            >
              <div style={{ width: '100%', height: 300 }}>
                <ResponsiveContainer>
                  <ComposedChart data={data.trends.aggregate} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
                    <CartesianGrid stroke="rgba(148,163,184,0.12)" strokeDasharray="3 3" />
                    <ReferenceArea x1="12/13" x2="21/22" fill="rgba(245,158,11,0.08)" />
                    <XAxis dataKey="transfer_season" stroke="#94a3b8" fontSize={12} />
                    <YAxis
                      yAxisId="spend"
                      stroke="#10b981"
                      fontSize={12}
                      tickFormatter={(v: number) => `€${(v / 1e9).toFixed(1)}B`}
                    />
                    <YAxis
                      yAxisId="avg"
                      orientation="right"
                      stroke="#f59e0b"
                      fontSize={12}
                      tickFormatter={(v: number) => `€${v.toFixed(0)}M`}
                    />
                    <Tooltip
                      content={({ active, payload, label }) => {
                        if (!active || !payload?.length) return null;
                        const r = payload[0].payload as (typeof data.trends.aggregate)[number];
                        return (
                          <div className="chart-tooltip">
                            <div className="chart-tooltip-title">Season {label}</div>
                            <div className="chart-tooltip-row">
                              <span>Total Spend:</span>
                              <span>€{(r.total_spending / 1e9).toFixed(2)}B</span>
                            </div>
                            <div className="chart-tooltip-row">
                              <span>Avg Paid Fee:</span>
                              <span>€{r.weighted_avg_fee_m.toFixed(2)}M</span>
                            </div>
                            <div className="chart-tooltip-row">
                              <span>Active Coverage:</span>
                              <span>{r.pct_active_players_covered.toFixed(1)}%</span>
                            </div>
                          </div>
                        );
                      }}
                    />
                    <Bar yAxisId="spend" dataKey="total_spending" fill="#10b981" radius={[4, 4, 0, 0]} />
                    <Line
                      yAxisId="avg"
                      type="monotone"
                      dataKey="weighted_avg_fee_m"
                      stroke="#f59e0b"
                      strokeWidth={2.5}
                      dot={{ r: 3 }}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </ChartCard>

            <ChartCard
              title="League-Wise Spending Comparison (€M)"
              subtitle="Annual gross transfer spending stacked across Europe's Big 5 leagues"
            >
              {seasonLeaguePivot.length === 0 ? (
                <EmptyState />
              ) : (
                <div style={{ width: '100%', height: 300 }}>
                  <ResponsiveContainer>
                    <BarChart data={seasonLeaguePivot} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
                      <CartesianGrid stroke="rgba(148,163,184,0.12)" strokeDasharray="3 3" />
                      <XAxis dataKey="season" stroke="#94a3b8" fontSize={12} />
                      <YAxis stroke="#94a3b8" fontSize={12} tickFormatter={(v: number) => `€${v}M`} />
                      <Tooltip
                        contentStyle={{
                          background: 'rgba(10,16,26,0.96)',
                          border: '1px solid rgba(148,163,184,0.25)',
                          borderRadius: 10,
                          fontSize: 12,
                        }}
                      />
                      {TOP5_LEAGUE_OPTIONS.filter((l) => !leagueId || l.id === leagueId).map((l) => (
                        <Bar key={l.id} dataKey={l.name} stackId="a" fill={LEAGUE_COLOR_MAP[l.name]} />
                      ))}
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </ChartCard>
          </div>

          <div className="chart-grid-2">
            <ChartCard
              title="Top Spending Clubs (Filtered Window)"
              subtitle="Cumulative gross vs net spending (€M) from season-aligned club records"
            >
              {topSpendingClubs.length === 0 ? (
                <EmptyState />
              ) : (
                <div style={{ width: '100%', height: 340 }}>
                  <ResponsiveContainer>
                    <BarChart
                      data={topSpendingClubs}
                      layout="vertical"
                      margin={{ top: 6, right: 20, left: 20, bottom: 4 }}
                    >
                      <CartesianGrid stroke="rgba(148,163,184,0.1)" strokeDasharray="3 3" />
                      <XAxis type="number" stroke="#94a3b8" fontSize={12} tickFormatter={(v: number) => `€${v}M`} />
                      <YAxis type="category" dataKey="name" width={132} stroke="#cbd5e1" fontSize={11.5} />
                      <Tooltip
                        content={({ active, payload }) => {
                          if (!active || !payload?.length) return null;
                          const c = payload[0].payload as (typeof topSpendingClubs)[number];
                          return (
                            <div className="chart-tooltip">
                              <div className="chart-tooltip-title">{c.name} ({c.league})</div>
                              <div className="chart-tooltip-row">
                                <span>Gross Spend:</span>
                                <span>{formatEurMillions(c.grossM)}</span>
                              </div>
                              <div className="chart-tooltip-row">
                                <span>Net Spend:</span>
                                <span>{formatEurMillions(c.netM, true)}</span>
                              </div>
                              <div className="chart-tooltip-row">
                                <span>Seasons:</span>
                                <span>{c.seasons}</span>
                              </div>
                            </div>
                          );
                        }}
                      />
                      <Bar dataKey="grossM" name="Gross Spend (€M)" fill="#10b981" radius={[0, 4, 4, 0]} />
                      <Bar dataKey="netM" name="Net Spend (€M)" fill="#38bdf8" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </ChartCard>

            <ChartCard
              title="Transfer Fee Bracket Distribution"
              subtitle={`Top ${data.transferSample.length} Top-5 paid transfers with arrival MV in window (matching pool: ${formatInteger(data.transferSampleTotal)})`}
              note="Derived dynamically from /api/v1/market-value/transfers sorted by transfer_fee descending."
            >
              {data.transferSample.length === 0 ? (
                <EmptyState />
              ) : (
                <div style={{ width: '100%', height: 340 }}>
                  <ResponsiveContainer>
                    <BarChart data={feeDistribution} margin={{ top: 10, right: 16, left: 0, bottom: 4 }}>
                      <CartesianGrid stroke="rgba(148,163,184,0.12)" strokeDasharray="3 3" />
                      <XAxis dataKey="label" stroke="#94a3b8" fontSize={12} />
                      <YAxis stroke="#94a3b8" fontSize={12} />
                      <Tooltip
                        contentStyle={{
                          background: 'rgba(10,16,26,0.96)',
                          border: '1px solid rgba(148,163,184,0.25)',
                          borderRadius: 10,
                          fontSize: 12,
                        }}
                      />
                      <Bar dataKey="count" name="Transfers" fill="#38bdf8" radius={[6, 6, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </ChartCard>
          </div>
        </>
      )}
    </div>
  );
}
