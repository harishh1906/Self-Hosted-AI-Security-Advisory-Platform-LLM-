// ── Latency & Performance Page ──

import { Timer, Gauge } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Cell } from 'recharts';
import { useMetrics } from '../hooks/useQueries';
import { formatLatency, SLA_THRESHOLD_MS } from '../utils/formatters';

export default function LatencyPage() {
  const { data } = useMetrics();

  if (!data) {
    return (
      <div className="page-header">
        <h2 className="page-title">Latency & Performance</h2>
        <p className="page-subtitle">Loading...</p>
      </div>
    );
  }

  const percentiles = [
    { label: 'P50', value: data.p50_latency_ms, color: '#6366f1', desc: 'Median response time' },
    { label: 'P95', value: data.p95_latency_ms, color: '#06b6d4', desc: '95th percentile' },
    { label: 'P99', value: data.p99_latency_ms, color: '#f59e0b', desc: '99th percentile' },
  ];

  const allLatency = [
    { name: 'Min', value: data.min_latency_ms ?? 0, color: '#10b981' },
    { name: 'Avg', value: data.avg_latency_ms, color: '#3b82f6' },
    { name: 'P50', value: data.p50_latency_ms, color: '#6366f1' },
    { name: 'P95', value: data.p95_latency_ms, color: '#06b6d4' },
    { name: 'P99', value: data.p99_latency_ms, color: '#f59e0b' },
    { name: 'Max', value: data.max_latency_ms ?? 0, color: '#ef4444' },
  ];

  return (
    <>
      <div className="page-header">
        <h2 className="page-title">Latency & Performance</h2>
        <p className="page-subtitle">Response time percentiles, SLA compliance, and performance distribution</p>
      </div>

      {/* Big Percentile Cards */}
      <div className="grid grid-3">
        {percentiles.map((p) => (
          <div key={p.label} className="metric-card" style={{ textAlign: 'center' }}>
            <div className="metric-label" style={{ justifyContent: 'center' }}>
              <Gauge size={14} /> {p.label} — {p.desc}
            </div>
            <div className="metric-value" style={{
              fontSize: 'var(--font-size-3xl)',
              color: p.value > SLA_THRESHOLD_MS ? 'var(--color-danger)' : p.color,
              WebkitTextFillColor: p.value > SLA_THRESHOLD_MS ? 'var(--color-danger)' : p.color,
              background: 'none',
            }}>
              {formatLatency(p.value)}
            </div>
            {p.value > SLA_THRESHOLD_MS && (
              <div style={{ marginTop: 8 }}>
                <span className="tag danger">Exceeds SLA ({formatLatency(SLA_THRESHOLD_MS)})</span>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Full Distribution Bar Chart */}
      <div className="card section-gap">
        <div className="card-header">
          <div className="card-title"><Timer size={16} /> Latency Distribution</div>
          <span className="tag">SLA Threshold: {formatLatency(SLA_THRESHOLD_MS)}</span>
        </div>
        <div className="chart-container">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={allLatency} barSize={48}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="name" />
              <YAxis tickFormatter={(v: number) => formatLatency(v)} />
              <Tooltip
                contentStyle={{ background: '#1a1a35', border: '1px solid rgba(99,102,241,0.2)', borderRadius: 8 }}
                formatter={((v: number) => [formatLatency(v), 'Latency']) as never}
              />
              <ReferenceLine y={SLA_THRESHOLD_MS} stroke="#ef4444" strokeDasharray="4 4" label={{ value: `SLA ${formatLatency(SLA_THRESHOLD_MS)}`, fill: '#ef4444', fontSize: 11, position: 'right' }} />
              <Bar dataKey="value" radius={[8, 8, 0, 0]}>
                {allLatency.map((entry, i) => (
                  <Cell key={i} fill={entry.value > SLA_THRESHOLD_MS ? '#ef4444' : entry.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Stats Table */}
      <div className="card section-gap">
        <div className="card-header">
          <div className="card-title">Latency Statistics</div>
          <span className="tag">{data.latency_sample_count ?? 0} samples</span>
        </div>
        <table className="data-table">
          <thead>
            <tr><th>Metric</th><th>Value</th><th>vs SLA</th></tr>
          </thead>
          <tbody>
            {allLatency.map((row) => (
              <tr key={row.name}>
                <td>{row.name}</td>
                <td className="mono">{formatLatency(row.value)}</td>
                <td>
                  {row.value <= SLA_THRESHOLD_MS
                    ? <span className="tag success">✓ Within</span>
                    : <span className="tag danger">✗ Exceeds by {formatLatency(row.value - SLA_THRESHOLD_MS)}</span>
                  }
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
