import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import type {
  HealthResponse,
  HistoricalTrendsResponse,
  OverviewResponse,
} from '../types/api';
import { formatEurCompact, formatInteger } from '../utils/formatters';
import { ChartCard } from '../components/common/ChartCard';
import { ErrorState, LoadingState, WarningBanner } from '../components/common/StatePanel';

interface MethodData {
  health: HealthResponse;
  overview: OverviewResponse;
  trends: HistoricalTrendsResponse;
}

const METRIC_DEFINITIONS = [
  {
    metric: 'Points Per Game (PPG)',
    formula: '(Wins × 3 + Draws) ÷ Matches Played',
    rationale:
      'Normalizes domestic and UCL table performance across 34-game leagues (Bundesliga, Ligue 1 2023+), 38-game leagues (EPL, LaLiga, Serie A), and shortened 2019/20 seasons.',
  },
  {
    metric: 'Normalized Position (pos_pct)',
    formula: '(N_teams − League Position) ÷ (N_teams − 1)',
    rationale: 'Maps league finish to [0.0 = last, 1.0 = champion] across 18- and 20-team divisions.',
  },
  {
    metric: 'Season Alignment',
    formula: "transfer_season '22/23' → games.season = 2022",
    rationale:
      'Matches clubs via actual season competition participation in games rather than static clubs.domestic_competition_id.',
  },
  {
    metric: 'UCL Stage Numeric (ucl_stage_num)',
    formula: 'Group=1.0, Knockout Playoff=1.5, R16=2.0, QF=3.0, SF=4.0, Final=5.0',
    rationale: 'Accounts for the 2024/25+ Champions League League-Phase Knockout Playoff round.',
  },
  {
    metric: 'Est. Market Value Gain & Multiple',
    formula: 'MV_spell − Transfer_Fee; MV_spell ÷ Transfer_Fee',
    rationale:
      'Strictly bounded to player_valuations within [transfer_date, next_transfer_date). Estimates paper squad valuation movement, not realized cash ROI.',
  },
];

export function MethodologySection() {
  const [data, setData] = useState<MethodData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      const [health, overview, trends] = await Promise.all([
        api.getHealth(signal),
        api.getOverview(signal),
        api.getTrends({ limit: 10 }, signal),
      ]);
      setData({ health, overview, trends });
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

  if (loading) return <LoadingState message="Loading methodology and DuckDB table metadata..." />;
  if (error || !data) return <ErrorState message={error ?? 'Failed to load'} onRetry={() => void load()} />;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <WarningBanner tone="danger" title="Mandatory Interpretation Safeguards">
        {data.overview.methodology_disclaimer}
      </WarningBanner>

      <div className="chart-grid-2">
        <ChartCard
          title="Dataset Source & Live DuckDB Snapshot"
          subtitle="transfermarkt-datasets loaded into footintel.duckdb"
        >
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6, marginTop: 0 }}>
            All figures are computed from the local DuckDB warehouse built from{' '}
            <code style={{ color: 'var(--accent-bright)' }}>dcaribou/transfermarkt-datasets</code> across
            seasons <strong>{data.overview.kpis.analysis_window}</strong> (Europe&apos;s Big 5 leagues + UEFA
            Champions League).
          </p>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>DuckDB Table</th>
                  <th className="num">Live Row Count</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(data.health.tables).map(([table, cnt]) => (
                  <tr key={table}>
                    <td><code style={{ fontFamily: 'var(--font-mono)' }}>{table}</code></td>
                    <td className="num">{formatInteger(cnt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </ChartCard>

        <ChartCard
          title="Key Limitations & Biases"
          subtitle="Structural constraints inherent to public transfer market data"
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {[
              {
                title: '1. Pre-2022 Survivorship / Cohort Attrition',
                text: `${data.trends.coverage_warning.summary} ${data.trends.coverage_warning.implication}`,
              },
              {
                title: '2. Non-Causal Observational Inference',
                text: 'Omitted variables (wage bills, commercial revenue, academy output) and reverse causality (UCL prize money funding transfers) drive cross-sectional R² (20.8%), while Two-Way FE within-R² is <0.5%.',
              },
              {
                title: '3. Market Value Estimation vs Financial ROI',
                text: 'Transfermarkt valuations are crowd-sourced player appraisals, not actual sale fees or accounting profits after wages, agent fees, and contract amortization.',
              },
              {
                title: '4. Undisclosed, Loan & Free Transfers',
                text: 'transfer_fee = 0 or NULL blends free transfers, loans, and undisclosed fees; 19 of 456 UCL club-seasons also lack metadata in clubs.',
              },
            ].map((item) => (
              <div
                key={item.title}
                style={{
                  padding: '10px 12px',
                  borderRadius: 10,
                  background: 'var(--bg-card-elevated)',
                  border: '1px solid var(--border-subtle)',
                }}
              >
                <strong style={{ fontSize: 13 }}>{item.title}</strong>
                <p style={{ margin: '4px 0 0', fontSize: 12.5, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                  {item.text}
                </p>
              </div>
            ))}
          </div>
        </ChartCard>
      </div>

      <ChartCard
        title="Metric Definitions"
        subtitle="Standardized formulas enforced consistently across SQL, SciPy, and FastAPI"
      >
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Metric</th>
                <th>Formula / Rule</th>
                <th>Methodological Rationale</th>
              </tr>
            </thead>
            <tbody>
              {METRIC_DEFINITIONS.map((m) => (
                <tr key={m.metric}>
                  <td><strong>{m.metric}</strong></td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12, whiteSpace: 'normal' }}>{m.formula}</td>
                  <td style={{ whiteSpace: 'normal', color: 'var(--text-secondary)' }}>{m.rationale}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </ChartCard>

      <ChartCard
        title="Historical Player-Cohort Coverage Audit (2012/13–2025/26)"
        subtitle="Live season-by-season audit of active Top-5 matchday players present in transfers"
      >
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Season</th>
                <th className="num">Top-5 Spend</th>
                <th className="num">Paid Deals</th>
                <th className="num">Active Top-5 Players</th>
                <th className="num">Covered in Transfers</th>
                <th className="num">Coverage %</th>
              </tr>
            </thead>
            <tbody>
              {data.trends.aggregate.map((row) => (
                <tr key={row.game_season}>
                  <td><strong>{row.transfer_season}</strong></td>
                  <td className="num">{formatEurCompact(row.total_spending)}</td>
                  <td className="num">{formatInteger(row.paid_transfers)}</td>
                  <td className="num">{formatInteger(row.active_top5_players)}</td>
                  <td className="num">{formatInteger(row.covered_top5_players)}</td>
                  <td className="num">
                    <span className={`tag-pill ${row.pct_active_players_covered >= 85 ? 'tag-green' : 'tag-amber'}`}>
                      {row.pct_active_players_covered.toFixed(1)}%
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </ChartCard>
    </div>
  );
}
