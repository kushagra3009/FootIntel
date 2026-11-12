import { useCallback, useEffect, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Repeat } from 'lucide-react';
import { api } from '../api/client';
import type { PlayerComparisonResponse, PlayerComparisonSide } from '../types/api';
import {
  formatDecimal,
  formatEurCompact,
  formatInteger,
  seasonLabel,
} from '../utils/formatters';
import { ChartCard } from '../components/common/ChartCard';
import { PlayerPicker } from '../components/common/PlayerPicker';
import { ErrorState, LoadingState, WarningBanner } from '../components/common/StatePanel';

interface PlayerComparisonSectionProps {
  initialPlayerId?: number | null;
}

function formatFeeCell(side: PlayerComparisonSide): string {
  const m = side.metrics;
  if (m.season_transfer_fee_status === 'paid' && m.season_transfer_fee_eur !== null) {
    return `${formatEurCompact(m.season_transfer_fee_eur)} (${m.season_transfer_description ?? ''})`;
  }
  if (m.season_transfer_fee_status === 'free_or_loan') {
    return `Free / Loan (€0) — ${m.season_transfer_description ?? ''}`;
  }
  if (m.season_transfer_fee_status === 'undisclosed') {
    return `Undisclosed — ${m.season_transfer_description ?? ''}`;
  }
  return m.season_transfer_description ?? 'No transfer in scope';
}

