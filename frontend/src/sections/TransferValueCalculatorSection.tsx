import { useCallback, useEffect, useState } from 'react';
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
import { ArrowRight } from 'lucide-react';
import { api } from '../api/client';
import type {
  PlayerTransferSpellsResponse,
  TransferSpellCalculatorRow,
} from '../types/api';
import {
  formatDecimal,
  formatEurCompact,
  formatPercent,
} from '../utils/formatters';
import { ChartCard } from '../components/common/ChartCard';
import { KpiCard } from '../components/common/KpiCard';
import { PlayerPicker } from '../components/common/PlayerPicker';
import { EmptyState, ErrorState, LoadingState, WarningBanner } from '../components/common/StatePanel';

interface TransferValueCalculatorSectionProps {
  initialPlayerId?: number | null;
}

export function TransferValueCalculatorSection({
  initialPlayerId,
}: TransferValueCalculatorSectionProps) {
  const [mode, setMode] = useState<'database' | 'manual'>('database');

  // Mode A: Database player lookup
  const [playerId, setPlayerId] = useState<number>(initialPlayerId ?? 418560);
  const [dbData, setDbData] = useState<PlayerTransferSpellsResponse | null>(null);
  const [selectedSpellIdx, setSelectedSpellIdx] = useState<number>(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Mode B: Manual scenario inputs (€M)
  const [manualFeeM, setManualFeeM] = useState<string>('60');
  const [manualArrivalMvM, setManualArrivalMvM] = useState<string>('150');
  const [manualPeakMvM, setManualPeakMvM] = useState<string>('200');

  useEffect(() => {
    if (initialPlayerId) {
      setPlayerId(initialPlayerId);
      setMode('database');
    }
  }, [initialPlayerId]);

  const loadSpells = useCallback(
    async (signal?: AbortSignal) => {
      setLoading(true);
      setError(null);
      try {
        const res = await api.getPlayerTransferSpells(playerId, signal);
        setDbData(res);
        // Default to newest paid spell if present, else first spell
        const paidIdx = res.spells.findIndex((s) => s.fee_status === 'paid');
        setSelectedSpellIdx(paidIdx >= 0 ? paidIdx : 0);
      } catch (err) {
        if ((err as Error).name === 'AbortError') return;
        setError((err as Error).message);
      } finally {
        setLoading(false);
      }
    },
    [playerId],
  );

  useEffect(() => {
    const ctrl = new AbortController();
    loadSpells(ctrl.signal);
    return () => ctrl.abort();
  }, [loadSpells]);

  const activeSpell: TransferSpellCalculatorRow | null =
    dbData?.spells[selectedSpellIdx] ?? null;

  const cloneToManual = (spell: TransferSpellCalculatorRow) => {
    setManualFeeM(
      spell.transfer_fee !== null ? String(Number((spell.transfer_fee / 1e6).toFixed(2))) : '0',
    );
    setManualArrivalMvM(
      spell.mv_at_arrival !== null ? String(Number((spell.mv_at_arrival / 1e6).toFixed(2))) : '0',
    );
    setManualPeakMvM(
      spell.peak_mv !== null ? String(Number((spell.peak_mv / 1e6).toFixed(2))) : '0',
    );
    setMode('manual');
  };

  // Manual computations (€M -> €)
  const feeM = Number(manualFeeM);
  const arrivalM = Number(manualArrivalMvM);
  const peakM = Number(manualPeakMvM);
  const validFee = Number.isFinite(feeM) && feeM > 0;
  const validArrival = Number.isFinite(arrivalM) && arrivalM > 0;
  const validPeak = Number.isFinite(peakM) && peakM >= 0;

  const arrivalPremiumM =
    Number.isFinite(feeM) && Number.isFinite(arrivalM) ? feeM - arrivalM : null;
  const arrivalPremiumPct =
    validArrival && arrivalPremiumM !== null ? (arrivalPremiumM / arrivalM) * 100 : null;
  const estMvGainM = validFee && validPeak ? peakM - feeM : null;
  const estMvGainPct = validFee && estMvGainM !== null ? (estMvGainM / feeM) * 100 : null;
  const estMvMultiple = validFee && validPeak ? peakM / feeM : null;

  const dbChartData = activeSpell
    ? [
        {
          stage: 'Transfer Fee',
          valueM: (activeSpell.transfer_fee ?? 0) / 1e6,
          color: '#38bdf8',
        },
        {
          stage: 'Arrival MV',
          valueM: (activeSpell.mv_at_arrival ?? 0) / 1e6,
          color: '#a78bfa',
        },
        {
          stage: 'Spell Peak MV',
          valueM: (activeSpell.peak_mv ?? 0) / 1e6,
          color: '#10b981',
        },
        {
          stage: 'Spell Latest MV',
          valueM: (activeSpell.latest_mv_at_club ?? 0) / 1e6,
          color: '#f59e0b',
        },
      ]
    : [];

  const manualChartData = [
    { stage: 'Transfer Fee', valueM: Number.isFinite(feeM) ? Math.max(0, feeM) : 0, color: '#38bdf8' },
    {
      stage: 'Arrival MV',
      valueM: Number.isFinite(arrivalM) ? Math.max(0, arrivalM) : 0,
      color: '#a78bfa',
    },
    {
      stage: 'Estimated Current / Peak MV',
      valueM: validPeak ? peakM : 0,
      color: estMvGainM !== null && estMvGainM < 0 ? '#f43f5e' : '#10b981',
    },
  ];

  return (
    <>
      <WarningBanner title="Estimated Market Value ≠ Financial ROI">
        {dbData?.valuation_disclaimer ||
          'Transfermarkt market values are crowdsourced valuation estimates, NOT actual club financial profit, accounting book value, realized sale proceeds, or ROI. Wages, bonuses, and amortization are not included.'}
      </WarningBanner>

      {/* Mode Switcher */}
      <div className="filter-bar" style={{ justifyContent: 'space-between' }}>
        <div className="seg-group" aria-label="Transfer Value Calculator modes">
          <button
            type="button"
            className={`seg-btn ${mode === 'database' ? 'active' : ''}`}
            onClick={() => setMode('database')}
          >
            Mode A: Database Player Spells
          </button>
          <button
            type="button"
            className={`seg-btn ${mode === 'manual' ? 'active' : ''}`}
            onClick={() => setMode('manual')}
          >
            Mode B: Manual Scenario Estimator
          </button>
        </div>

        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          Spell valuation bounds match Phase 2 methodology (`[transfer_date, next_transfer_date)`)
        </span>
      </div>

      {mode === 'database' ? (
        <>
          <div className="filter-bar">
            <div style={{ flex: '1 1 280px' }}>
              <PlayerPicker
                label="Select Player from DuckDB"
                selectedName={dbData?.profile.name}
                selectedMeta={
                  dbData
                    ? `#${dbData.profile.player_id} • ${dbData.profile.current_club_name ?? 'No current club'}`
                    : undefined
                }
                onSelect={(p) => setPlayerId(p.player_id)}
              />
            </div>

            {dbData && dbData.spells.length > 0 && (
              <div className="filter-field" style={{ flex: '1 1 280px' }}>
                <label className="filter-label" htmlFor="calc-spell-select">
                  Transfer Spell ({dbData.spells.length} recorded)
                </label>
                <select
                  id="calc-spell-select"
                  className="control-select"
                  value={selectedSpellIdx}
                  onChange={(e) => setSelectedSpellIdx(Number(e.target.value))}
                >
                  {dbData.spells.map((s, idx) => (
                    <option key={`${s.spell_index}-${idx}`} value={idx}>
                      {s.transfer_season || s.transfer_date || 'Spell'} •{' '}
                      {s.from_club_name || 'Unknown'} → {s.to_club_name || 'Unknown'} (
                      {s.fee_status === 'paid'
                        ? formatEurCompact(s.transfer_fee)
                        : s.fee_status === 'free_or_loan'
                        ? '€0 Free/Loan'
                        : 'Undisclosed'}
                      )
                    </option>
                  ))}
                </select>
              </div>
            )}

            {activeSpell && (
              <button
                type="button"
                className="btn btn-accent"
                onClick={() => cloneToManual(activeSpell)}
              >
                Clone into Manual Mode
                <ArrowRight size={14} aria-hidden="true" />
              </button>
            )}
          </div>

          {loading ? (
            <LoadingState message="Computing spell-bounded valuations from DuckDB..." />
          ) : error || !dbData ? (
            <ErrorState message={error || 'Unable to load player transfer spells.'} onRetry={() => loadSpells()} />
          ) : !activeSpell ? (
            <EmptyState
              message={`${dbData.profile.name} has no transfer records in DuckDB. Switch to Mode B to test hypothetical valuation scenarios.`}
            />
          ) : (
            <>
              <div className="kpi-grid">
                <KpiCard
                  label="Recorded Transfer Fee"
                  value={
                    activeSpell.fee_status === 'paid'
                      ? formatEurCompact(activeSpell.transfer_fee)
                      : activeSpell.fee_status === 'free_or_loan'
                      ? 'Free / Loan (€0)'
                      : 'Undisclosed'
                  }
                  sublabel={`${activeSpell.from_club_name || 'Unknown'} → ${activeSpell.to_club_name || 'Unknown'} (${activeSpell.transfer_date || 'Date N/A'})`}
                  badge={activeSpell.transfer_season || undefined}
                  badgeTone={activeSpell.fee_status === 'paid' ? 'sky' : 'amber'}
                />
                <KpiCard
                  label="Estimated Arrival Market Value"
                  value={formatEurCompact(activeSpell.mv_at_arrival)}
                  sublabel={activeSpell.mv_at_arrival_source || 'No arrival valuation recorded'}
                  badge={
                    activeSpell.transfer_fee !== null &&
                    activeSpell.mv_at_arrival !== null &&
                    activeSpell.mv_at_arrival > 0 &&
                    activeSpell.fee_status === 'paid'
                      ? `${formatPercent(((activeSpell.transfer_fee - activeSpell.mv_at_arrival) / activeSpell.mv_at_arrival) * 100, 1)} vs MV`
                      : undefined
                  }
                  badgeTone="amber"
                />
                <KpiCard
                  label="Spell Peak Est. MV & Gain"
                  value={formatEurCompact(activeSpell.peak_mv)}
                  sublabel={
                    activeSpell.est_peak_mv_gain !== null
                      ? `Est. MV Gain vs Fee: ${formatEurCompact(activeSpell.est_peak_mv_gain, true)} (${formatPercent(activeSpell.est_peak_mv_gain_pct, 1)})`
                      : activeSpell.fee_status === 'paid'
                      ? `${activeSpell.valuation_count} valuations in spell`
                      : 'MV/Fee multiple requires paid fee (>€0)'
                  }
                  badge={
                    activeSpell.peak_mv_to_fee_multiple !== null
                      ? `${formatDecimal(activeSpell.peak_mv_to_fee_multiple, 2)}x Fee`
                      : undefined
                  }
                  badgeTone={
                    (activeSpell.est_peak_mv_gain ?? 0) >= 0 ? 'green' : 'rose'
                  }
                />
                <KpiCard
                  label="Latest Spell Est. MV"
                  value={formatEurCompact(activeSpell.latest_mv_at_club)}
                  sublabel={
                    activeSpell.est_latest_mv_gain !== null
                      ? `Est. MV Change vs Fee: ${formatEurCompact(activeSpell.est_latest_mv_gain, true)}`
                      : `Last spell valuation: ${activeSpell.last_valuation_date || 'None in window'}`
                  }
                  badge={
                    activeSpell.latest_mv_to_fee_multiple !== null
                      ? `${formatDecimal(activeSpell.latest_mv_to_fee_multiple, 2)}x Fee`
                      : undefined
                  }
                  badgeTone="green"
                />
              </div>

              <div className="chart-grid-2">
                <ChartCard
                  title="Spell Valuation Benchmark (€M)"
                  subtitle={`${dbData.profile.name} at ${activeSpell.to_club_name || 'Club'} (${activeSpell.transfer_date || '—'} to ${activeSpell.next_transfer_date || 'Present'})`}
                  note={dbData.methodology_note}
                >
                  <ResponsiveContainer width="100%" height={280}>
                    <BarChart data={dbChartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.12)" />
                      <XAxis dataKey="stage" stroke="#94a3b8" fontSize={11.5} />
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
                      <Bar dataKey="valueM" radius={[6, 6, 0, 0]}>
                        {dbChartData.map((d) => (
                          <Cell key={d.stage} fill={d.color} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </ChartCard>

                <section className="card">
                  <div className="card-header">
                    <div>
                      <h3 className="card-title">All Recorded Spells ({dbData.profile.name})</h3>
                      <p className="card-subtitle">Click any row to inspect spell valuation metrics</p>
                    </div>
                  </div>
                  <div className="table-wrap">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Window</th>
                          <th>To Club</th>
                          <th className="num">Fee</th>
                          <th className="num">Peak MV</th>
                          <th className="num">Peak Mult</th>
                        </tr>
                      </thead>
                      <tbody>
                        {dbData.spells.map((s, idx) => (
                          <tr
                            key={`${s.spell_index}-${idx}`}
                            style={{
                              cursor: 'pointer',
                              background:
                                idx === selectedSpellIdx ? 'rgba(16, 185, 129, 0.08)' : undefined,
                            }}
                            onClick={() => setSelectedSpellIdx(idx)}
                          >
                            <td>
                              <div>{s.transfer_season || '—'}</div>
                              <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                                {s.transfer_date || 'No date'}
                              </div>
                            </td>
                            <td>
                              <strong>{s.to_club_name || 'Unknown'}</strong>
                            </td>
                            <td className="num">
                              {s.fee_status === 'paid'
                                ? formatEurCompact(s.transfer_fee)
                                : s.fee_status === 'free_or_loan'
                                ? '€0 Free/Loan'
                                : 'Undisclosed'}
                            </td>
                            <td className="num">{formatEurCompact(s.peak_mv)}</td>
                            <td className="num">
                              {s.peak_mv_to_fee_multiple !== null
                                ? `${formatDecimal(s.peak_mv_to_fee_multiple, 2)}x`
                                : '—'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              </div>
            </>
          )}
        </>
      ) : (
        /* Mode B: Manual Calculator */
        <div className="chart-grid-asym">
          <section className="card">
            <div className="card-header">
              <div>
                <h2 className="card-title">Manual Valuation Estimator (€ Millions)</h2>
                <p className="card-subtitle">
                  Interactive sensitivity calculator for hypothetical transfer fee vs estimated market value
                </p>
              </div>
            </div>

            <div className="calc-inputs-grid">
              <div className="filter-field">
                <label className="filter-label" htmlFor="manual-fee-input">
                  Transfer Fee Paid (€M)
                </label>
                <input
                  id="manual-fee-input"
                  type="number"
                  min={0}
                  step="0.5"
                  className="control-input"
                  value={manualFeeM}
                  onChange={(e) => setManualFeeM(e.target.value)}
                />
              </div>

              <div className="filter-field">
                <label className="filter-label" htmlFor="manual-arrival-input">
                  Estimated Market Value at Arrival (€M)
                </label>
                <input
                  id="manual-arrival-input"
                  type="number"
                  min={0}
                  step="0.5"
                  className="control-input"
                  value={manualArrivalMvM}
                  onChange={(e) => setManualArrivalMvM(e.target.value)}
                />
              </div>

              <div className="filter-field">
                <label className="filter-label" htmlFor="manual-peak-input">
                  Estimated Peak / Current Market Value (€M)
                </label>
                <input
                  id="manual-peak-input"
                  type="number"
                  min={0}
                  step="0.5"
                  className="control-input"
                  value={manualPeakMvM}
                  onChange={(e) => setManualPeakMvM(e.target.value)}
                />
              </div>
            </div>

            <div className="kpi-grid-3" style={{ marginTop: 18 }}>
              <KpiCard
                label="Fee vs Arrival MV Premium"
                value={
                  arrivalPremiumM !== null
                    ? `${arrivalPremiumM >= 0 ? '+' : ''}€${arrivalPremiumM.toFixed(1)}M`
                    : '—'
                }
                sublabel={
                  arrivalPremiumPct !== null
                    ? `${formatPercent(arrivalPremiumPct, 1)} relative to arrival MV`
                    : 'Enter positive arrival MV'
                }
                badgeTone={arrivalPremiumM !== null && arrivalPremiumM > 0 ? 'amber' : 'green'}
              />
              <KpiCard
                label="Estimated MV Gain vs Fee"
                value={
                  estMvGainM !== null
                    ? `${estMvGainM >= 0 ? '+' : ''}€${estMvGainM.toFixed(1)}M`
                    : 'N/A'
                }
                sublabel={
                  estMvGainPct !== null
                    ? `${formatPercent(estMvGainPct, 1)} estimated MV change vs fee`
                    : 'Enter positive transfer fee'
                }
                badgeTone={estMvGainM !== null && estMvGainM >= 0 ? 'green' : 'rose'}
              />
              <KpiCard
                label="Estimated MV / Fee Multiple"
                value={estMvMultiple !== null ? `${formatDecimal(estMvMultiple, 2)}x` : 'N/A'}
                sublabel="Target Estimated MV ÷ Transfer Fee"
                badgeTone={estMvMultiple !== null && estMvMultiple >= 1 ? 'green' : 'rose'}
              />
            </div>
          </section>

          <ChartCard
            title="Manual Scenario Comparison (€M)"
            subtitle="Hypothetical benchmark comparing fee against arrival and target estimated MV"
            note="Manual outputs reflect user-entered hypothetical numbers only and do not represent realized profit or financial ROI."
          >
            <ResponsiveContainer width="100%" height={270}>
              <BarChart data={manualChartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.12)" />
                <XAxis dataKey="stage" stroke="#94a3b8" fontSize={11} />
                <YAxis stroke="#94a3b8" fontSize={11} tickFormatter={(v) => `€${v}M`} />
                <Tooltip
                  formatter={(val: number) => [`€${val.toFixed(1)}M`, 'Scenario Value']}
                  contentStyle={{
                    backgroundColor: '#0a101a',
                    borderColor: 'rgba(148,163,184,0.28)',
                    borderRadius: 10,
                    fontSize: 12,
                  }}
                />
                <Bar dataKey="valueM" radius={[6, 6, 0, 0]}>
                  {manualChartData.map((d) => (
                    <Cell key={d.stage} fill={d.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        </div>
      )}
    </>
  );
}
