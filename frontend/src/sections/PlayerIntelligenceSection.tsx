import { useCallback, useEffect, useState } from 'react';
import {
  Area,
  AreaChart,
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  Calculator,
  ExternalLink,
  GitCompareArrows,
  Search,
} from 'lucide-react';
import { api } from '../api/client';
import type {
  PlayerDetailResponse,
  PlayerSearchItem,
} from '../types/api';
import {
  formatDecimal,
  formatEurCompact,
  formatInteger,
} from '../utils/formatters';
import { ChartCard } from '../components/common/ChartCard';
import { KpiCard } from '../components/common/KpiCard';
import { EmptyState, ErrorState, LoadingState, WarningBanner } from '../components/common/StatePanel';

interface PlayerIntelligenceSectionProps {
  selectedPlayerId: number;
  onSelectPlayerId: (id: number) => void;
  onOpenComparison: (id: number) => void;
  onOpenCalculator: (id: number) => void;
}

const PAGE_SIZE = 10;

function PlayerAvatar({ name, imageUrl }: { name: string; imageUrl: string | null }) {
  const [imgFailed, setImgFailed] = useState(false);
  useEffect(() => {
    setImgFailed(false);
  }, [imageUrl]);

  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? '')
    .join('');

  if (imageUrl && !imgFailed) {
    return (
      <img
        src={imageUrl}
        alt={name}
        className="player-avatar-img"
        referrerPolicy="no-referrer"
        onError={() => setImgFailed(true)}
      />
    );
  }
  return <div className="player-avatar-fallback">{initials || 'PL'}</div>;
}

function FeeBadge({
  fee,
  status,
  isFuture,
}: {
  fee: number | null;
  status: string;
  isFuture?: boolean;
}) {
  if (status === 'paid' && fee !== null) {
    return (
      <span className="tag-pill tag-green">
        {formatEurCompact(fee)}
        {isFuture ? ' • Scheduled' : ''}
      </span>
    );
  }
  if (status === 'free_or_loan') {
    return (
      <span className="tag-pill tag-sky">
        Free / Loan (€0){isFuture ? ' • Scheduled' : ''}
      </span>
    );
  }
  return (
    <span className="tag-pill tag-amber">
      Undisclosed{isFuture ? ' • Scheduled' : ''}
    </span>
  );
}

