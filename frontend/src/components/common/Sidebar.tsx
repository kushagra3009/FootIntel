import {
  Activity,
  Award,
  BarChart3,
  BookOpen,
  Calculator,
  DollarSign,
  GitCompareArrows,
  Globe,
  ShieldCheck,
  TrendingUp,
  Users,
} from 'lucide-react';
import type { HealthResponse, NavSectionId } from '../../types/api';

export interface NavItemConfig {
  id: NavSectionId;
  label: string;
  subtitle: string;
  icon: typeof BarChart3;
}

export const NAV_ITEMS: NavItemConfig[] = [
  { id: 'overview', label: 'Overview', subtitle: 'Executive KPIs & synthesis', icon: Activity },
  { id: 'market', label: 'Transfer Market', subtitle: 'Spending & cohort coverage', icon: TrendingUp },
  { id: 'domestic', label: 'Domestic Performance', subtitle: 'Big 5 leagues & OLS slope', icon: Globe },
  { id: 'ucl', label: 'Champions League', subtitle: 'UCL stages & paired test', icon: Award },
  { id: 'value', label: 'Transfer Value Analysis', subtitle: 'Fee vs MV & spell gains', icon: DollarSign },
  { id: 'statistics', label: 'Statistical Insights', subtitle: 'Correlations & fixed effects', icon: BarChart3 },
  { id: 'players', label: 'Player Intelligence', subtitle: 'Profiles, stats & career timeline', icon: Users },
  { id: 'player-compare', label: 'Player Comparison', subtitle: 'Cross-season player matrix', icon: GitCompareArrows },
  { id: 'calculator', label: 'Value Calculator', subtitle: 'Spell & manual MV estimator', icon: Calculator },
  { id: 'methodology', label: 'Methodology & Limits', subtitle: 'Definitions & data caveats', icon: BookOpen },
];

interface SidebarProps {
  activeSection: NavSectionId;
  onSelect: (id: NavSectionId) => void;
  health: HealthResponse | null;
  apiOnline: boolean;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}

export function Sidebar({
  activeSection,
  onSelect,
  health,
  apiOnline,
  mobileOpen,
  onCloseMobile,
}: SidebarProps) {
  return (
    <>
      <div
        className={`mobile-backdrop ${mobileOpen ? 'open' : ''}`}
        onClick={onCloseMobile}
        aria-hidden="true"
      />
      <aside className={`sidebar ${mobileOpen ? 'open' : ''}`} aria-label="Primary navigation">
        <div className="brand-block">
          <div className="brand-mark" aria-hidden="true">
            <ShieldCheck size={20} />
          </div>
          <div>
            <div className="brand-title">FOOTINTEL</div>
            <div className="brand-subtitle">Transfer Intelligence Engine</div>
          </div>
        </div>

        <div className="nav-group-label">Research Modules</div>
        <nav className="nav-list">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = item.id === activeSection;
            return (
              <button
                key={item.id}
                type="button"
                className={`nav-item ${isActive ? 'active' : ''}`}
                aria-current={isActive ? 'page' : undefined}
                onClick={() => {
                  onSelect(item.id);
                  onCloseMobile();
                }}
              >
                <Icon size={17} aria-hidden="true" />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        <div className="sidebar-footer">
          <div className="status-pill">
            <span className={`status-dot ${apiOnline ? 'online' : 'offline'}`} aria-hidden="true" />
            <div>
              <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                {apiOnline ? 'FastAPI Connected' : 'API Offline'}
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                {health ? `${health.database_file} • ${health.output_files_count} outputs` : 'Checking backend...'}
              </div>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