export function PlayerComparisonSection({ initialPlayerId }: PlayerComparisonSectionProps) {
  const [playerAId, setPlayerAId] = useState<number>(initialPlayerId ?? 342229);
  const [playerBId, setPlayerBId] = useState<number>(initialPlayerId === 418560 ? 342229 : 418560);
  const [seasonA, setSeasonA] = useState<number | undefined>(2023);
  const [seasonB, setSeasonB] = useState<number | undefined>(2023);

  const [data, setData] = useState<PlayerComparisonResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (initialPlayerId) {
      setPlayerAId(initialPlayerId);
      setSeasonA(undefined);
      if (initialPlayerId === playerBId) {
        setPlayerBId(initialPlayerId === 418560 ? 342229 : 418560);
      }
    }
  }, [initialPlayerId]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadComparison = useCallback(
    async (signal?: AbortSignal) => {
      setLoading(true);
      setError(null);
      try {
        const res = await api.comparePlayers(
          {
            player_a_id: playerAId,
            player_b_id: playerBId,
            season_a: seasonA,
            season_b: seasonB,
          },
          signal,
        );
        setData(res);
      } catch (err) {
        if ((err as Error).name === 'AbortError') return;
        setError((err as Error).message);
      } finally {
        setLoading(false);
      }
    },
    [playerAId, playerBId, seasonA, seasonB],
  );

  useEffect(() => {
    const ctrl = new AbortController();
    loadComparison(ctrl.signal);
    return () => ctrl.abort();
  }, [loadComparison]);

  const applySameSeason = () => {
    const shared =
      data?.player_a.available_seasons.find((s) =>
        data.player_b.available_seasons.includes(s),
      ) ?? 2023;
    setSeasonA(shared);
    setSeasonB(shared);
  };

  const applySelfCrossSeason = () => {
    const targetId = playerAId;
    setPlayerBId(targetId);
    const seasons = data?.player_a.available_seasons ?? [2024, 2023];
    setSeasonA(seasons[0] ?? 2024);
    setSeasonB(seasons[1] ?? seasons[0] ?? 2023);
  };

  const applyCareerMode = () => {
    setSeasonA(undefined);
    setSeasonB(undefined);
  };

  const labelA = data
    ? `${data.player_a.profile.name} (${data.player_a.metrics.selected_season_label})`
    : 'Selection A';
  const labelB = data
    ? `${data.player_b.profile.name} (${data.player_b.metrics.selected_season_label})`
    : 'Selection B';

  const outputBarData = data
    ? [
        {
          metric: 'Appearances',
          a: data.player_a.metrics.appearances,
          b: data.player_b.metrics.appearances,
        },
        {
          metric: 'Goals',
          a: data.player_a.metrics.goals,
          b: data.player_b.metrics.goals,
        },
        {
          metric: 'Assists',
          a: data.player_a.metrics.assists,
          b: data.player_b.metrics.assists,
        },
      ]
    : [];

  const financialBarData = data
    ? [
        {
          metric: 'Estimated MV',
          a: (data.player_a.metrics.market_value_in_eur ?? 0) / 1e6,
          b: (data.player_b.metrics.market_value_in_eur ?? 0) / 1e6,
        },
        {
          metric: 'Season Fee',
          a: (data.player_a.metrics.season_transfer_fee_eur ?? 0) / 1e6,
          b: (data.player_b.metrics.season_transfer_fee_eur ?? 0) / 1e6,
        },
        {
          metric: 'Latest Paid Fee',
          a: (data.player_a.metrics.latest_paid_transfer_fee_eur ?? 0) / 1e6,
          b: (data.player_b.metrics.latest_paid_transfer_fee_eur ?? 0) / 1e6,
        },
      ]
    : [];

  return (
    <>
      {/* Preset & Control Bar */}
      <div className="filter-bar" style={{ justifyContent: 'space-between' }}>
        <div className="seg-group" aria-label="Comparison preset modes">
          <button type="button" className="seg-btn" onClick={applySameSeason}>
            Same Season Pair
          </button>
          <button type="button" className="seg-btn" onClick={applySelfCrossSeason}>
            Same Player Across Seasons
          </button>
          <button type="button" className="seg-btn" onClick={applyCareerMode}>
            Full Career Totals
          </button>
        </div>

        <button
          type="button"
          className="btn"
          onClick={() => {
            setPlayerAId(playerBId);
            setPlayerBId(playerAId);
            setSeasonA(seasonB);
            setSeasonB(seasonA);
          }}
        >
          <Repeat size={14} aria-hidden="true" />
          Swap A ↔ B
        </button>
      </div>

      {/* Dual Player + Season Pickers */}
      <div className="chart-grid-2">
        <div className="card comparison-slot-card">
          <div className="comparison-slot-badge">
            <span className="tag-pill tag-green">Selection A</span>
            {data && (
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                {data.player_a.profile.position || 'Pos N/A'} •{' '}
                {data.player_a.profile.current_club_name || 'No Club'}
              </span>
            )}
          </div>
          <div className="comparison-slot-controls">
            <PlayerPicker
              label="Player A"
              selectedName={data?.player_a.profile.name}
              selectedMeta={
                data
                  ? `#${data.player_a.profile.player_id} • ${data.player_a.profile.country_of_citizenship ?? 'N/A'}`
                  : undefined
              }
              onSelect={(p) => {
                setPlayerAId(p.player_id);
              }}
            />
            <div className="filter-field">
              <label className="filter-label" htmlFor="compare-season-a">
                Season Scope (games.season)
              </label>
              <select
                id="compare-season-a"
                className="control-select"
                value={seasonA ?? ''}
                onChange={(e) =>
                  setSeasonA(e.target.value ? Number(e.target.value) : undefined)
                }
              >
                <option value="">Career (All Recorded Seasons)</option>
                {(data?.player_a.available_seasons ?? []).map((s) => (
                  <option key={s} value={s}>
                    {seasonLabel(s)} ({s})
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        <div className="card comparison-slot-card">
          <div className="comparison-slot-badge">
            <span className="tag-pill tag-sky">Selection B</span>
            {data && (
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                {data.player_b.profile.position || 'Pos N/A'} •{' '}
                {data.player_b.profile.current_club_name || 'No Club'}
              </span>
            )}
          </div>
          <div className="comparison-slot-controls">
            <PlayerPicker
              label="Player B"
              selectedName={data?.player_b.profile.name}
              selectedMeta={
                data
                  ? `#${data.player_b.profile.player_id} • ${data.player_b.profile.country_of_citizenship ?? 'N/A'}`
                  : undefined
              }
              onSelect={(p) => {
                setPlayerBId(p.player_id);
              }}
            />
            <div className="filter-field">
              <label className="filter-label" htmlFor="compare-season-b">
                Season Scope (games.season)
              </label>
              <select
                id="compare-season-b"
                className="control-select"
                value={seasonB ?? ''}
                onChange={(e) =>
                  setSeasonB(e.target.value ? Number(e.target.value) : undefined)
                }
              >
                <option value="">Career (All Recorded Seasons)</option>
                {(data?.player_b.available_seasons ?? []).map((s) => (
                  <option key={s} value={s}>
                    {seasonLabel(s)} ({s})
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>
      </div>

      {loading ? (
        <LoadingState message="Computing DuckDB player comparison..." />
      ) : error || !data ? (
        <ErrorState message={error || 'Unable to compare selections.'} onRetry={() => loadComparison()} />
      ) : (
        <>
          <WarningBanner tone="info" title={`Active Mode: ${data.comparison_mode.replace(/_/g, ' ')}`}>
            {data.season_boundary_definition}
          </WarningBanner>

          {/* Charts Row */}
          <div className="chart-grid-2">
            <ChartCard
              title="Normalized Profile Radar (6 Verified Metrics)"
              subtitle="Scaled 0–100 relative to the higher value across Selection A and Selection B"
              note={data.unavailable_metrics_note}
            >
              {!data.radar_supported ? (
                <WarningBanner title="Radar Chart Unavailable">
                  {data.radar_unavailable_reason}
                </WarningBanner>
              ) : (
                <ResponsiveContainer width="100%" height={310}>
                  <RadarChart data={data.radar_axes}>
                    <PolarGrid stroke="rgba(148,163,184,0.22)" />
                    <PolarAngleAxis dataKey="metric" stroke="#cbd5e1" fontSize={11.5} />
                    <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
                    <Radar
                      name={labelA}
                      dataKey="player_a_score"
                      stroke="#10b981"
                      fill="#10b981"
                      fillOpacity={0.28}
                    />
                    <Radar
                      name={labelB}
                      dataKey="player_b_score"
                      stroke="#38bdf8"
                      fill="#38bdf8"
                      fillOpacity={0.25}
                    />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Tooltip
                      content={({ active, payload }) => {
                        if (!active || !payload?.length) return null;
                        const row = payload[0].payload as PlayerComparisonResponse['radar_axes'][0];
                        return (
                          <div className="chart-tooltip">
                            <div className="chart-tooltip-title">{row.metric}</div>
                            <div className="chart-tooltip-row" style={{ color: '#34d399' }}>
                              <span>{labelA}:</span>
                              <strong>
                                {row.unit === 'ratio'
                                  ? formatDecimal(row.player_a_raw, 2)
                                  : formatInteger(row.player_a_raw)}
                              </strong>
                            </div>
                            <div className="chart-tooltip-row" style={{ color: '#38bdf8' }}>
                              <span>{labelB}:</span>
                              <strong>
                                {row.unit === 'ratio'
                                  ? formatDecimal(row.player_b_raw, 2)
                                  : formatInteger(row.player_b_raw)}
                              </strong>
                            </div>
                          </div>
                        );
                      }}
                    />
                  </RadarChart>
                </ResponsiveContainer>
              )}
            </ChartCard>

            <ChartCard
              title="Output & Estimated Valuation Side-by-Side"
              subtitle="Direct numeric comparison of observed appearances, goals, assists, and valuation (€M)"
              note={data.valuation_disclaimer}
            >
              <div className="comparison-dual-charts">
                <ResponsiveContainer width="100%" height={155}>
                  <BarChart data={outputBarData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.12)" />
                    <XAxis dataKey="metric" stroke="#94a3b8" fontSize={11} />
                    <YAxis stroke="#94a3b8" fontSize={11} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#0a101a',
                        borderColor: 'rgba(148,163,184,0.28)',
                        borderRadius: 10,
                        fontSize: 12,
                      }}
                    />
                    <Bar dataKey="a" name={labelA} fill="#10b981" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="b" name={labelB} fill="#38bdf8" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>

                <ResponsiveContainer width="100%" height={155}>
                  <BarChart data={financialBarData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.12)" />
                    <XAxis dataKey="metric" stroke="#94a3b8" fontSize={11} />
                    <YAxis stroke="#94a3b8" fontSize={11} tickFormatter={(v) => `€${v}M`} />
                    <Tooltip
                      formatter={(val: number) => [`€${val.toFixed(1)}M`, 'Amount']}
                      contentStyle={{
                        backgroundColor: '#0a101a',
                        borderColor: 'rgba(148,163,184,0.28)',
                        borderRadius: 10,
                        fontSize: 12,
                      }}
                    />
                    <Legend wrapperStyle={{ fontSize: 11.5 }} />
                    <Bar dataKey="a" name={labelA} fill="#10b981" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="b" name={labelB} fill="#38bdf8" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </ChartCard>
          </div>

          {/* Detailed Side-by-Side Table */}
          <section className="card">
            <div className="card-header">
              <div>
                <h3 className="card-title">Complete Side-by-Side Comparison Matrix</h3>
                <p className="card-subtitle">
                  Unavailable metrics are explicitly labeled rather than omitted or estimated
                </p>
              </div>
            </div>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Metric / Dimension</th>
                    <th style={{ color: '#34d399' }}>{labelA}</th>
                    <th style={{ color: '#38bdf8' }}>{labelB}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Position / Nationality</td>
                    <td>
                      {data.player_a.profile.position || 'N/A'} •{' '}
                      {data.player_a.profile.country_of_citizenship || 'N/A'}
                    </td>
                    <td>
                      {data.player_b.profile.position || 'N/A'} •{' '}
                      {data.player_b.profile.country_of_citizenship || 'N/A'}
                    </td>
                  </tr>
                  <tr>
                    <td>Club(s) in Scope</td>
                    <td>{data.player_a.metrics.clubs_in_scope.join(', ') || 'No appearances in scope'}</td>
                    <td>{data.player_b.metrics.clubs_in_scope.join(', ') || 'No appearances in scope'}</td>
                  </tr>
                  <tr>
                    <td>Competitions in Scope</td>
                    <td>{data.player_a.metrics.competitions_in_scope.join(', ') || '—'}</td>
                    <td>{data.player_b.metrics.competitions_in_scope.join(', ') || '—'}</td>
                  </tr>
                  <tr>
                    <td>Appearances</td>
                    <td>{data.player_a.metrics.has_appearance_data ? formatInteger(data.player_a.metrics.appearances) : 'No Records (0)'}</td>
                    <td>{data.player_b.metrics.has_appearance_data ? formatInteger(data.player_b.metrics.appearances) : 'No Records (0)'}</td>
                  </tr>
                  <tr>
                    <td>Goals / Assists</td>
                    <td>
                      {data.player_a.metrics.has_appearance_data
                        ? `${formatInteger(data.player_a.metrics.goals)}G / ${formatInteger(data.player_a.metrics.assists)}A`
                        : 'Unavailable'}
                    </td>
                    <td>
                      {data.player_b.metrics.has_appearance_data
                        ? `${formatInteger(data.player_b.metrics.goals)}G / ${formatInteger(data.player_b.metrics.assists)}A`
                        : 'Unavailable'}
                    </td>
                  </tr>
                  <tr>
                    <td>Minutes Played</td>
                    <td>{data.player_a.metrics.has_appearance_data ? `${formatInteger(data.player_a.metrics.minutes_played)}'` : 'Unavailable'}</td>
                    <td>{data.player_b.metrics.has_appearance_data ? `${formatInteger(data.player_b.metrics.minutes_played)}'` : 'Unavailable'}</td>
                  </tr>
                  <tr>
                    <td>Goals / Appearance</td>
                    <td>{formatDecimal(data.player_a.metrics.goals_per_appearance, 2)}</td>
                    <td>{formatDecimal(data.player_b.metrics.goals_per_appearance, 2)}</td>
                  </tr>
                  <tr>
                    <td>Assists / Appearance</td>
                    <td>{formatDecimal(data.player_a.metrics.assists_per_appearance, 2)}</td>
                    <td>{formatDecimal(data.player_b.metrics.assists_per_appearance, 2)}</td>
                  </tr>
                  <tr>
                    <td>Discipline (Yellow / Red)</td>
                    <td>{data.player_a.metrics.yellow_cards} / {data.player_a.metrics.red_cards}</td>
                    <td>{data.player_b.metrics.yellow_cards} / {data.player_b.metrics.red_cards}</td>
                  </tr>
                  <tr>
                    <td>Estimated Market Value (Boundary-Aligned)</td>
                    <td>
                      <div><strong>{formatEurCompact(data.player_a.metrics.market_value_in_eur)}</strong></div>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                        {data.player_a.metrics.market_value_boundary_note}
                      </div>
                    </td>
                    <td>
                      <div><strong>{formatEurCompact(data.player_b.metrics.market_value_in_eur)}</strong></div>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                        {data.player_b.metrics.market_value_boundary_note}
                      </div>
                    </td>
                  </tr>
                  <tr>
                    <td>Transfer Fee in Scope</td>
                    <td>{formatFeeCell(data.player_a)}</td>
                    <td>{formatFeeCell(data.player_b)}</td>
                  </tr>
                  <tr>
                    <td>Latest Prior Paid Transfer Fee (&gt;€0)</td>
                    <td>
                      {data.player_a.metrics.latest_paid_transfer_fee_eur !== null
                        ? `${formatEurCompact(data.player_a.metrics.latest_paid_transfer_fee_eur)} (${data.player_a.metrics.latest_paid_transfer_season})`
                        : 'None recorded'}
                    </td>
                    <td>
                      {data.player_b.metrics.latest_paid_transfer_fee_eur !== null
                        ? `${formatEurCompact(data.player_b.metrics.latest_paid_transfer_fee_eur)} (${data.player_b.metrics.latest_paid_transfer_season})`
                        : 'None recorded'}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </>
  );
}
