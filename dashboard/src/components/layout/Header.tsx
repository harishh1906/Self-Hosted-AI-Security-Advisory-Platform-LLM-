// ── Header Bar ──

import { RefreshCw, Radio, WifiOff } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { useHealth } from '../../hooks/useQueries';
import { useSSE } from '../../hooks/useSSE';

export default function Header({ title }: { title: string }) {
  const queryClient = useQueryClient();
  const { data: health } = useHealth();
  const { connected: sseConnected } = useSSE();

  const overallStatus = health?.status || 'unknown';

  return (
    <header className="header">
      <h1 className="header-title">{title}</h1>
      <div className="header-actions">
        {/* SSE / Polling indicator */}
        <div
          className="header-badge"
          title={sseConnected ? 'Receiving live data via SSE stream' : 'SSE disconnected — falling back to REST polling'}
          style={{ gap: 6 }}
        >
          {sseConnected ? (
            <>
              <Radio size={13} style={{ color: 'var(--color-success)' }} />
              <span style={{ color: 'var(--color-success)', fontWeight: 600 }}>Live</span>
            </>
          ) : (
            <>
              <WifiOff size={13} style={{ color: 'var(--color-warning)' }} />
              <span style={{ color: 'var(--color-warning)', fontWeight: 600 }}>Polling</span>
            </>
          )}
        </div>

        {/* System health badge */}
        <div className="header-badge">
          <span
            className="pulse-dot"
            style={{
              background:
                overallStatus === 'ready'
                  ? 'var(--color-success)'
                  : overallStatus === 'unknown'
                  ? 'var(--color-warning)'
                  : 'var(--color-danger)',
            }}
          />
          {overallStatus === 'ready'
            ? 'All Systems Operational'
            : overallStatus === 'unknown'
            ? 'Connecting…'
            : 'Degraded'}
        </div>

        {/* Refresh */}
        <button
          className="header-badge"
          onClick={() => queryClient.invalidateQueries()}
          style={{ cursor: 'pointer', border: '1px solid var(--border-subtle)' }}
          title="Refresh all data"
        >
          <RefreshCw size={14} />
          Refresh
        </button>
      </div>
    </header>
  );
}
