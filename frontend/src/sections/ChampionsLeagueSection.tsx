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
  PairedDomesticUCLRow,
  UCLClubSeasonRow,
  UCLPerformanceResponse,
} from '../types/api';
import {
  formatEurMillions,
  formatInteger,
  formatPercent,
  formatPValue,
} from '../utils/formatters';
import { ChartCard } from '../components/common/ChartCard';
import { KpiCard } from '../components/common/KpiCard';
import { EmptyState, ErrorState, LoadingState } from '../components/common/StatePanel';

const SEASONS = Array.from({ length: 14 }, (_, i) => 2012 + i);
const STAGES = [
  'Group / League Phase',
  'Knockout Playoff',
  'Round of 16',
  'Quarter-Finals',
  'Semi-Finals',
  'Final',
];

export function ChampionsLeagueSection() {
  const [season, setSeason] = useState<string>('');
  const [top5Filter, setTop5Filter] = useState<'all' | 'true' | 'false'>('all');
  const [stage, setStage] = useState<string>('');
  const [clubQuery, setClubQuery] = useState<string>('');

  const [uclData, setUclData] = useState<UCLPerformanceResponse | null>(null);
  const [pairedRows, setPairedRows] = useState<PairedDomesticUCLRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      const isTop5Param = top5Filter === 'all' ? undefined : top5Filter === 'true';
      const [uclRes, pairedRes] = await Promise.all([
        api.getUcl(
          {
            season: season ? Number(season) : undefined,
            is_top5: isTop5Param,
            ucl_stage: stage || undefined,
            club_name: clubQuery.trim() || undefined,
            sort_by: 'ucl_ppg',
            sort_order: 'desc',
            limit: 500,
            offset: 0,
          },
          signal,
        ),
        api.getUclPaired(
          {
            season: season ? Number(season) : undefined,
            club_name: clubQuery.trim() || undefined,
            positive_spend_only: true,
            limit: 300,
            offset: 0,
          },
          signal,
        ),
      ]);
      setUclData(uclRes);
      setPairedRows(pairedRes.observations);
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        setError((err as Error).message);
      }
    } finally {
      setLoading(false);
    }
  }, [season, top5Filter, stage, clubQuery]);

  useEffect(() => {
    const ctrl = new AbortController();
    const t = setTimeout(() => void load(ctrl.signal), 180);
    return () => {
      clearTimeout(t);
      ctrl.abort();
    };
  }, [load]);

  const scatterUcl = useMemo(
    () =>
      (uclData?.observations ?? [])
        .filter((r) => r.gross_spend_m > 0)
        .map((r: UCLClubSeasonRow) => ({
          ...r,
          logSpendM: Math.log(r.gross_spend_m),
          winRatePct: Number(((r.ucl_wins / Math.max(r.ucl_matches, 1)) * 100).toFixed(1)),
        })),
    [uclData],
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div className="filter-bar" role="region" aria-label="Champions League filters">
        <div className="filter-field">
          <label className="filter-label" htmlFor="ucl-season">Season</label>
          <select
            id="ucl-season"
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

        <div className="filter-field">
          <label className="filter-label" htmlFor="ucl-pool">Club Pool</label>
          <select
            id="ucl-pool"
            className="control-select"
            value={top5Filter}
            onChange={(e) => setTop5Filter(e.target.value as 'all' | 'true' | 'false')}
          >
            <option value="all">All UCL Participants</option>
            <option value="true">Top-5 League Clubs Only</option>
            <option value="false">Non-Top-5 Clubs Only</option>
          </select>
        </div>

        <div className="filter-field">
          <label className="filter-label" htmlFor="ucl-stage">UCL Stage</label>
          <select
            id="ucl-stage"
            className="control-select"
            value={stage}
            onChange={(e) => setStage(e.target.value)}
          >
            <option value="">All Stages</option>
            {STAGES.map((st) => (
              <option key={st} value={st}>{st}</option>
            ))}
          </select>
        </div>

        <div className="filter-field" style={{ flex: '1 1 200px' }}>
          <label className="filter-label" htmlFor="ucl-club">Search Club</label>
          <input
            id="ucl-club"
            type="text"
            className="control-input"
            placeholder="e.g. Real Madrid, Bayern, Porto..."
            value={clubQuery}
            onChange={(e) => setClubQuery(e.target.value)}
          />
        </div>
      </div>

      {loading && <LoadingState message="Loading UEFA Champions League analytics..." />}
      {!loading && error && <ErrorState message={error} onRetry={() => void load()} />}
      {!loading && !error && uclData && (
        <>
          <div className="kpi-grid">
            <KpiCard
              label="All UCL Spenders (UCL PPG r)"
              value={uclData.statistical_summary.all_ucl_spenders.ucl_ppg_pearson_r.toFixed(4)}
              sublabel={`R² = ${formatPercent(uclData.statistical_summary.all_ucl_spenders.ucl_ppg_ols.r_squared! * 100, 1)} • n=${uclData.statistical_summary.all_ucl_spenders.n}`}
              badge={`p=${formatPValue(uclData.statistical_summary.all_ucl_spenders.ucl_ppg_ols.cluster_p)}`}
            />
            <KpiCard
              label="All UCL Stage Correlation (ρ)"
              value={uclData.statistical_summary.all_ucl_spenders.stage_spearman_rho.toFixed(4)}
              sublabel={`Stage R² = ${formatPercent(uclData.statistical_summary.all_ucl_spenders.stage_ols.r_squared! * 100, 1)}`}
              badgeTone="sky"
            />
            <KpiCard
              label="Top-5 Subset UCL PPG r"
              value={uclData.statistical_summary.top5_ucl_spenders.ucl_ppg_pearson_r.toFixed(4)}
              sublabel={`Range-restricted n=${uclData.statistical_summary.top5_ucl_spenders.n} (${uclData.statistical_summary.top5_ucl_spenders.clusters} clubs)`}
              badge={`vs Dom r=${uclData.domestic_vs_ucl_comparison.spenders_domestic_ppg_r.toFixed(3)}`}
              badgeTone="amber"
            />
            <KpiCard
              label="Steiger z (Dom PPG vs UCL PPG)"
              value={uclData.domestic_vs_ucl_comparison.steiger_z_dom_ppg_vs_ucl_ppg.toFixed(3)}
              sublabel={`Paired n=${uclData.domestic_vs_ucl_comparison.n_paired_spenders} spenders`}
              badge={`p=${formatPValue(uclData.domestic_vs_ucl_comparison.steiger_p_dom_ppg_vs_ucl_ppg)}`}
              badgeTone="green"
            />
          </div>

          <div className="chart-grid-2">
            <ChartCard
              title="UCL Spending vs UCL Points Per Game"
              subtitle={`Green = Top-5 clubs, Sky = Non-Top-5 clubs (${scatterUcl.length} positive-spend rows)`}
              note={uclData.methodology_note}
            >
              {scatterUcl.length === 0 ? (
                <EmptyState />
              ) : (
                <div style={{ width: '100%', height: 310 }}>
                  <ResponsiveContainer>
                    <ScatterChart margin={{ top: 10, right: 16, left: 0, bottom: 8 }}>
                      <CartesianGrid stroke="rgba(148,163,184,0.12)" strokeDasharray="3 3" />
                      <XAxis
                        type="number"
                        dataKey="logSpendM"
                        stroke="#94a3b8"
                        fontSize={12}
                        tickFormatter={(v: number) => `€${Math.exp(v).toFixed(0)}M`}
                      />
                      <YAxis type="number" dataKey="ucl_ppg" stroke="#94a3b8" fontSize={12} domain={[0, 3.05]} />
                      <Tooltip
                        content={({ active, payload }) => {
                          if (!active || !payload?.length) return null;
                          const r = payload[0].payload as (typeof scatterUcl)[number];
                          return (
                            <div className="chart-tooltip">
                              <div className="chart-tooltip-title">{r.name} ({r.transfer_season})</div>
                              <div className="chart-tooltip-row"><span>Stage:</span><span>{r.ucl_stage}</span></div>
                              <div className="chart-tooltip-row"><span>UCL PPG:</span><span>{r.ucl_ppg.toFixed(3)}</span></div>
                              <div className="chart-tooltip-row"><span>UCL Win %:</span><span>{r.winRatePct.toFixed(1)}% ({r.ucl_wins}/{r.ucl_matches})</span></div>
                              <div className="chart-tooltip-row"><span>Gross Spend:</span><span>{formatEurMillions(r.gross_spend_m)}</span></div>
                            </div>
                          );
                        }}
                      />
                      <Scatter data={scatterUcl} fillOpacity={0.75}>
                        {scatterUcl.map((entry) => (
                          <Cell key={`${entry.club_id}-${entry.season}`} fill={entry.is_top5 ? '#10b981' : '#38bdf8'} />
                        ))}
                      </Scatter>
                    </ScatterChart>
                  </ResponsiveContainer>
                </div>
              )}
            </ChartCard>

            <ChartCard
              title="UCL Stage Distribution (Filtered Pool)"
              subtitle="Elimination / peak round reached across filtered club-seasons"
              note="Includes Knockout Playoff (2024+ intermediate stage, coded as 1.5)."
            >
              {uclData.stage_distribution.length === 0 ? (
                <EmptyState />
              ) : (
                <div style={{ width: '100%', height: 310 }}>
                  <ResponsiveContainer>
                    <BarChart
                      data={uclData.stage_distribution}
                      margin={{ top: 10, right: 16, left: 0, bottom: 20 }}
                    >
                      <CartesianGrid stroke="rgba(148,163,184,0.12)" strokeDasharray="3 3" />
                      <XAxis dataKey="ucl_stage" stroke="#94a3b8" fontSize={11} interval={0} angle={-15} textAnchor="end" />
                      <YAxis stroke="#94a3b8" fontSize={12} />
                      <Tooltip
                        contentStyle={{
                          background: 'rgba(10,16,26,0.96)',
                          border: '1px solid rgba(148,163,184,0.25)',
                          borderRadius: 10,
                          fontSize: 12,
                        }}
                      />
                      <Bar dataKey="count" name="Club-Seasons" fill="#10b981" radius={[6, 6, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </ChartCard>
          </div>

          <div className="chart-grid-2">
            <ChartCard
              title="Domestic PPG vs UCL PPG (Paired Top-5 Qualifiers)"
              subtitle={`Same ${pairedRows.length} positive-spend club-seasons plotted in domestic league vs UCL`}
              note={`Steiger test (Dom PPG vs UCL Stage): z=${uclData.domestic_vs_ucl_comparison.steiger_z_dom_ppg_vs_ucl_stage.toFixed(2)}, p=${formatPValue(uclData.domestic_vs_ucl_comparison.steiger_p_dom_ppg_vs_ucl_stage)}; Dom PPG vs UCL PPG: z=${uclData.domestic_vs_ucl_comparison.steiger_z_dom_ppg_vs_ucl_ppg.toFixed(2)}, p=${formatPValue(uclData.domestic_vs_ucl_comparison.steiger_p_dom_ppg_vs_ucl_ppg)}.`}
            >
              {pairedRows.length === 0 ? (
                <EmptyState />
              ) : (
                <div style={{ width: '100%', height: 310 }}>
                  <ResponsiveContainer>
                    <ScatterChart margin={{ top: 10, right: 16, left: 0, bottom: 8 }}>
                      <CartesianGrid stroke="rgba(148,163,184,0.12)" strokeDasharray="3 3" />
                      <XAxis type="number" dataKey="ppg" name="Domestic PPG" stroke="#94a3b8" fontSize={12} domain={[1.0, 2.8]} />
                      <YAxis type="number" dataKey="ucl_ppg" name="UCL PPG" stroke="#94a3b8" fontSize={12} domain={[0, 3.05]} />
                      <Tooltip
                        content={({ active, payload }) => {
                          if (!active || !payload?.length) return null;
                          const r = payload[0].payload as PairedDomesticUCLRow;
                          return (
                            <div className="chart-tooltip">
                              <div className="chart-tooltip-title">{r.name} ({r.season})</div>
                              <div className="chart-tooltip-row"><span>Domestic PPG:</span><span>{r.ppg.toFixed(3)} (#{r.league_position})</span></div>
                              <div className="chart-tooltip-row"><span>UCL PPG:</span><span>{r.ucl_ppg.toFixed(3)} ({r.ucl_stage})</span></div>
                              <div className="chart-tooltip-row"><span>Gross Spend:</span><span>{formatEurMillions(r.gross_spend_m)}</span></div>
                            </div>
                          );
                        }}
                      />
                      <Scatter data={pairedRows} fill="#a78bfa" fillOpacity={0.75} />
                    </ScatterChart>
                  </ResponsiveContainer>
                </div>
              )}
            </ChartCard>

            <ChartCard
              title="UCL Club Comparison"
              subtitle={`Showing ${Math.min(uclData.observations.length, 60)} of ${formatInteger(uclData.pagination.total)} UCL club-seasons`}
            >
              {uclData.observations.length === 0 ? (
                <EmptyState />
              ) : (
                <div className="table-wrap" style={{ maxHeight: 330 }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Club</th>
                        <th>Season</th>
                        <th>Stage</th>
                        <th className="num">Matches</th>
                        <th className="num">Win %</th>
                        <th className="num">UCL PPG</th>
                        <th className="num">Gross Spend</th>
                      </tr>
                    </thead>
                    <tbody>
                      {uclData.observations.slice(0, 60).map((r) => (
                        <tr key={`${r.club_id}-${r.season}`}>
                          <td><strong>{r.name}</strong></td>
                          <td>{r.transfer_season}</td>
                          <td>{r.ucl_stage}</td>
                          <td className="num">{r.ucl_matches}</td>
                          <td className="num">{((r.ucl_wins / Math.max(r.ucl_matches, 1)) * 100).toFixed(1)}%</td>
                          <td className="num">{r.ucl_ppg.toFixed(3)}</td>
                          <td className="num">{formatEurMillions(r.gross_spend_m)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </ChartCard>
          </div>
        </>
      )}
    </div>
  );
}
