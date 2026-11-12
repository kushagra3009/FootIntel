import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { api } from '../api/client';
import type { StatisticalResultsResponse } from '../types/api';
import { formatPercent, formatPValue } from '../utils/formatters';
import { ChartCard } from '../components/common/ChartCard';
import { KpiCard } from '../components/common/KpiCard';
import { ErrorState, LoadingState, WarningBanner } from '../components/common/StatePanel';

type StatsTab = 'all' | 'domestic' | 'ucl' | 'value' | 'robustness';

export function StatisticalInsightsSection() {
  const [tab, setTab] = useState<StatsTab>('all');
  const [data, setData] = useState<StatisticalResultsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getStatistics('all', signal);
      setData(res);
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

  const modelRows = useMemo(() => {
    if (!data) return [];
    const sr = data.statistical_results;
    const comp = data.domestic_vs_ucl_comparison;
    const s6a = sr['6A_domestic_spend_vs_performance'];
    const s6b = sr['6B_net_spend_vs_performance'];
    const s6d = sr['6D_ucl_spend_vs_performance'];
    const s6e = sr['6E_fee_vs_mv'];
    const s6f = sr['6F_robustness'];
    if (!s6a || !s6b || !s6d || !s6e || !s6f) return [];

    return [
      {
        group: 'domestic',
        model: '6A: Pooled OLS (ln Gross Spend → PPG)',
        n: `${s6a.ols_log_spend_m_to_ppg.n} (${s6a.ols_log_spend_m_to_ppg.clusters} clubs)`,
        corr: `r=${s6a.pearson_r_log_vs_ppg.toFixed(4)} / ρ=${s6a.spearman_rho_spend_vs_ppg.toFixed(4)}`,
        slope: s6a.ols_log_spend_m_to_ppg.slope.toFixed(4),
        r2: s6a.ols_log_spend_m_to_ppg.r_squared ?? 0,
        pVal: formatPValue(s6a.ols_log_spend_m_to_ppg.cluster_p),
        ci: s6a.ols_log_spend_m_to_ppg.cluster_95ci
          ? `[${s6a.ols_log_spend_m_to_ppg.cluster_95ci[0].toFixed(4)}, ${s6a.ols_log_spend_m_to_ppg.cluster_95ci[1].toFixed(4)}]`
          : '—',
      },
      {
        group: 'domestic',
        model: '6A: Full-Sample asinh(Spend €M) → PPG',
        n: `${s6a.full_sample_asinh_ols_ppg.n} (${s6a.full_sample_asinh_ols_ppg.clusters} clubs)`,
        corr: `ρ=${s6a.full_sample_spearman_rho_ppg.toFixed(4)}`,
        slope: s6a.full_sample_asinh_ols_ppg.slope.toFixed(4),
        r2: s6a.full_sample_asinh_ols_ppg.r_squared ?? 0,
        pVal: formatPValue(s6a.full_sample_asinh_ols_ppg.cluster_p),
        ci: s6a.full_sample_asinh_ols_ppg.cluster_95ci
          ? `[${s6a.full_sample_asinh_ols_ppg.cluster_95ci[0].toFixed(4)}, ${s6a.full_sample_asinh_ols_ppg.cluster_95ci[1].toFixed(4)}]`
          : '—',
      },
      {
        group: 'domestic',
        model: '6B: Net Spend (€M) → PPG',
        n: `${s6b.ols_net_spend_m_to_ppg.n} (${s6b.ols_net_spend_m_to_ppg.clusters} clubs)`,
        corr: `r=${s6b.pearson_r_ppg.toFixed(4)} / ρ=${s6b.spearman_rho_ppg.toFixed(4)}`,
        slope: s6b.ols_net_spend_m_to_ppg.slope.toFixed(5),
        r2: s6b.ols_net_spend_m_to_ppg.r_squared ?? 0,
        pVal: formatPValue(s6b.ols_net_spend_m_to_ppg.cluster_p),
        ci: s6b.ols_net_spend_m_to_ppg.cluster_95ci
          ? `[${s6b.ols_net_spend_m_to_ppg.cluster_95ci[0].toFixed(5)}, ${s6b.ols_net_spend_m_to_ppg.cluster_95ci[1].toFixed(5)}]`
          : '—',
      },
      {
        group: 'ucl',
        model: '6D: All UCL Spenders (ln Spend → UCL PPG)',
        n: `${s6d.all_ucl_spenders.n} (${s6d.all_ucl_spenders.clusters} clubs)`,
        corr: `r=${s6d.all_ucl_spenders.ucl_ppg_pearson_r.toFixed(4)}`,
        slope: s6d.all_ucl_spenders.ucl_ppg_ols.slope.toFixed(4),
        r2: s6d.all_ucl_spenders.ucl_ppg_ols.r_squared ?? 0,
        pVal: formatPValue(s6d.all_ucl_spenders.ucl_ppg_ols.cluster_p),
        ci: s6d.all_ucl_spenders.ucl_ppg_ols.cluster_95ci
          ? `[${s6d.all_ucl_spenders.ucl_ppg_ols.cluster_95ci[0].toFixed(4)}, ${s6d.all_ucl_spenders.ucl_ppg_ols.cluster_95ci[1].toFixed(4)}]`
          : '—',
      },
      {
        group: 'ucl',
        model: '6D: Top-5 UCL Spenders (ln Spend → UCL PPG)',
        n: `${s6d.top5_ucl_spenders.n} (${s6d.top5_ucl_spenders.clusters} clubs)`,
        corr: `r=${s6d.top5_ucl_spenders.ucl_ppg_pearson_r.toFixed(4)} (Dom r=${comp?.spenders_domestic_ppg_r.toFixed(4) ?? '—'})`,
        slope: s6d.top5_ucl_spenders.ucl_ppg_ols.slope.toFixed(4),
        r2: s6d.top5_ucl_spenders.ucl_ppg_ols.r_squared ?? 0,
        pVal: formatPValue(s6d.top5_ucl_spenders.ucl_ppg_ols.cluster_p),
        ci: s6d.top5_ucl_spenders.ucl_ppg_ols.cluster_95ci
          ? `[${s6d.top5_ucl_spenders.ucl_ppg_ols.cluster_95ci[0].toFixed(4)}, ${s6d.top5_ucl_spenders.ucl_ppg_ols.cluster_95ci[1].toFixed(4)}]`
          : '—',
      },
      {
        group: 'value',
        model: '6E: Log-Log OLS (ln MV → ln Fee)',
        n: `${s6e.n} (${s6e.ols_log_mv_to_log_fee.clusters} clubs)`,
        corr: `r=${s6e.pearson_r_log_log.toFixed(4)} / ρ=${s6e.spearman_rho.toFixed(4)}`,
        slope: s6e.ols_log_mv_to_log_fee.slope.toFixed(4),
        r2: s6e.ols_log_mv_to_log_fee.r_squared ?? 0,
        pVal: formatPValue(s6e.ols_log_mv_to_log_fee.cluster_p),
        ci: s6e.ols_log_mv_to_log_fee.cluster_95ci
          ? `[${s6e.ols_log_mv_to_log_fee.cluster_95ci[0].toFixed(4)}, ${s6e.ols_log_mv_to_log_fee.cluster_95ci[1].toFixed(4)}]`
          : '—',
      },
      {
        group: 'robustness',
        model: '6F: Season Fixed Effects (PPG)',
        n: `${s6f.season_fixed_effects_ppg.n} (${s6f.season_fixed_effects_ppg.clusters} clubs)`,
        corr: 'Season demeaned',
        slope: s6f.season_fixed_effects_ppg.slope.toFixed(4),
        r2: s6f.season_fixed_effects_ppg.r_squared ?? 0,
        pVal: formatPValue(s6f.season_fixed_effects_ppg.cluster_p),
        ci: s6f.season_fixed_effects_ppg.cluster_95ci
          ? `[${s6f.season_fixed_effects_ppg.cluster_95ci[0].toFixed(4)}, ${s6f.season_fixed_effects_ppg.cluster_95ci[1].toFixed(4)}]`
          : '—',
      },
      {
        group: 'robustness',
        model: '6F: Club-Averaged Cross-Section',
        n: `${s6f.club_averaged_cross_section.n_clubs} unique clubs`,
        corr: `r=${s6f.club_averaged_cross_section.pearson_r.toFixed(4)}`,
        slope: s6f.club_averaged_cross_section.slope.toFixed(4),
        r2: s6f.club_averaged_cross_section.r_squared,
        pVal: formatPValue(s6f.club_averaged_cross_section.p_value),
        ci: `[${s6f.club_averaged_cross_section.ci_95[0].toFixed(4)}, ${s6f.club_averaged_cross_section.ci_95[1].toFixed(4)}]`,
      },
      {
        group: 'robustness',
        model: '6F: Club Fixed Effects (Within-Club)',
        n: `${s6f.club_fixed_effects_ppg.n} (${s6f.club_fixed_effects_ppg.clusters} clubs)`,
        corr: 'Club demeaned',
        slope: s6f.club_fixed_effects_ppg.slope.toFixed(4),
        r2: s6f.club_fixed_effects_ppg.r_squared ?? 0,
        pVal: formatPValue(s6f.club_fixed_effects_ppg.cluster_p),
        ci: s6f.club_fixed_effects_ppg.cluster_95ci
          ? `[${s6f.club_fixed_effects_ppg.cluster_95ci[0].toFixed(4)}, ${s6f.club_fixed_effects_ppg.cluster_95ci[1].toFixed(4)}]`
          : '—',
      },
      {
        group: 'robustness',
        model: '6F: Two-Way Fixed Effects (Club + Season)',
        n: `${s6f.two_way_fixed_effects_ppg.n} (${s6f.two_way_fixed_effects_ppg.clusters} clubs)`,
        corr: 'Two-way demeaned',
        slope: s6f.two_way_fixed_effects_ppg.slope.toFixed(4),
        r2: s6f.two_way_fixed_effects_ppg.within_r_squared ?? 0,
        pVal: formatPValue(s6f.two_way_fixed_effects_ppg.cluster_p),
        ci: '—',
      },
      {
        group: 'robustness',
        model: '6F: High-Coverage Sub-Period (2022–2025)',
        n: `${s6f.subperiod_2022_2025.n} (${s6f.subperiod_2022_2025.clusters} clubs)`,
        corr: 'Near-complete cohort',
        slope: s6f.subperiod_2022_2025.slope.toFixed(4),
        r2: s6f.subperiod_2022_2025.r_squared ?? 0,
        pVal: formatPValue(s6f.subperiod_2022_2025.cluster_p),
        ci: s6f.subperiod_2022_2025.cluster_95ci
          ? `[${s6f.subperiod_2022_2025.cluster_95ci[0].toFixed(4)}, ${s6f.subperiod_2022_2025.cluster_95ci[1].toFixed(4)}]`
          : '—',
      },
    ];
  }, [data]);

  const feComparisonData = useMemo(() => {
    const s6a = data?.statistical_results['6A_domestic_spend_vs_performance'];
    const s6f = data?.statistical_results['6F_robustness'];
    if (!s6a || !s6f) return [];
    return [
      { label: 'Club-Averaged', r2Pct: Number((s6f.club_averaged_cross_section.r_squared * 100).toFixed(2)), color: '#38bdf8' },
      { label: 'Season FE', r2Pct: Number(((s6f.season_fixed_effects_ppg.r_squared ?? 0) * 100).toFixed(2)), color: '#10b981' },
      { label: '2018–2025', r2Pct: Number(((s6f.subperiod_2018_2025.r_squared ?? 0) * 100).toFixed(2)), color: '#10b981' },
      { label: '2022–2025', r2Pct: Number(((s6f.subperiod_2022_2025.r_squared ?? 0) * 100).toFixed(2)), color: '#10b981' },
      { label: 'Pooled Log OLS', r2Pct: Number(((s6a.ols_log_spend_m_to_ppg.r_squared ?? 0) * 100).toFixed(2)), color: '#a78bfa' },
      { label: 'Linear Spend', r2Pct: Number(((s6f.linear_spend_ols_ppg.r_squared ?? 0) * 100).toFixed(2)), color: '#f59e0b' },
      { label: 'Two-Way FE (Within)', r2Pct: Number(((s6f.two_way_fixed_effects_ppg.within_r_squared ?? 0) * 100).toFixed(2)), color: '#f43f5e' },
      { label: 'Club FE (Within)', r2Pct: Number(((s6f.club_fixed_effects_ppg.r_squared ?? 0) * 100).toFixed(2)), color: '#f43f5e' },
    ];
  }, [data]);

  const visibleRows = tab === 'all' ? modelRows : modelRows.filter((r) => r.group === tab);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {loading && <LoadingState message="Loading statistical battery..." />}
      {!loading && error && <ErrorState message={error} onRetry={() => void load()} />}
      {!loading && !error && data && data.statistical_results['6F_robustness'] && (
        <>
          <WarningBanner tone="info" title="Pooled R² (0.2076) vs Two-Way Fixed Effects Within-R² (0.0047)">
            {data.methodology_note}
          </WarningBanner>

          <div className="kpi-grid">
            <KpiCard
              label="Club-Averaged Cross-Section"
              value={formatPercent(data.statistical_results['6F_robustness'].club_averaged_cross_section.r_squared * 100, 2)}
              sublabel={`r = ${data.statistical_results['6F_robustness'].club_averaged_cross_section.pearson_r.toFixed(4)} across 166 clubs`}
              badge="Between-Club Tier"
              badgeTone="sky"
            />
            <KpiCard
              label="Two-Way FE Within-R²"
              value={formatPercent((data.statistical_results['6F_robustness'].two_way_fixed_effects_ppg.within_r_squared ?? 0) * 100, 2)}
              sublabel={`Slope=${data.statistical_results['6F_robustness'].two_way_fixed_effects_ppg.slope.toFixed(4)}, p=${formatPValue(data.statistical_results['6F_robustness'].two_way_fixed_effects_ppg.cluster_p)}`}
              badge="Within-Club Change"
              badgeTone="rose"
            />
            <KpiCard
              label="Heteroscedasticity Check"
              value={data.statistical_results['6F_robustness'].heteroscedasticity_detected ? 'Detected' : 'None'}
              sublabel={`Breusch-Pagan p = ${formatPValue(data.statistical_results['6F_robustness'].heteroscedasticity_test_p)}`}
              badge="Clustered SEs Used"
              badgeTone="amber"
            />
            <KpiCard
              label="Repeated Club Clusters"
              value={`${data.statistical_results['6F_robustness'].avg_obs_per_club} avg`}
              sublabel={`Max ${data.statistical_results['6F_robustness'].max_obs_per_club} seasons/club (${data.statistical_results['6F_robustness'].unique_clubs} clubs)`}
            />
          </div>

          <ChartCard
            title="Explained Variance (R² / Within-R²) Across Econometric Specifications"
            subtitle="Between-club models (blue/green) vs within-club single-season fixed effects (rose)"
            note="Comparing Pooled OLS (20.76%) and Club-Averaged (38.61%) against Two-Way FE (0.47%) demonstrates why annual transfer spending cannot be treated as an instant causal lever."
          >
            <div style={{ width: '100%', height: 290 }}>
              <ResponsiveContainer>
                <BarChart data={feComparisonData} margin={{ top: 10, right: 18, left: 0, bottom: 20 }}>
                  <CartesianGrid stroke="rgba(148,163,184,0.12)" strokeDasharray="3 3" />
                  <XAxis dataKey="label" stroke="#94a3b8" fontSize={11.5} interval={0} angle={-12} textAnchor="end" />
                  <YAxis stroke="#94a3b8" fontSize={12} unit="%" />
                  <Tooltip
                    contentStyle={{
                      background: 'rgba(10,16,26,0.96)',
                      border: '1px solid rgba(148,163,184,0.25)',
                      borderRadius: 10,
                      fontSize: 12,
                    }}
                  />
                  <Bar dataKey="r2Pct" name="R² (%)" radius={[6, 6, 0, 0]}>
                    {feComparisonData.map((d) => (
                      <Cell key={d.label} fill={d.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </ChartCard>

          <ChartCard
            title="Complete Statistical Results Matrix"
            subtitle="Pearson r, Spearman ρ, OLS slopes, R², club-clustered p-values, and 95% confidence intervals"
            actions={
              <div className="seg-group" role="tablist" aria-label="Filter statistical models">
                {(
                  [
                    ['all', 'All'],
                    ['domestic', 'Domestic'],
                    ['ucl', 'UCL'],
                    ['value', 'Market Value'],
                    ['robustness', 'Robustness & FE'],
                  ] as const
                ).map(([id, label]) => (
                  <button
                    key={id}
                    type="button"
                    role="tab"
                    aria-selected={tab === id}
                    className={`seg-btn ${tab === id ? 'active' : ''}`}
                    onClick={() => setTab(id)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            }
          >
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Model / Test</th>
                    <th>Sample (n / Clusters)</th>
                    <th>Correlation</th>
                    <th className="num">Slope</th>
                    <th className="num">R² / Within-R²</th>
                    <th className="num">Cluster p</th>
                    <th className="num">Cluster 95% CI</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleRows.map((row) => (
                    <tr key={row.model}>
                      <td><strong>{row.model}</strong></td>
                      <td>{row.n}</td>
                      <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{row.corr}</td>
                      <td className="num">{row.slope}</td>
                      <td className="num">{formatPercent(row.r2 * 100, 2)}</td>
                      <td className="num">{row.pVal}</td>
                      <td className="num">{row.ci}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </ChartCard>
        </>
      )}
    </div>
  );
}
