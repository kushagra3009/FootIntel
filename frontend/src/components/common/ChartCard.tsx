import type { ReactNode } from 'react';

interface ChartCardProps {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  note?: string;
  children: ReactNode;
}

export function ChartCard({ title, subtitle, actions, note, children }: ChartCardProps) {
  return (
    <section className="card">
      <div className="card-header">
        <div>
          <h3 className="card-title">{title}</h3>
          {subtitle && <p className="card-subtitle">{subtitle}</p>}
        </div>
        {actions && <div>{actions}</div>}
      </div>
      <div>{children}</div>
      {note && <div className="chart-note">{note}</div>}
    </section>
  );
}
