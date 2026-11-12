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
import type {
  ClubValuationSummaryRow,
  FeeVsMVStatistics,
  FeeVsMVTransferRow,
  PlayerValueGainRow,
} from '../types/api';
import {
  formatDecimal,
  formatEurCompact,
  formatInteger,
  formatPercent,
  TOP5_LEAGUE_OPTIONS,
} from '../utils/formatters';
import { ChartCard } from '../components/common/ChartCard';
import { KpiCard } from '../components/common/KpiCard';
import { EmptyState, ErrorState, LoadingState, WarningBanner } from '../components/common/StatePanel';

export function MarketValueSection() {
  const [leagueId, setLeagueId] = useState<string>('');
  const [clubQuery, setClubQuery] = useState<string>('');
  const [sortClubsBy, setSortClubsBy] = useState<string>('total_est_peak_mv_gain');

  const [disclaimer, setDisclaimer] = useState<string>('');
  const [feeStats, setFeeStats] = useState<FeeVsMVStatistics | null>(null);
  const [clubs, setClubs] = useState<ClubValuationSummaryRow[]>([]);
  const [transfers, setTransfers] = useState<FeeVsMVTransferRow[]>([]);
  const [playerGains, setPlayerGains] = useState<PlayerValueGainRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      const [sumRes, trRes, pgRes] = await Promise.all([
        api.getMarketValueSummary(
          {
            league_id: leagueId || undefined,
            club_name: clubQuery.trim() || undefined,
            sort_by: sortClubsBy,
            sort_order: 'desc',
            limit: 40,
            offset: 0,
          },
          signal,
        ),
        api.getMarketValueTransfers(
          {
            league_id: leagueId || undefined,
            club_name: clubQuery.trim() || undefined,
            is_top5: true,
            sort_by: 'transfer_fee',
            sort_order: 'desc',
            limit: 200,
            offset: 0,
          },
          signal,
        ),
        api.getPlayerValueGains(
          {
            league_id: leagueId || undefined,
            club_name: clubQuery.trim() || undefined,
            sort_by: 'est_peak_mv_gain',
            sort_order: 'desc',
            limit: 30,
            offset: 0,
          },
          signal,
        ),
      ]);
      setDisclaimer(sumRes.valuation_disclaimer);
      setFeeStats(sumRes.fee_vs_mv_statistics);
      setClubs(sumRes.club_valuation_summaries);
      setTransfers(trRes.transfers);
      setPlayerGains(pgRes.player_gains);
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        setError((err as Error).message);
      }
    } finally {
      setLoading(false);
    }
  }, [leagueId, clubQuery, sortClubsBy]);

  useEffect(() => {
    const ctrl = new AbortController();
    const t = setTimeout(() => void load(ctrl.signal), 180);
    return () => {
      clearTimeout(t);
      ctrl.abort();
    };
  }, [load]);

  const scatterTransfers = useMemo(
    () =>
      transfers.map((t) => ({
        ...t,
        mvM: Number((t.mv_at_transfer / 1e6).toFixed(2)),
        feeM: Number((t.transfer_fee / 1e6).toFixed(2)),
      })),
    [transfers],
  );

  const fairValueLine = useMemo(() => {
    if (scatterTransfers.length === 0) return [];
    const maxVal = Math.max(
      ...scatterTransfers.map((t) => Math.max(t.mvM, t.feeM)),
      50,
    );
    return [
      { mvM: 0, feeM: 0 },
      { mvM: maxVal, feeM: maxVal },
    ];
  }, [scatterTransfers]);

  const outcomeBreakdown = useMemo(() => {
    if (!feeStats) return [];
    return [
      { label: 'Underpay (Fee < MV)', pct: feeStats.pct_underpay, color: '#10b981' },
      { label: 'Overpay (Fee > MV)', pct: feeStats.pct_overpay, color: '#f43f5e' },
      { label: 'Exact Match (Fee = MV)', pct: feeStats.pct_exact_match, color: '#38bdf8' },
    ];
  }, [feeStats]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <WarningBanner tone="warning" title="Important Methodological Distinction: Estimated Market Value ≠ Financial ROI">
        {disclaimer ||
          'Transfermarkt player valuations are crowdsourced market value estimates, NOT realized transfer sale proceeds, net accounting profit, or cash Return on Investment (ROI).'}
      </WarningBanner>

      <div className="filter-bar" role="region" aria-label="Market value filters">
        <div className="filter-field">
          <label className="filter-label" htmlFor="mv-league">Top-5 League</label>
          <select
            id="mv-league"
            className="control-select"
            value={leagueId}
            onChange={(e) => setLeagueId(e.target.value)}
          >
            <option value="">All Top-5 Leagues</option>
            {TOP5_LEAGUE_OPTIONS.map((l) => (
              <option key={l.id} value={l.id}>{l.name}</option>
            ))}
          </select>
        </div>

        <div className="filter-field" style={{ flex: '1 1 220px' }}>
          <label className="filter-label" htmlFor="mv-club">Filter Club Name</label>
          <input
            id="mv-club"
            type="text"
            className="control-input"
            placeholder="e.g. Dortmund, Liverpool, Stuttgart..."
            value={clubQuery}
            onChange={(e) => setClubQuery(e.target.value)}
          />
        </div>

        <div className="filter-field">
          <label className="filter-label" htmlFor="mv-sort">Sort Club Summary</label>
          <select
            id="mv-sort"
            className="control-select"
            value={sortClubsBy}
            onChange={(e) => setSortClubsBy(e.target.value)}
          >
            <option value="total_est_peak_mv_gain">Est. Peak MV Gain</option>
            <option value="portfolio_peak_mv_multiple">Peak MV / Fee Multiple</option>
            <option value="portfolio_latest_mv_multiple">Latest MV / Fee Multiple</option>
            <option value="total_spent">Total Acquisition Spend</option>
          </select>
        </div>
      </div>

      {loading && <LoadingState message="Loading transfer valuation analytics..." />}
      {!loading && error && <ErrorState message={error} onRetry={() => void load()} />}
      {!loading && !error && feeStats && (
        <>
          <div className="kpi-grid">
            <KpiCard
              label="Log-Log Fee vs MV R²"
              value={formatPercent(feeStats.ols_log_mv_to_log_fee.r_squared! * 100, 2)}
              sublabel={`Pearson r = ${formatDecimal(feeStats.pearson_r_log_log, 4)} • n = ${formatInteger(feeStats.n)}`}
              badge={`ρ = ${feeStats.spearman_rho.toFixed(3)}`}
            />
            <KpiCard
              label="Median Fee / MV Ratio"
              value={`${feeStats.median_fee_to_mv_ratio.toFixed(2)}×`}
              sublabel={`Mean ratio = ${feeStats.mean_fee_to_mv_ratio.toFixed(2)}× (right-skewed)`}
              badgeTone="sky"
            />
            <KpiCard
              label="Transfer Premium Split"
              value={`${feeStats.pct_overpay.toFixed(1)}% Overpay`}
              sublabel={`${feeStats.pct_underpay.toFixed(1)}% below MV • ${feeStats.pct_exact_match.toFixed(1)}% exact`}
              badgeTone="amber"
            />
            <KpiCard
              label="Top Est. Peak MV Gain Club"
              value={clubs[0]?.club_name ?? '—'}
              sublabel={clubs[0] ? `${formatEurCompact(clubs[0].total_est_peak_mv_gain, true)} (${clubs[0].portfolio_peak_mv_multiple.toFixed(2)}×)` : 'No clubs matched'}
              badgeTone="green"
            />
          </div>

          <div className="chart-grid-2">
            <ChartCard
              title="Transfer Fee vs Estimated Market Value (Top 200 Deals)"
              subtitle="Arrival MV (€M) vs Transfer Fee (€M); dashed line shows 1:1 parity"
              note={`Full dataset (n=${formatInteger(feeStats.n)}): log-log OLS slope=${feeStats.ols_log_mv_to_log_fee.slope.toFixed(4)} (cluster 95% CI [${feeStats.ols_log_mv_to_log_fee.cluster_95ci![0].toFixed(3)}, ${feeStats.ols_log_mv_to_log_fee.cluster_95ci![1].toFixed(3)}]).`}
            >
              {scatterTransfers.length === 0 ? (
                <EmptyState />
              ) : (
                <div style={{ width: '100%', height: 310 }}>
                  <ResponsiveContainer>
                    <ScatterChart margin={{ top: 10, right: 18, left: 0, bottom: 8 }}>
                      <CartesianGrid stroke="rgba(148,163,184,0.12)" strokeDasharray="3 3" />
                      <XAxis type="number" dataKey="mvM" stroke="#94a3b8" fontSize={12} unit="M" />
                      <YAxis type="number" dataKey="feeM" stroke="#94a3b8" fontSize={12} unit="M" />
                      <Tooltip
                        content={({ active, payload }) => {
                          if (!active || !payload?.length) return null;
                          const t = payload[0].payload as (typeof scatterTransfers)[number];
                          if (!t.player_name) return null;
                          return (
                            <div className="chart-tooltip">
                              <div className="chart-tooltip-title">{t.player_name} ({t.transfer_season})</div>
                              <div className="chart-tooltip-row"><span>Club:</span><span>{t.to_club_name}</span></div>
                              <div className="chart-tooltip-row"><span>Transfer Fee:</span><span>€{t.feeM.toFixed(1)}M</span></div>
                              <div className="chart-tooltip-row"><span>Arrival MV:</span><span>€{t.mvM.toFixed(1)}M</span></div>
                              <div className="chart-tooltip-row"><span>Premium:</span><span>{t.premium_pct > 0 ? '+' : ''}{t.premium_pct.toFixed(1)}%</span></div>
                            </div>
                          );
                        }}
                      />
                      <Scatter data={scatterTransfers} fill="#38bdf8" fillOpacity={0.72} />
                      {fairValueLine.length === 2 && (
                        <Scatter
                          data={fairValueLine}
                          line={{ stroke: '#10b981', strokeWidth: 2, strokeDasharray: '6 4' }}
                          fill="transparent"
                          isAnimationActive={false}
                        />
                      )}
                    </ScatterChart>
                  </ResponsiveContainer>
                </div>
              )}
            </ChartCard>

            <ChartCard
              title="Club-Level Est. Peak MV Gain (€M)"
              subtitle="Top matching clubs using spell-bounded [transfer_date, next_transfer_date) valuations"
              note="Peak MV gain compares maximum observed Transfermarkt valuation during club spell vs acquisition fee (before wages/amortization)."
            >
              {clubs.length === 0 ? (
                <EmptyState />
              ) : (
                <div style={{ width: '100%', height: 310 }}>
                  <ResponsiveContainer>
                    <BarChart
                      data={clubs.slice(0, 10).map((c) => ({
                        club: c.club_name,
                        peakGainM: Number((c.total_est_peak_mv_gain / 1e6).toFixed(1)),
                        latestGainM: Number((c.total_est_latest_mv_gain / 1e6).toFixed(1)),
                        peakMultiple: c.portfolio_peak_mv_multiple,
                      }))}
                      layout="vertical"
                      margin={{ top: 8, right: 20, left: 20, bottom: 4 }}
                    >
                      <CartesianGrid stroke="rgba(148,163,184,0.1)" strokeDasharray="3 3" />
                      <XAxis type="number" stroke="#94a3b8" fontSize={12} tickFormatter={(v: number) => `€${v}M`} />
                      <YAxis type="category" dataKey="club" width={135} stroke="#cbd5e1" fontSize={11.5} />
                      <Tooltip
                        contentStyle={{
                          background: 'rgba(10,16,26,0.96)',
                          border: '1px solid rgba(148,163,184,0.25)',
                          borderRadius: 10,
                          fontSize: 12,
                        }}
                      />
                      <Bar dataKey="peakGainM" name="Est. Peak MV Gain (€M)" fill="#10b981" radius={[0, 4, 4, 0]} />
                      <Bar dataKey="latestGainM" name="Est. Latest MV Gain (€M)" fill="#f59e0b" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </ChartCard>
          </div>

          <div className="chart-grid-asym">
            <ChartCard
              title="Club Valuation Summaries (Spell-Bounded)"
              subtitle={`Top ${clubs.length} matching clubs • non-financial valuation multiples`}
            >
              {clubs.length === 0 ? (
                <EmptyState />
              ) : (
                <div className="table-wrap" style={{ maxHeight: 330 }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Club</th>
                        <th>League</th>
                        <th className="num">Signings</th>
                        <th className="num">Spent</th>
                        <th className="num">Est. Peak MV Gain</th>
                        <th className="num">Peak MV / Fee</th>
                        <th className="num">Latest MV / Fee</th>
                      </tr>
                    </thead>
                    <tbody>
                      {clubs.map((c) => (
                        <tr key={c.club_id}>
                          <td><strong>{c.club_name}</strong></td>
                          <td>{c.league_name}</td>
                          <td className="num">{c.num_signings}</td>
                          <td className="num">{formatEurCompact(c.total_spent)}</td>
                          <td className="num" style={{ color: c.total_est_peak_mv_gain >= 0 ? 'var(--accent-bright)' : 'var(--rose)' }}>
                            {formatEurCompact(c.total_est_peak_mv_gain, true)}
                          </td>
                          <td className="num">{c.portfolio_peak_mv_multiple.toFixed(2)}×</td>
                          <td className="num">{c.portfolio_latest_mv_multiple.toFixed(2)}×</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </ChartCard>

            <ChartCard
              title="Fee vs Arrival MV Outcome Mix"
              subtitle={`All ${formatInteger(feeStats.n)} paid transfers with positive MV`}
            >
              <div style={{ width: '100%', height: 210 }}>
                <ResponsiveContainer>
                  <BarChart data={outcomeBreakdown} margin={{ top: 10, right: 16, left: 0, bottom: 4 }}>
                    <CartesianGrid stroke="rgba(148,163,184,0.1)" strokeDasharray="3 3" />
                    <XAxis dataKey="label" stroke="#94a3b8" fontSize={11} />
                    <YAxis stroke="#94a3b8" fontSize={12} unit="%" />
                    <Tooltip
                      contentStyle={{
                        background: 'rgba(10,16,26,0.96)',
                        border: '1px solid rgba(148,163,184,0.25)',
                        borderRadius: 10,
                        fontSize: 12,
                      }}
                    />
                    <Bar dataKey="pct" name="Share (%)" radius={[6, 6, 0, 0]}>
                      {outcomeBreakdown.map((o) => (
                        <Cell key={o.label} fill={o.color} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div style={{ marginTop: 12 }}>
                <div className="filter-label" style={{ marginBottom: 6 }}>Top Spell-Bounded Player MV Gains</div>
                <div className="table-wrap" style={{ maxHeight: 165 }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Player</th>
                        <th>Club</th>
                        <th className="num">Fee</th>
                        <th className="num">Peak MV</th>
                        <th className="num">Multiple</th>
                      </tr>
                    </thead>
                    <tbody>
                      {playerGains.slice(0, 12).map((p) => (
                        <tr key={`${p.player_id}-${p.transfer_date}`}>
                          <td>{p.player_name}</td>
                          <td>{p.club_name}</td>
                          <td className="num">{formatEurCompact(p.transfer_fee)}</td>
                          <td className="num">{formatEurCompact(p.peak_mv)}</td>
                          <td className="num">{p.peak_mv_to_fee_multiple.toFixed(2)}×</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </ChartCard>
          </div>
        </>
      )}
    </div>
  );
}
