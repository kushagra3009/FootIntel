export const TOP5_LEAGUE_OPTIONS = [
  { id: 'GB1', name: 'Premier League', color: '#10b981' },
  { id: 'ES1', name: 'LaLiga', color: '#f59e0b' },
  { id: 'IT1', name: 'Serie A', color: '#38bdf8' },
  { id: 'L1', name: 'Bundesliga', color: '#f43f5e' },
  { id: 'FR1', name: 'Ligue 1', color: '#a78bfa' },
] as const;

export const LEAGUE_COLOR_MAP: Record<string, string> = {
  GB1: '#10b981',
  'Premier League': '#10b981',
  ES1: '#f59e0b',
  LaLiga: '#f59e0b',
  IT1: '#38bdf8',
  'Serie A': '#38bdf8',
  L1: '#f43f5e',
  Bundesliga: '#f43f5e',
  FR1: '#a78bfa',
  'Ligue 1': '#a78bfa',
};

export function formatEurCompact(euros: number | null | undefined, signed = false): string {
  if (euros === null || euros === undefined || Number.isNaN(euros)) return '—';
  const abs = Math.abs(euros);
  const sign = euros < 0 ? '-' : signed && euros > 0 ? '+' : '';
  if (abs >= 1e9) return `${sign}€${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}€${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}€${(abs / 1e3).toFixed(0)}K`;
  return `${sign}€${abs.toFixed(0)}`;
}

export function formatEurMillions(millions: number | null | undefined, signed = false): string {
  if (millions === null || millions === undefined || Number.isNaN(millions)) return '—';
  const sign = millions < 0 ? '-' : signed && millions > 0 ? '+' : '';
  const abs = Math.abs(millions);
  if (abs >= 1000) return `${sign}€${(abs / 1000).toFixed(2)}B`;
  return `${sign}€${abs.toFixed(1)}M`;
}

export function formatInteger(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  return new Intl.NumberFormat('en-US').format(Math.round(n));
}

export function formatPercent(pct: number | null | undefined, digits = 1): string {
  if (pct === null || pct === undefined || Number.isNaN(pct)) return '—';
  return `${pct.toFixed(digits)}%`;
}

export function formatDecimal(val: number | null | undefined, digits = 4): string {
  if (val === null || val === undefined || Number.isNaN(val)) return '—';
  return val.toFixed(digits);
}

export function formatPValue(p: number | null | undefined): string {
  if (p === null || p === undefined || Number.isNaN(p)) return '—';
  if (p === 0) return '< 1e-300';
  if (p < 0.0001) return p.toExponential(2);
  return p.toFixed(4);
}

export function seasonLabel(gameSeason: number): string {
  const y1 = String(gameSeason % 100).padStart(2, '0');
  const y2 = String((gameSeason + 1) % 100).padStart(2, '0');
  return `${y1}/${y2}`;
}
