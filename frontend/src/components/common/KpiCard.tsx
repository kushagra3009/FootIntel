import type { ReactNode } from 'react';

interface KpiCardProps {
  label: string;
  value: string;
  sublabel?: string;
  badge?: string;
  badgeTone?: 'green' | 'amber' | 'sky' | 'rose';
  icon?: ReactNode;
}

export function KpiCard({
  label,
  value,
  sublabel,
  badge,
  badgeTone = 'green',
  icon,
}: KpiCardProps) {
  return (
    <article className="card kpi-card">
      <div className="kpi-top">
        <span className="kpi-label">{label}</span>
        {icon && <span className="kpi-icon" aria-hidden="true">{icon}</span>}
      </div>
      <div className="kpi-value">{value}</div>
      {(sublabel || badge) && (
        <div className="kpi-foot">
          <span>{sublabel ?? ''}</span>
          {badge && <span className={`tag-pill tag-${badgeTone}`}>{badge}</span>}
        </div>
      )}
    </article>
  );
}
