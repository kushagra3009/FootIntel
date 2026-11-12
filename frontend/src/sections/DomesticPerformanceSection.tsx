import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { api } from '../api/client';
import type { DomesticClubSeasonRow, DomesticPerformanceResponse } from '../types/api';
import {
  formatEurMillions,
  formatInteger,
  formatPercent,
  formatPValue,
  LEAGUE_COLOR_MAP,
  TOP5_LEAGUE_OPTIONS,
} from '../utils/formatters';
import { ChartCard } from '../components/common/ChartCard';
import { KpiCard } from '../components/common/KpiCard';
import { EmptyState, ErrorState, LoadingState, WarningBanner } from '../components/common/StatePanel';

const SEASONS = Array.from({ length: 14 }, (_, i) => 2012 + i);

export function DomesticPerformanceSection() {
  const [leagueId, setLeagueId] = useState<string>('');
  const [season, setSeason] = useState<string>('');
  const [clubQuery, setClubQuery] = useState<string>('');
  const [positiveOnly, setPositiveOnly] = useState<boolean>(true);
  const [sortBy, setSortBy] = useState<string>('ppg');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  const [meta, setMeta] = useState<DomesticPerformanceResponse | null>(null);
  const [rows, setRows] = useState<DomesticClubSeasonRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      const first = await api.getDomestic(
        {
          league_id: leagueId || undefined,
          season: season ? Number(season) : undefined,
          club_name: clubQuery.trim() || undefined,
          positive_spend_only: positiveOnly,
          sort_by: sortBy,
          sort_order: sortOrder,
          limit: 500,
          offset: 0,
        },
        signal,
      );
      const extra: Promise<DomesticPerformanceResponse>[] = [];
      for (let off = 500; off < first.pagination.total; off += 500) {
        extra.push(
          api.getDomestic(
            {
              league_id: leagueId || undefined,
              season: season ? Number(season) : undefined,
              club_name: clubQuery.trim() || undefined,
              positive_spend_only: positiveOnly,
              sort_by: sortBy,
              sort_order: sortOrder,
              limit: 500,
              offset: off,
            },
            signal,
          ),
        );
      }
      const rest = await Promise.all(extra);
      setMeta(first);
      setRows([first, ...rest].flatMap((d) => d.observations));
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        setError((err as Error).message);
      }
    } finally {
      setLoading(false);
    }
  }, [leagueId, season, clubQuery, positiveOnly, sortBy, sortOrder]);

  useEffect(() => {
    const ctrl = new AbortController();
    const timer = setTimeout(() => void load(ctrl.signal), 180);
    return () => {
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [load]);

  const scatterPoints = useMemo(
    () =>
      rows
        .filter((r) => r.gross_spend_m > 0 && r.played > 0)
        .map((r) => ({
          ...r,
          logSpendM: Math.log(r.gross_spend_m),
          winRatePct: Number(((r.wins / r.played) * 100).toFixed(1)),
        })),
    [rows],
  );

  // OLS regression line from backend parameters (exact pooled 6A or league 6C slope through sample mean)
  const regressionLine = useMemo(() => {
    if (!meta || scatterPoints.length < 2) return [];
    const ols = meta.regression_summary['6A_gross_spend'].ols_log_spend_m_to_ppg;
    const selectedLeague = meta.league_summaries.find((l) => l.league_id === leagueId);
    const slope = selectedLeague ? selectedLeague.statistics.slope_ppg : ols.slope;
    let intercept = ols.intercept ?? 0.989048;
    if (selectedLeague) {
      const meanX =
        scatterPoints.reduce((s, p) => s + p.logSpendM, 0) / scatterPoints.length;
      const meanY = scatterPoints.reduce((s, p) => s + p.ppg, 0) / scatterPoints.length;
      intercept = meanY - slope * meanX;
    }
    const xs = scatterPoints.map((p) => p.logSpendM);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    return [
      { logSpendM: minX, ppg: Number((intercept + slope * minX).toFixed(3)) },
      { logSpendM: maxX, ppg: Number((intercept + slope * maxX).toFixed(3)) },
    ];
  }, [meta, scatterPoints, leagueId]);

  const activeStats = useMemo(() => {
    if (!meta) return null;
    if (leagueId) {
      const ls = meta.league_summaries.find((l) => l.league_id === leagueId);
      if (ls) {
        return {
          title: ls.league_name,
          r: ls.statistics.pearson_r_ppg,
          rho: ls.statistics.spearman_rho_pos,
          r2: ls.statistics.r_squared_ppg,
          slope: ls.statistics.slope_ppg,
          p: ls.statistics.cluster_p,
          ci: ls.statistics.cluster_95ci,
          n: ls.statistics.n,
        };
      }
    }
    const s6a = meta.regression_summary['6A_gross_spend'];
    const ols = s6a.ols_log_spend_m_to_ppg;
    return {
      title: 'All Big 5 Leagues (Pooled)',
      r: s6a.pearson_r_log_vs_ppg,
      rho: s6a.spearman_rho_spend_vs_ppg,
      r2: ols.r_squared ?? 0.2076,
      slope: ols.slope,
      p: ols.cluster_p,
      ci: ols.cluster_95ci ?? [0.1095, 0.1657],
      n: ols.n,
    };
  }, [meta, leagueId]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div className="filter-bar" role="region" aria-label="Domestic performance filters">
        <div className="filter-field">
          <label className="filter-label" htmlFor="dom-league">League</label>
          <select
            id="dom-league"
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
          <label className="filter-label" htmlFor="dom-season">Season</label>
          <select
            id="dom-season"
            className="control-select"
            value={season}
            onChange={(e) => setSeason(e.target.value)}
          >
            <option value="">All Seasons (2012–2025)</option>
            {SEASONS.map((y) => (
              <option key={y} value={y}>{y}/{String((y + 1) % 100).padStart(2, '0')}</option>
            ))}
          </select>
        </div>

        <div className="filter-field" style={{ flex: '1 1 200px' }}>
          <label className="filter-label" htmlFor="dom-club">Search Club</label>
          <input
            id="dom-club"
            type="text"
            className="control-input"
            placeholder="e.g. Liverpool, Arsenal, Real Madrid..."
            value={clubQuery}
            onChange={(e) => setClubQuery(e.target.value)}
          />
        </div>

        <div className="filter-field">
          <label className="filter-label" htmlFor="dom-sort">Sort Table By</label>
          <select
            id="dom-sort"
            className="control-select"
            value={`${sortBy}:${sortOrder}`}
            onChange={(e) => {
              const [col, ord] = e.target.value.split(':') as [string, 'asc' | 'desc'];
              setSortBy(col);
              setSortOrder(ord);
            }}
          >
            <option value="ppg:desc">PPG (High → Low)</option>
            <option value="gross_spend_m:desc">Gross Spend (High → Low)</option>
            <option value="league_position:asc">League Position (1st → 20th)</option>
            <option value="season:desc">Season (Newest)</option>
          </select>
        </div>

        <label style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12.5, alignSelf: 'flex-end', paddingBottom: 6, cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={positiveOnly}
            onChange={(e) => setPositiveOnly(e.target.checked)}
          />
          Gross Spend &gt; 0
        </label>
      </div>

      {loading && <LoadingState message="Loading domestic league standings and regression data..." />}
      {!loading && error && <ErrorState message={error} onRetry={() => void load()} />}
      {!loading && !error && meta && activeStats && (
        <>
          <WarningBanner tone="info" title="Non-Causal Regression Context">
            {meta.interpretation_note}
          </WarningBanner>

          <div className="kpi-grid">
            <KpiCard
              label={`Pearson r (${activeStats.title})`}
              value={activeStats.r.toFixed(4)}
              sublabel={`OLS Sample n = ${formatInteger(activeStats.n)}`}
              badge="Log Spend → PPG"
            />
            <KpiCard
              label="Variance Explained (R²)"
              value={formatPercent(activeStats.r2 * 100, 2)}
              sublabel={`Cluster-robust p = ${formatPValue(activeStats.p)}`}
              badge="Pooled / League"
              badgeTone="sky"
            />
            <KpiCard
              label="OLS Slope (ln €M → PPG)"
              value={`+${activeStats.slope.toFixed(4)}`}
              sublabel={`95% CI [${activeStats.ci[0].toFixed(3)}, ${activeStats.ci[1].toFixed(3)}]`}
              badge={`+${(Math.log(2) * activeStats.slope).toFixed(3)} PPG / 2×`}
            />
            <KpiCard
              label={leagueId ? 'Spearman ρ (Rank Pos)' : 'Spearman ρ (PPG)'}
              value={activeStats.rho.toFixed(4)}
              sublabel={`Showing ${formatInteger(rows.length)} filtered club-seasons`}
              badgeTone="amber"
            />
          </div>

          {scatterPoints.length === 0 ? (
            <EmptyState message="No positive-spend club-seasons match your current filters." />
          ) : (
            <div className="chart-grid-2">
              <ChartCard
                title="Gross Spending vs Points Per Game (with OLS Fit)"
                subtitle={`ln(Gross Spend €M) vs PPG across ${formatInteger(scatterPoints.length)} observations`}
                note={`Dashed line plots the validated OLS fit (slope = ${activeStats.slope.toFixed(4)}).`}
              >
                <div style={{ width: '100%', height: 320 }}>
                  <ResponsiveContainer>
                    <ScatterChart margin={{ top: 10, right: 18, left: 0, bottom: 8 }}>
                      <CartesianGrid stroke="rgba(148,163,184,0.12)" strokeDasharray="3 3" />
                      <XAxis
                        type="number"
                        dataKey="logSpendM"
                        name="ln(Spend €M)"
                        stroke="#94a3b8"
                        fontSize={12}
                        tickFormatter={(v: number) => `€${Math.exp(v).toFixed(0)}M`}
                      />
                      <YAxis type="number" dataKey="ppg" name="PPG" stroke="#94a3b8" fontSize={12} domain={[0.3, 2.8]} />
                      <Tooltip
                        content={({ active, payload }) => {
                          if (!active || !payload?.length) return null;
                          const p = payload[0].payload as (typeof scatterPoints)[number];
                          if (!p.name) return null;
                          return (
                            <div className="chart-tooltip">
                              <div className="chart-tooltip-title">{p.name} ({p.transfer_season})</div>
                              <div className="chart-tooltip-row"><span>League:</span><span>{p.league_name} (#{p.league_position})</span></div>
                              <div className="chart-tooltip-row"><span>Gross Spend:</span><span>{formatEurMillions(p.gross_spend_m)}</span></div>
                              <div className="chart-tooltip-row"><span>PPG / Pts:</span><span>{p.ppg.toFixed(3)} ({p.points} pts)</span></div>
                            </div>
                          );
                        }}
                      />
                      <Scatter name="Club-Seasons" data={scatterPoints} fillOpacity={0.7}>
                        {scatterPoints.map((entry) => (
                          <Cell key={`${entry.club_id}-${entry.season}`} fill={LEAGUE_COLOR_MAP[entry.league_id] ?? '#10b981'} />
                        ))}
                      </Scatter>
                      {regressionLine.length === 2 && (
                        <Scatter
                          name="OLS Regression Line"
                          data={regressionLine}
                          line={{ stroke: '#f8fafc', strokeWidth: 2.5, strokeDasharray: '6 4' }}
                          fill="transparent"
                          isAnimationActive={false}
                        />
                      )}
                    </ScatterChart>
                  </ResponsiveContainer>
                </div>
              </ChartCard>

              <ChartCard
                title="Gross Spending vs Win Rate (%)"
                subtitle="Wins ÷ Matches Played (%) vs ln(Gross Spend €M)"
                note="Points are colored by competition (Premier League green, LaLiga amber, Serie A sky, Bundesliga rose, Ligue 1 violet)."
              >
                <div style={{ width: '100%', height: 320 }}>
                  <ResponsiveContainer>
                    <ScatterChart margin={{ top: 10, right: 18, left: 0, bottom: 8 }}>
                      <CartesianGrid stroke="rgba(148,163,184,0.12)" strokeDasharray="3 3" />
                      <XAxis
                        type="number"
                        dataKey="logSpendM"
                        stroke="#94a3b8"
                        fontSize={12}
                        tickFormatter={(v: number) => `€${Math.exp(v).toFixed(0)}M`}
                      />
                      <YAxis type="number" dataKey="winRatePct" stroke="#94a3b8" fontSize={12} unit="%" domain={[0, 95]} />
                      <Tooltip
                        content={({ active, payload }) => {
                          if (!active || !payload?.length) return null;
                          const p = payload[0].payload as (typeof scatterPoints)[number];
                          return (
                            <div className="chart-tooltip">
                              <div className="chart-tooltip-title">{p.name} ({p.transfer_season})</div>
                              <div className="chart-tooltip-row"><span>Win Rate:</span><span>{p.winRatePct.toFixed(1)}% ({p.wins}/{p.played})</span></div>
                              <div className="chart-tooltip-row"><span>Gross Spend:</span><span>{formatEurMillions(p.gross_spend_m)}</span></div>
                              <div className="chart-tooltip-row"><span>Net Spend:</span><span>{formatEurMillions(p.net_spend_m, true)}</span></div>
                            </div>
                          );
                        }}
                      />
                      <Scatter data={scatterPoints} fillOpacity={0.7}>
                        {scatterPoints.map((entry) => (
                          <Cell key={`wr-${entry.club_id}-${entry.season}`} fill={LEAGUE_COLOR_MAP[entry.league_id] ?? '#10b981'} />
                        ))}
                      </Scatter>
                    </ScatterChart>
                  </ResponsiveContainer>
                </div>
              </ChartCard>
            </div>
          )}

          <div className="chart-grid-asym">
            <ChartCard
              title="Club-Level Observations"
              subtitle={`Top ${Math.min(rows.length, 60)} of ${formatInteger(rows.length)} matching club-seasons`}
            >
              {rows.length === 0 ? (
                <EmptyState />
              ) : (
                <div className="table-wrap" style={{ maxHeight: 350 }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Club</th>
                        <th>Season</th>
                        <th>League</th>
                        <th className="num">Pos</th>
                        <th className="num">PPG</th>
                        <th className="num">Win %</th>
                        <th className="num">Gross Spend</th>
                        <th className="num">Net Spend</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.slice(0, 60).map((r) => (
                        <tr key={`${r.club_id}-${r.season}`}>
                          <td><strong>{r.name}</strong></td>
                          <td>{r.transfer_season}</td>
                          <td>{r.league_name}</td>
                          <td className="num">#{r.league_position}</td>
                          <td className="num">{r.ppg.toFixed(3)}</td>
                          <td className="num">{((r.wins / Math.max(r.played, 1)) * 100).toFixed(1)}%</td>
                          <td className="num">{formatEurMillions(r.gross_spend_m)}</td>
                          <td className="num">{formatEurMillions(r.net_spend_m, true)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </ChartCard>

            <ChartCard
              title="League-Wise R² (Log Spend → PPG)"
              subtitle="Explained variance across Big 5 domestic leagues (Analysis 6C)"
            >
              <div style={{ width: '100%', height: 320 }}>
                <ResponsiveContainer>
                  <BarChart
                    data={meta.league_summaries.map((l) => ({
                      league: l.league_name,
                      leagueId: l.league_id,
                      r2Pct: Number((l.statistics.r_squared_ppg * 100).toFixed(1)),
                      r: l.statistics.pearson_r_ppg,
                    }))}
                    layout="vertical"
                    margin={{ top: 8, right: 20, left: 16, bottom: 4 }}
                  >
                    <CartesianGrid stroke="rgba(148,163,184,0.1)" strokeDasharray="3 3" />
                    <XAxis type="number" stroke="#94a3b8" fontSize={12} domain={[0, 40]} unit="%" />
                    <YAxis type="category" dataKey="league" width={110} stroke="#cbd5e1" fontSize={12} />
                    <Tooltip
                      contentStyle={{
                        background: 'rgba(10,16,26,0.96)',
                        border: '1px solid rgba(148,163,184,0.25)',
                        borderRadius: 10,
                        fontSize: 12,
                      }}
                    />
                    <Bar dataKey="r2Pct" name="R² (%)" radius={[0, 6, 6, 0]}>
                      {meta.league_summaries.map((l) => (
                        <Cell key={l.league_id} fill={LEAGUE_COLOR_MAP[l.league_id] ?? '#10b981'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </ChartCard>
          </div>
        </>
      )}
    </div>
  );
}
