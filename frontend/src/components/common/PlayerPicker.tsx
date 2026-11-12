import { useEffect, useRef, useState } from 'react';
import { Search, User } from 'lucide-react';
import { api } from '../../api/client';
import type { PlayerSearchItem } from '../../types/api';
import { formatEurCompact } from '../../utils/formatters';

interface PlayerPickerProps {
  label: string;
  selectedName?: string;
  selectedMeta?: string;
  onSelect: (player: PlayerSearchItem) => void;
  minAppearances?: number;
}

export function PlayerPicker({
  label,
  selectedName,
  selectedMeta,
  onSelect,
  minAppearances,
}: PlayerPickerProps) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<PlayerSearchItem[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, []);

  useEffect(() => {
    if (!open) return;
    const ctrl = new AbortController();
    const timer = window.setTimeout(() => {
      setLoading(true);
      setErr(null);
      api
        .searchPlayers(
          {
            q: query.trim() || undefined,
            min_appearances: minAppearances,
            sort_by: 'market_value',
            limit: 12,
            offset: 0,
          },
          ctrl.signal,
        )
        .then((res) => setResults(res.players))
        .catch((e: Error) => {
          if (e.name !== 'AbortError') setErr(e.message);
        })
        .finally(() => setLoading(false));
    }, 220);

    return () => {
      window.clearTimeout(timer);
      ctrl.abort();
    };
  }, [query, open, minAppearances]);

  return (
    <div ref={containerRef} className="player-picker">
      <span className="filter-label">{label}</span>
      <div className="player-picker-box">
        <Search size={14} className="player-picker-icon" aria-hidden="true" />
        <input
          type="text"
          className="control-input player-picker-input"
          value={open ? query : selectedName ?? query}
          placeholder="Search player name (e.g. Bellingham, Haaland)..."
          aria-label={label}
          onFocus={() => {
            setQuery('');
            setOpen(true);
          }}
          onChange={(e) => {
            setQuery(e.target.value);
            if (!open) setOpen(true);
          }}
        />
      </div>
      {selectedMeta && !open && <div className="player-picker-meta">{selectedMeta}</div>}

      {open && (
        <div className="player-picker-dropdown" role="listbox" aria-label={`${label} results`}>
          {loading && <div className="player-picker-empty">Searching DuckDB players...</div>}
          {err && <div className="player-picker-empty" style={{ color: 'var(--rose)' }}>{err}</div>}
          {!loading && !err && results.length === 0 && (
            <div className="player-picker-empty">No players matched “{query}”.</div>
          )}
          {!loading &&
            !err &&
            results.map((p) => (
              <button
                key={p.player_id}
                type="button"
                role="option"
                className="player-picker-option"
                onClick={() => {
                  onSelect(p);
                  setOpen(false);
                  setQuery('');
                }}
              >
                <div className="player-picker-option-main">
                  <User size={13} aria-hidden="true" style={{ color: 'var(--accent-bright)' }} />
                  <span style={{ fontWeight: 600 }}>{p.name}</span>
                  <span className="tag-pill tag-sky">{p.position || 'Unknown'}</span>
                </div>
                <div className="player-picker-option-sub">
                  <span>{p.current_club_name || 'No current club'}</span>
                  <span>
                    {p.appearance_count} apps • {formatEurCompact(p.market_value_in_eur)}
                  </span>
                </div>
              </button>
            ))}
        </div>
      )}
    </div>
  );
}