export function PlayerIntelligenceSection({
  selectedPlayerId,
  onSelectPlayerId,
  onOpenComparison,
  onOpenCalculator,
}: PlayerIntelligenceSectionProps) {
  const [queryInput, setQueryInput] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [positionFilter, setPositionFilter] = useState('');
  const [nationalityFilter, setNationalityFilter] = useState('');
  const [minAppsFilter, setMinAppsFilter] = useState<string>('');
  const [sortBy, setSortBy] = useState<'market_value' | 'highest_market_value' | 'appearances' | 'name' | 'last_season'>('market_value');
  const [offset, setOffset] = useState(0);

  const [searchRows, setSearchRows] = useState<PlayerSearchItem[]>([]);
  const [positions, setPositions] = useState<string[]>([]);
  const [totalMatches, setTotalMatches] = useState(0);
  const [searchLoading, setSearchLoading] = useState(true);
  const [searchError, setSearchError] = useState<string | null>(null);

  const [detail, setDetail] = useState<PlayerDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(true);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [chartMode, setChartMode] = useState<'totals' | 'rates'>('totals');

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedQuery(queryInput);
      setOffset(0);
    }, 260);
    return () => window.clearTimeout(timer);
  }, [queryInput]);

  const loadSearch = useCallback(
    async (signal?: AbortSignal) => {
      setSearchLoading(true);
      setSearchError(null);
      try {
        const res = await api.searchPlayers(
          {
            q: debouncedQuery.trim() || undefined,
            position: positionFilter || undefined,
            nationality: nationalityFilter.trim() || undefined,
            min_appearances: minAppsFilter ? Number(minAppsFilter) : undefined,
            sort_by: sortBy,
            limit: PAGE_SIZE,
            offset,
          },
          signal,
        );
        setSearchRows(res.players);
        setPositions(res.available_positions);
        setTotalMatches(res.pagination.total);
      } catch (err) {
        if ((err as Error).name === 'AbortError') return;
        setSearchError((err as Error).message);
      } finally {
        setSearchLoading(false);
      }
    },
    [debouncedQuery, positionFilter, nationalityFilter, minAppsFilter, sortBy, offset],
  );

  const loadDetail = useCallback(
    async (signal?: AbortSignal) => {
      setDetailLoading(true);
      setDetailError(null);
      try {
        const res = await api.getPlayerDetail(selectedPlayerId, signal);
        setDetail(res);
      } catch (err) {
        if ((err as Error).name === 'AbortError') return;
        setDetailError((err as Error).message);
      } finally {
        setDetailLoading(false);
      }
    },
    [selectedPlayerId],
  );

  useEffect(() => {
    const ctrl = new AbortController();
    loadSearch(ctrl.signal);
    return () => ctrl.abort();
  }, [loadSearch]);

  useEffect(() => {
    const ctrl = new AbortController();
    loadDetail(ctrl.signal);
    return () => ctrl.abort();
  }, [loadDetail]);

  const profile = detail?.profile;
  const summary = detail?.career_summary;

  return (
    <>
      {/* Filter & Search Bar */}
      <div className="filter-bar">
        <div className="filter-field" style={{ flex: '1 1 240px' }}>
          <label className="filter-label" htmlFor="player-search-input">
            Search DuckDB Players (50,149)
          </label>
          <div style={{ position: 'relative' }}>
            <Search
              size={14}
              aria-hidden="true"
              style={{
                position: 'absolute',
                left: 10,
                top: '50%',
                transform: 'translateY(-50%)',
                color: 'var(--text-muted)',
              }}
            />
            <input
              id="player-search-input"
              type="text"
              className="control-input"
              style={{ width: '100%', paddingLeft: 32 }}
              value={queryInput}
              placeholder="Name (e.g. Mbappé, Bellingham, Haaland, Salah)..."
              onChange={(e) => setQueryInput(e.target.value)}
            />
          </div>
        </div>

        <div className="filter-field">
          <label className="filter-label" htmlFor="player-pos-select">
            Position
          </label>
          <select
            id="player-pos-select"
            className="control-select"
            value={positionFilter}
            onChange={(e) => {
              setPositionFilter(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">All positions</option>
            {positions.map((pos) => (
              <option key={pos} value={pos}>
                {pos}
              </option>
            ))}
          </select>
        </div>

        <div className="filter-field">
          <label className="filter-label" htmlFor="player-nat-input">
            Nationality
          </label>
          <input
            id="player-nat-input"
            type="text"
            className="control-input"
            style={{ width: 150 }}
            value={nationalityFilter}
            placeholder="e.g. France, England"
            onChange={(e) => {
              setNationalityFilter(e.target.value);
              setOffset(0);
            }}
          />
        </div>

        <div className="filter-field">
          <label className="filter-label" htmlFor="player-apps-filter">
            Match Coverage
          </label>
          <select
            id="player-apps-filter"
            className="control-select"
            value={minAppsFilter}
            onChange={(e) => {
              setMinAppsFilter(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">All players (incl. 0 apps)</option>
            <option value="1">1+ recorded apps</option>
            <option value="50">50+ appearances</option>
            <option value="150">150+ appearances</option>
          </select>
        </div>

        <div className="filter-field">
          <label className="filter-label" htmlFor="player-sort-select">
            Sort Order
          </label>
          <select
            id="player-sort-select"
            className="control-select"
            value={sortBy}
            onChange={(e) => {
              setSortBy(e.target.value as typeof sortBy);
              setOffset(0);
            }}
          >
            <option value="market_value">Current Market Value</option>
            <option value="highest_market_value">Peak Market Value</option>
            <option value="appearances">Recorded Appearances</option>
            <option value="last_season">Last Active Season</option>
            <option value="name">Alphabetical</option>
          </select>
        </div>
      </div>

      {/* Main Split Directory + Profile Workspace */}
      <div className="player-intel-layout">
        {/* Search Directory Panel */}
        <section className="card player-directory-panel" aria-label="Player search directory">
          <div className="card-header" style={{ marginBottom: 12 }}>
            <div>
              <h2 className="card-title">Player Directory</h2>
              <p className="card-subtitle">
                {formatInteger(totalMatches)} matching players
              </p>
            </div>
          </div>

          {searchLoading ? (
            <LoadingState message="Querying DuckDB player index..." />
          ) : searchError ? (
            <ErrorState message={searchError} onRetry={() => loadSearch()} />
          ) : searchRows.length === 0 ? (
            <EmptyState message="No matching players found. Clear or broaden your search query, position, or nationality filters." />
          ) : (
            <>
              <div className="player-directory-list">
                {searchRows.map((p) => {
                  const active = p.player_id === selectedPlayerId;
                  return (
                    <button
                      key={p.player_id}
                      type="button"
                      className={`player-dir-item ${active ? 'active' : ''}`}
                      onClick={() => onSelectPlayerId(p.player_id)}
                    >
                      <div className="player-dir-top">
                        <span className="player-dir-name">{p.name}</span>
                        <span className="tag-pill tag-green">
                          {formatEurCompact(p.market_value_in_eur)}
                        </span>
                      </div>
                      <div className="player-dir-sub">
                        <span>
                          {p.position || 'Unknown'} • {p.country_of_citizenship || 'Unknown'}
                        </span>
                        <span>{p.current_club_name || 'No club listed'}</span>
                      </div>
                      <div className="player-dir-stats">
                        <span>{formatInteger(p.appearance_count)} apps</span>
                        <span>{formatInteger(p.total_goals)}G / {formatInteger(p.total_assists)}A</span>
                      </div>
                    </button>
                  );
                })}
              </div>

              <div className="pagination-bar">
                <button
                  type="button"
                  className="btn"
                  disabled={offset === 0}
                  onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
                >
                  Prev
                </button>
                <span>
                  {offset + 1}–{Math.min(offset + PAGE_SIZE, totalMatches)} of{' '}
                  {formatInteger(totalMatches)}
                </span>
                <button
                  type="button"
                  className="btn"
                  disabled={offset + PAGE_SIZE >= totalMatches}
                  onClick={() => setOffset((o) => o + PAGE_SIZE)}
                >
                  Next
                </button>
              </div>
            </>
          )}
        </section>

        {/* Selected Player Deep Dive */}
        <div className="player-detail-column">
          {detailLoading ? (
            <LoadingState message="Loading player intelligence profile..." />
          ) : detailError || !detail || !profile || !summary ? (
            <ErrorState message={detailError || 'Player not found.'} onRetry={() => loadDetail()} />
          ) : (
            <>
              {/* Profile Card */}
              <section className="hero-card player-profile-hero">
                <div className="player-profile-top">
                  <div className="player-profile-identity">
                    <PlayerAvatar name={profile.name} imageUrl={profile.image_url} />
                    <div>
                      <div className="hero-eyebrow">
                        Player ID #{profile.player_id} •{' '}
                        {profile.current_club_domestic_competition_id || 'Competition N/A'}
                      </div>
                      <h2 className="hero-title" style={{ fontSize: 24 }}>
                        {profile.name}
                      </h2>
                      <div className="player-meta-tags">
                        <span className="tag-pill tag-green">
                          {profile.position || 'Position N/A'}
                          {profile.sub_position ? ` • ${profile.sub_position}` : ''}
                        </span>
                        <span className="tag-pill tag-sky">
                          {profile.country_of_citizenship || 'Citizenship N/A'}
                        </span>
                        {profile.current_club_name && (
                          <span className="tag-pill tag-amber">{profile.current_club_name}</span>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="player-profile-actions">
                    <button
                      type="button"
                      className="btn btn-accent"
                      onClick={() => onOpenComparison(profile.player_id)}
                    >
                      <GitCompareArrows size={14} aria-hidden="true" />
                      Compare Player
                    </button>
                    <button
                      type="button"
                      className="btn"
                      onClick={() => onOpenCalculator(profile.player_id)}
                    >
                      <Calculator size={14} aria-hidden="true" />
                      Value Calculator
                    </button>
                    {profile.url && (
                      <a
                        href={profile.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        referrerPolicy="no-referrer"
                        className="btn"
                        style={{ textDecoration: 'none' }}
                      >
                        <ExternalLink size={14} aria-hidden="true" />
                        Source Profile
                      </a>
                    )}
                  </div>
                </div>

                <div className="player-bio-grid">
                  <div>
                    <span className="filter-label">Date of Birth / Age</span>
                    <div>
                      {profile.date_of_birth ? `${profile.date_of_birth} (${profile.age} yrs)` : 'Unavailable'}
                    </div>
                  </div>
                  <div>
                    <span className="filter-label">Height / Foot</span>
                    <div>
                      {profile.height_in_cm ? `${profile.height_in_cm} cm` : 'Height N/A'} •{' '}
                      {profile.foot ? `${profile.foot} foot` : 'Foot N/A'}
                    </div>
                  </div>
                  <div>
                    <span className="filter-label">Latest Market Value</span>
                    <div>
                      {formatEurCompact(profile.latest_valuation_in_eur ?? profile.market_value_in_eur)}
                      {profile.latest_valuation_date ? ` (${profile.latest_valuation_date})` : ''}
                    </div>
                  </div>
                  <div>
                    <span className="filter-label">Peak Career Valuation</span>
                    <div>{formatEurCompact(profile.highest_market_value_in_eur)}</div>
                  </div>
                  <div>
                    <span className="filter-label">Contract Expiry</span>
                    <div>{profile.contract_expiration_date || 'Unavailable'}</div>
                  </div>
                  <div>
                    <span className="filter-label">Birthplace / Last Season</span>
                    <div>
                      {profile.city_of_birth || profile.country_of_birth || 'N/A'} •{' '}
                      {profile.last_season ?? 'N/A'}
                    </div>
                  </div>
                </div>
              </section>

              {/* Career KPI Row */}
              <div className="kpi-grid">
                <KpiCard
                  label="Recorded Appearances"
                  value={summary.has_appearance_data ? formatInteger(summary.appearances) : 'No Records'}
                  sublabel={
                    summary.has_appearance_data
                      ? `${summary.seasons_with_appearances} seasons (${summary.first_appearance_season}–${summary.last_appearance_season})`
                      : 'No rows in appearances (2012–2025)'
                  }
                  badge={summary.has_appearance_data ? 'games.season' : 'Unavailable'}
                  badgeTone={summary.has_appearance_data ? 'green' : 'amber'}
                />
                <KpiCard
                  label="Goals & Rate"
                  value={summary.has_appearance_data ? formatInteger(summary.goals) : 'N/A'}
                  sublabel={
                    summary.goals_per_appearance !== null
                      ? `${formatDecimal(summary.goals_per_appearance, 2)} goals / appearance`
                      : 'No appearances to compute rate'
                  }
                  badge={summary.goals_per_appearance !== null ? `${formatDecimal(summary.goals_per_appearance, 2)} G/App` : undefined}
                  badgeTone="green"
                />
                <KpiCard
                  label="Assists & Rate"
                  value={summary.has_appearance_data ? formatInteger(summary.assists) : 'N/A'}
                  sublabel={
                    summary.assists_per_appearance !== null
                      ? `${formatDecimal(summary.assists_per_appearance, 2)} assists / appearance`
                      : 'No appearances to compute rate'
                  }
                  badge={summary.assists_per_appearance !== null ? `${formatDecimal(summary.assists_per_appearance, 2)} A/App` : undefined}
                  badgeTone="sky"
                />
                <KpiCard
                  label="Minutes & Discipline"
                  value={summary.has_appearance_data ? `${formatInteger(summary.minutes_played)}'` : 'N/A'}
                  sublabel={
                    summary.has_appearance_data
                      ? `${summary.yellow_cards} yellow • ${summary.red_cards} red cards`
                      : 'Minutes & cards unavailable'
                  }
                  badge={summary.has_appearance_data ? `${summary.yellow_cards}Y / ${summary.red_cards}R` : 'Unavailable'}
                  badgeTone="amber"
                />
              </div>

              <WarningBanner title="Scope & Non-Fabrication Notice">
                {summary.unavailable_metrics_note} {detail.valuation_disclaimer}
              </WarningBanner>

              {/* Charts Row */}
              <div className="chart-grid-2">
                <ChartCard
                  title="Season-by-Season Performance (games.season)"
                  subtitle="Observed output aggregated strictly by match season from DuckDB appearances"
                  actions={
                    summary.has_appearance_data ? (
                      <div className="seg-group">
                        <button
                          type="button"
                          className={`seg-btn ${chartMode === 'totals' ? 'active' : ''}`}
                          onClick={() => setChartMode('totals')}
                        >
                          Volume
                        </button>
                        <button
                          type="button"
                          className={`seg-btn ${chartMode === 'rates' ? 'active' : ''}`}
                          onClick={() => setChartMode('rates')}
                        >
                          Per App
                        </button>
                      </div>
                    ) : undefined
                  }
                >
                  {!summary.has_appearance_data ? (
                    <EmptyState message="No appearance data available in DuckDB (2012–2025) for this player." />
                  ) : (
                    <ResponsiveContainer width="100%" height={290}>
                      <ComposedChart data={detail.season_stats}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.12)" />
                        <XAxis dataKey="season_label" stroke="#94a3b8" fontSize={11} />
                        <YAxis stroke="#94a3b8" fontSize={11} />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: '#0a101a',
                            borderColor: 'rgba(148,163,184,0.28)',
                            borderRadius: 10,
                            fontSize: 12,
                          }}
                        />
                        <Legend wrapperStyle={{ fontSize: 12 }} />
                        {chartMode === 'totals' ? (
                          <>
                            <Bar dataKey="appearances" name="Appearances" fill="#334155" radius={[4, 4, 0, 0]} />
                            <Bar dataKey="goals" name="Goals" fill="#10b981" radius={[4, 4, 0, 0]} />
                            <Line type="monotone" dataKey="assists" name="Assists" stroke="#38bdf8" strokeWidth={2.2} dot={{ r: 3 }} />
                          </>
                        ) : (
                          <>
                            <Line
                              type="monotone"
                              dataKey="goals_per_appearance"
                              name="Goals / App"
                              stroke="#10b981"
                              strokeWidth={2.4}
                              dot={{ r: 3 }}
                            />
                            <Line
                              type="monotone"
                              dataKey="assists_per_appearance"
                              name="Assists / App"
                              stroke="#38bdf8"
                              strokeWidth={2.4}
                              dot={{ r: 3 }}
                            />
                          </>
                        )}
                      </ComposedChart>
                    </ResponsiveContainer>
                  )}
                </ChartCard>

                <ChartCard
                  title="Estimated Market Value History"
                  subtitle="Chronological Transfermarkt valuations from player_valuations (estimated, not ROI)"
                >
                  {!summary.has_valuation_data ? (
                    <EmptyState message="No valuation history recorded in DuckDB player_valuations for this player." />
                  ) : (
                    <ResponsiveContainer width="100%" height={290}>
                      <AreaChart data={detail.market_value_history}>
                        <defs>
                          <linearGradient id="mvAreaGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#10b981" stopOpacity={0.38} />
                            <stop offset="95%" stopColor="#10b981" stopOpacity={0.0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.12)" />
                        <XAxis dataKey="date" stroke="#94a3b8" fontSize={11} minTickGap={28} />
                        <YAxis
                          stroke="#94a3b8"
                          fontSize={11}
                          tickFormatter={(v) => formatEurCompact(Number(v))}
                        />
                        <Tooltip
                          formatter={(val: number) => [formatEurCompact(val), 'Estimated MV']}
                          contentStyle={{
                            backgroundColor: '#0a101a',
                            borderColor: 'rgba(148,163,184,0.28)',
                            borderRadius: 10,
                            fontSize: 12,
                          }}
                        />
                        <Area
                          type="monotone"
                          dataKey="market_value_in_eur"
                          stroke="#10b981"
                          strokeWidth={2.2}
                          fill="url(#mvAreaGrad)"
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  )}
                </ChartCard>
              </div>

              {/* Season Stats Table */}
              {summary.has_appearance_data && (
                <section className="card">
                  <div className="card-header">
                    <div>
                      <h3 className="card-title">Season-Wise Appearance Breakdown</h3>
                      <p className="card-subtitle">
                        Aligned strictly to games.season ({detail.season_stats.length} seasons)
                      </p>
                    </div>
                  </div>
                  <div className="table-wrap">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Season</th>
                          <th>Clubs</th>
                          <th>Competitions</th>
                          <th className="num">Apps</th>
                          <th className="num">Goals</th>
                          <th className="num">Assists</th>
                          <th className="num">Minutes</th>
                          <th className="num">G/App</th>
                          <th className="num">A/App</th>
                          <th className="num">Cards (Y/R)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.season_stats.map((s) => (
                          <tr key={s.season}>
                            <td>
                              <strong>{s.season_label}</strong>{' '}
                              <span style={{ color: 'var(--text-muted)' }}>({s.season})</span>
                            </td>
                            <td>{s.clubs.join(', ') || '—'}</td>
                            <td>{s.competitions.join(', ') || '—'}</td>
                            <td className="num">{formatInteger(s.appearances)}</td>
                            <td className="num">{formatInteger(s.goals)}</td>
                            <td className="num">{formatInteger(s.assists)}</td>
                            <td className="num">{formatInteger(s.minutes_played)}</td>
                            <td className="num">{formatDecimal(s.goals_per_appearance, 2)}</td>
                            <td className="num">{formatDecimal(s.assists_per_appearance, 2)}</td>
                            <td className="num">
                              {s.yellow_cards}/{s.red_cards}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}

              {/* Club Career Timeline & Transfer History */}
              <div className="chart-grid-2">
                <section className="card">
                  <div className="card-header">
                    <div>
                      <h3 className="card-title">Club Career Timeline</h3>
                      <p className="card-subtitle">
                        Unified from appearances spells & recorded transfer destinations
                      </p>
                    </div>
                  </div>
                  {detail.club_timeline.length === 0 ? (
                    <EmptyState message="No club spells recorded in appearances or transfers for this player." />
                  ) : (
                    <div className="club-timeline-list">
                      {detail.club_timeline.map((spell, idx) => (
                        <div key={`${spell.club_name}-${idx}`} className="club-timeline-item">
                          <div className="club-timeline-dot" aria-hidden="true" />
                          <div className="club-timeline-body">
                            <div className="club-timeline-head">
                              <strong>{spell.club_name}</strong>
                              <span className="tag-pill tag-sky">{spell.season_span}</span>
                            </div>
                            <div className="club-timeline-meta">
                              {spell.appearances > 0 ? (
                                <span>
                                  {formatInteger(spell.appearances)} apps • {spell.goals}G •{' '}
                                  {spell.assists}A • {formatInteger(spell.minutes_played)} mins
                                </span>
                              ) : (
                                <span>No appearance rows in DuckDB for this spell</span>
                              )}
                              <span className="tag-pill tag-amber">{spell.source}</span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </section>

                <section className="card">
                  <div className="card-header">
                    <div>
                      <h3 className="card-title">Career Transfer History</h3>
                      <p className="card-subtitle">
                        Distinguishing paid fees (&gt;€0), Free/Loan (€0), and Undisclosed (NULL)
                      </p>
                    </div>
                  </div>
                  {!summary.has_transfer_data ? (
                    <EmptyState message="No transfer history recorded in DuckDB for this player." />
                  ) : (
                    <div className="table-wrap">
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>Date / Season</th>
                            <th>From → To</th>
                            <th>Fee Status</th>
                            <th className="num">Arrival MV</th>
                          </tr>
                        </thead>
                        <tbody>
                          {detail.transfer_history.map((tr, idx) => (
                            <tr key={`${tr.transfer_date}-${tr.to_club_name}-${idx}`}>
                              <td>
                                <div>{tr.transfer_date || 'Date N/A'}</div>
                                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                                  {tr.transfer_season || '—'}
                                </div>
                              </td>
                              <td>
                                <span>{tr.from_club_name || 'Unknown'}</span>
                                {' → '}
                                <strong>{tr.to_club_name || 'Unknown'}</strong>
                              </td>
                              <td>
                                <FeeBadge
                                  fee={tr.transfer_fee}
                                  status={tr.fee_status}
                                  isFuture={tr.is_future_scheduled}
                                />
                              </td>
                              <td className="num">{formatEurCompact(tr.market_value_in_eur)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </section>
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}
