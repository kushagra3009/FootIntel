import { useCallback, useEffect, useState } from 'react';
import { Award, Coins, Database, Globe, TrendingUp } from 'lucide-react';
import {
  Bar,
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
  DomesticPerformanceResponse,
  OverviewResponse,
  UCLPerformanceResponse,
} from '../types/api';
import {
  formatDecimal,
  formatEurCompact,
  formatInteger,
  formatPercent,
  formatPValue,
} from '../utils/formatters';
import { ChartCard } from '../components/common/ChartCard';
import { KpiCard } from '../components/common/KpiCard';
import { ErrorState, LoadingState, WarningBanner } from '../components/common/StatePanel';

interface OverviewBundle {
  overview: OverviewResponse;
  domestic: DomesticPerformanceResponse;
  ucl: UCLPerformanceResponse;
}

export function OverviewSection() {
  const [data, setData] = useState<OverviewBundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      const [overview, domestic, ucl] = await Promise.all([
        api.getOverview(signal),
        api.getDomestic({ limit: 1 }, signal),
        api.getUcl({ limit: 1 }, signal),
      ]);
      setData({ overview, domestic, ucl });
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        setError((err as Error).message);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    void load(ctrl.signal);
    return () => ctrl.abort();
  }, [load]);

  if (loading) return <LoadingState message="Loading executive overview from FastAPI..." />;
  if (error || !data) return <ErrorState message={error ?? 'No data returned'} onRetry={() => void load()} />;

  const { overview, domestic, ucl } = data;
  const { kpis } = overview;
  const s6a = domestic.regression_summary['6A_gross_spend'];
  const s6dAll = ucl.statistical_summary.all_ucl_spenders;
  const comp = ucl.domestic_vs_ucl_comparison;

  const trendChartData = overview.historical_summary.map((row) => ({
    season: row.transfer_season,
    gameSeason: row.game_season,
    spendB: Number((row.total_spending / 1e9).toFixed(2)),
    coveragePct: row.pct_active_players_covered,
    paidTransfers: row.paid_transfers,
  }));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <section className="hero-card">
        <div className="hero-eyebrow">Empirical Transfer Analytics • {kpis.analysis_window}</div>
        <h2 className="hero-title">{overview.research_question}</h2>
        <p className="hero-desc">{overview.methodology_disclaimer}</p>
      </section>

      <div className="kpi-grid">
        <KpiCard
          label="Top-5 Gross Transfer Spending"
          value={formatEurCompact(kpis.top5_total_spending_eur_2012_2025)}
          sublabel={`${formatInteger(kpis.top5_paid_transfers_2012_2025)} paid Top-5 transfers`}
          badge="2012–2025"
          icon={<Coins size={16} />}
        />
        <KpiCard
          label="Transfers & Valuations in DB"
          value={formatInteger(kpis.total_transfers_db)}
          sublabel={`${formatInteger(kpis.total_valuations_db)} valuations • ${formatInteger(kpis.total_games_db)} games`}
          badge="DuckDB Live"
          badgeTone="sky"
          icon={<Database size={16} />}
        />
        <KpiCard
          label="Clubs & Leagues Covered"
          value={`${formatInteger(kpis.top5_unique_clubs)} Top-5 Clubs`}
          sublabel={`${formatInteger(kpis.total_clubs_db)} total DB clubs • Big 5 + UCL`}
          badge={`${formatInteger(kpis.top5_domestic_observations)} obs`}
          badgeTone="green"
          icon={<Globe size={16} />}
        />
        <KpiCard
          label="Fee vs MV & Spell Samples"
          value={formatInteger(kpis.fee_vs_mv_sample_size)}
          sublabel={`${formatInteger(kpis.spell_bounded_valuations_sample)} spell-bounded • ${formatInteger(kpis.ucl_observations)} UCL obs`}
          badge="Validated"
          badgeTone="sky"
          icon={<TrendingUp size={16} />}
        />
      </div>

      <div className="chart-grid-2">
        <ChartCard
          title="Domestic League Indicators (Big 5)"
          subtitle="Pooled OLS & rank correlations across club-seasons with positive spending"
          note="Cross-sectional R² reflects persistent between-club hierarchy; see Statistical Insights for Two-Way Fixed Effects."
        >
          <div className="kpi-grid-3" style={{ gap: 12 }}>
            <div className="card" style={{ padding: 14, background: 'var(--bg-card-elevated)' }}>
              <div className="filter-label">Pearson r (log spend → PPG)</div>
              <div className="kpi-value" style={{ fontSize: 22, marginTop: 6 }}>
                {formatDecimal(s6a.pearson_r_log_vs_ppg, 4)}
              </div>
              <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 4 }}>
                n = {formatInteger(s6a.n_spenders)} ({s6a.unique_clubs_spenders} clubs)
              </div>
            </div>
            <div className="card" style={{ padding: 14, background: 'var(--bg-card-elevated)' }}>
              <div className="filter-label">Pooled R² (PPG)</div>
              <div className="kpi-value" style={{ fontSize: 22, marginTop: 6, color: 'var(--accent-bright)' }}>
                {formatPercent(s6a.ols_log_spend_m_to_ppg.r_squared! * 100, 2)}
              </div>
              <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 4 }}>
                Cluster p = {formatPValue(s6a.ols_log_spend_m_to_ppg.cluster_p)}
              </div>
            </div>
            <div className="card" style={{ padding: 14, background: 'var(--bg-card-elevated)' }}>
              <div className="filter-label">Spearman ρ (spend → PPG)</div>
              <div className="kpi-value" style={{ fontSize: 22, marginTop: 6 }}>
                {formatDecimal(s6a.spearman_rho_spend_vs_ppg, 4)}
              </div>
              <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 4 }}>
                Net spend R² = {formatPercent(domestic.regression_summary['6B_net_spend'].ols_net_spend_m_to_ppg.r_squared! * 100, 2)}
              </div>
            </div>
          </div>
          <div className="table-wrap" style={{ marginTop: 14 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>League</th>
                  <th className="num">Obs</th>
                  <th className="num">Avg Spend</th>
                  <th className="num">Avg PPG</th>
                  <th className="num">r (PPG)</th>
                  <th className="num">R²</th>
                </tr>
              </thead>
              <tbody>
                {domestic.league_summaries.map((ls) => (
                  <tr key={ls.league_id}>
                    <td>{ls.league_name}</td>
                    <td className="num">{ls.positive_spend_observations}</td>
                    <td className="num">€{ls.avg_gross_spend_m.toFixed(1)}M</td>
                    <td className="num">{ls.avg_ppg.toFixed(3)}</td>
                    <td className="num">{ls.statistics.pearson_r_ppg.toFixed(3)}</td>
                    <td className="num">{formatPercent(ls.statistics.r_squared_ppg * 100, 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </ChartCard>

        <ChartCard
          title="UEFA Champions League Indicators"
          subtitle="All UCL spenders (n=415) vs Paired Top-5 UCL qualifiers (n=248)"
          actions={<Award size={18} color="var(--accent-bright)" />}
          note={`Steiger z-test (Domestic PPG vs UCL PPG on same ${comp.n_paired_spenders} club-seasons): z = ${comp.steiger_z_dom_ppg_vs_ucl_ppg.toFixed(2)}, p = ${formatPValue(comp.steiger_p_dom_ppg_vs_ucl_ppg)}.`}
        >
          <div className="kpi-grid-3" style={{ gap: 12 }}>
            <div className="card" style={{ padding: 14, background: 'var(--bg-card-elevated)' }}>
              <div className="filter-label">All UCL PPG r / R²</div>
              <div className="kpi-value" style={{ fontSize: 22, marginTop: 6 }}>
                {s6dAll.ucl_ppg_pearson_r.toFixed(3)}
              </div>
              <div style={{ fontSize: 11.5, color: 'var(--accent-bright)', marginTop: 4 }}>
                R² = {formatPercent(s6dAll.ucl_ppg_ols.r_squared! * 100, 1)} (n={s6dAll.n})
              </div>
            </div>
            <div className="card" style={{ padding: 14, background: 'var(--bg-card-elevated)' }}>
              <div className="filter-label">UCL Stage ρ / R²</div>
              <div className="kpi-value" style={{ fontSize: 22, marginTop: 6 }}>
                {s6dAll.stage_spearman_rho.toFixed(3)}
              </div>
              <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 4 }}>
                Stage R² = {formatPercent(s6dAll.stage_ols.r_squared! * 100, 1)}
              </div>
            </div>
            <div className="card" style={{ padding: 14, background: 'var(--bg-card-elevated)' }}>
              <div className="filter-label">Top-5 Paired UCL r</div>
              <div className="kpi-value" style={{ fontSize: 22, marginTop: 6, color: 'var(--sky)' }}>
                {comp.spenders_ucl_ppg_r.toFixed(3)}
              </div>
              <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 4 }}>
                vs Dom r = {comp.spenders_domestic_ppg_r.toFixed(3)}
              </div>
            </div>
          </div>

          <div style={{ marginTop: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
            {overview.key_findings.map((kf) => (
              <div
                key={kf.metric_name}
                style={{
                  padding: '10px 12px',
                  borderRadius: 10,
                  background: 'var(--bg-card-elevated)',
                  border: '1px solid var(--border-subtle)',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center' }}>
                  <strong style={{ fontSize: 13 }}>{kf.topic}</strong>
                  <span className="tag-pill tag-green">n={formatInteger(kf.sample_size)}</span>
                </div>
                <div style={{ fontSize: 12.5, color: 'var(--text-primary)', marginTop: 4 }}>{kf.headline}</div>
                <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 3 }}>{kf.interpretation_note}</div>
              </div>
            ))}
          </div>
        </ChartCard>
      </div>

      <ChartCard
        title="Historical Top-5 Spending (€B) vs Active-Player Cohort Coverage (%)"
        subtitle="Shaded region (12/13–21/22) marks <85% active Top-5 player coverage in the transfers table"
        note="Because transfermarkt-datasets only scraped transfers for players with last_season >= 2023, pre-2022/23 totals undercount retired cohorts."
      >
        <div style={{ width: '100%', height: 310 }}>
          <ResponsiveContainer>
            <ComposedChart data={trendChartData} margin={{ top: 12, right: 18, left: 0, bottom: 4 }}>
              <CartesianGrid stroke="rgba(148,163,184,0.12)" strokeDasharray="3 3" />
              <ReferenceArea x1="12/13" x2="21/22" fill="rgba(245,158,11,0.08)" />
              <XAxis dataKey="season" stroke="#94a3b8" fontSize={12} />
              <YAxis yAxisId="left" stroke="#10b981" fontSize={12} unit="B" />
              <YAxis yAxisId="right" orientation="right" stroke="#38bdf8" fontSize={12} domain={[0, 100]} unit="%" />
              <Tooltip
                content={({ active, payload, label }) => {
                  if (!active || !payload?.length) return null;
                  const row = payload[0].payload as (typeof trendChartData)[number];
                  return (
                    <div className="chart-tooltip">
                      <div className="chart-tooltip-title">Season {label}</div>
                      <div className="chart-tooltip-row">
                        <span>Gross Spend:</span>
                        <span>€{row.spendB.toFixed(2)}B</span>
                      </div>
                      <div className="chart-tooltip-row">
                        <span>Cohort Coverage:</span>
                        <span>{row.coveragePct.toFixed(1)}%</span>
                      </div>
                      <div className="chart-tooltip-row">
                        <span>Paid Transfers:</span>
                        <span>{formatInteger(row.paidTransfers)}</span>
                      </div>
                    </div>
                  );
                }}
              />
              <Bar yAxisId="left" dataKey="spendB" name="Gross Spend (€B)" fill="#10b981" radius={[5, 5, 0, 0]} />
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="coveragePct"
                name="Active Player Coverage (%)"
                stroke="#38bdf8"
                strokeWidth={2.5}
                dot={{ r: 3.5 }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </ChartCard>

      <WarningBanner tone="warning" title="Historical Coverage & Dataset Caveats">
        <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
          {overview.caveats.map((c) => (
            <li key={c} style={{ marginBottom: 4 }}>{c}</li>
          ))}
        </ul>
      </WarningBanner>
    </div>
  );
}
