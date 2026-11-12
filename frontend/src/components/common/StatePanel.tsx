import { AlertTriangle, Info, RefreshCw, ShieldAlert } from 'lucide-react';
import type { ReactNode } from 'react';

export function LoadingState({ message = 'Loading live analytics from FootIntel API...' }: { message?: string }) {
  return (
    <div className="state-box" role="status" aria-live="polite">
      <div className="spinner" aria-hidden="true" />
      <div style={{ color: 'var(--text-secondary)', fontSize: 13.5 }}>{message}</div>
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="state-box" role="alert">
      <ShieldAlert size={28} color="#f43f5e" aria-hidden="true" />
      <div style={{ fontWeight: 700, fontSize: 15 }}>Unable to Load Backend Data</div>
      <div style={{ color: 'var(--text-secondary)', fontSize: 13, maxWidth: 520 }}>{message}</div>
      {onRetry && (
        <button type="button" className="btn btn-accent" onClick={onRetry}>
          <RefreshCw size={14} /> Retry Request
        </button>
      )}
    </div>
  );
}

export function EmptyState({
  message = 'No records match your current filter selection.',
  action,
}: {
  message?: string;
  action?: ReactNode;
}) {
  return (
    <div className="state-box">
      <Info size={24} color="#64748b" aria-hidden="true" />
      <div style={{ color: 'var(--text-secondary)', fontSize: 13.5 }}>{message}</div>
      {action}
    </div>
  );
}

export function WarningBanner({
  tone = 'warning',
  title,
  children,
}: {
  tone?: 'warning' | 'info' | 'danger';
  title: string;
  children: ReactNode;
}) {
  return (
    <div className={`banner banner-${tone}`} role="note">
      <AlertTriangle size={18} style={{ flexShrink: 0, marginTop: 2 }} aria-hidden="true" />
      <div>
        <strong style={{ display: 'block', marginBottom: 2 }}>{title}</strong>
        <span>{children}</span>
      </div>
    </div>
  );
}
