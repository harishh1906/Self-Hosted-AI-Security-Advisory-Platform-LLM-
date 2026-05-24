// ── Model Intelligence Page ──

import { Cpu, ArrowUpRight, ArrowDownRight, Zap, ShieldCheck } from 'lucide-react';

import { useModelHealth, useOptimizationInsights } from '../hooks/useQueries';
import { formatNumber, formatLatency, relativeTime, SLA_THRESHOLD_MS } from '../utils/formatters';

export default function ModelsPage() {
  const { data: models, isLoading } = useModelHealth();
  const { data: insights } = useOptimizationInsights();

  if (isLoading) {
    return (
      <div className="page-header">
        <h2 className="page-title">Model Intelligence</h2>
        <p className="page-subtitle">Loading model data...</p>
      </div>
    );
  }

  return (
    <>
      <div className="page-header">
        <h2 className="page-title">Model Intelligence</h2>
        <p className="page-subtitle">Per-model health, confidence trends, SLA compliance, and optimization insights</p>
      </div>

      {/* Per-model detail cards */}
      {models && models.length > 0 ? (
        models.map((m) => {
          const trend = m.confidence_trend;
          const slaRate = m.usage_count > 0 ? (m.sla_violations / m.usage_count) * 100 : 0;

          return (
            <div key={m.model_name} className="card" style={{ marginBottom: 'var(--space-lg)' }}>
              <div className="card-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <Cpu size={20} style={{ color: 'var(--brand-primary-light)' }} />
                  <span className="tag primary" style={{ fontSize: 'var(--font-size-base)' }}>{m.model_name}</span>
                  <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)' }}>Last used: {relativeTime(m.last_used_at)}</span>
                </div>
                {trend?.is_declining ? (
                  <span className="status-badge degraded"><ArrowDownRight size={12} /> Confidence Declining</span>
                ) : (
                  <span className="status-badge healthy"><ArrowUpRight size={12} /> Healthy</span>
                )}
              </div>

              <div className="grid grid-4" style={{ marginTop: 'var(--space-md)' }}>
                <div className="metric-card">
                  <div className="metric-label">Total Requests</div>
                  <div className="metric-value">{formatNumber(m.usage_count)}</div>
                </div>
                <div className="metric-card">
                  <div className="metric-label">Avg Latency</div>
                  <div className={`metric-value ${m.avg_latency_ms > SLA_THRESHOLD_MS ? 'danger' : ''}`}>{formatLatency(m.avg_latency_ms)}</div>
                  <div className="metric-subtext">SLA: {formatLatency(SLA_THRESHOLD_MS)}</div>
                </div>
                <div className="metric-card">
                  <div className="metric-label">SLA Violations</div>
                  <div className={`metric-value ${m.sla_violations > 0 ? 'danger' : 'success'}`}>{m.sla_violations}</div>
                  <div className="metric-subtext">{slaRate.toFixed(1)}% of requests</div>
                </div>
                <div className="metric-card">
                  <div className="metric-label">Confidence</div>
                  <div className="metric-value">{trend ? `${(trend.recent_avg * 100).toFixed(0)}%` : '—'}</div>
                  {trend && <div className="metric-subtext">{trend.is_declining ? `↓ ${trend.drop_percent.toFixed(1)}%` : '↑ Stable'} ({trend.sample_count} samples)</div>}
                </div>
              </div>

              <div className="grid grid-3" style={{ marginTop: 'var(--space-md)' }}>
                <div className="metric-card">
                  <div className="metric-label"><Zap size={14} /> Fallback Count</div>
                  <div className="metric-value">{m.fallback_count}</div>
                </div>
                <div className="metric-card">
                  <div className="metric-label"><ShieldCheck size={14} /> Drift Adjustments</div>
                  <div className="metric-value">{m.drift_adjustments}</div>
                  <div className="metric-subtext">{(m.drift_adjustment_rate * 100).toFixed(2)}% rate</div>
                </div>
                <div className="metric-card">
                  <div className="metric-label">Drift Adj. Rate</div>
                  <div className="pct-bar-container" style={{ marginTop: 12 }}>
                    <div className={`pct-bar-fill ${m.drift_adjustment_rate > 0.05 ? 'danger' : 'success'}`} style={{ width: `${Math.min(m.drift_adjustment_rate * 100, 100)}%` }} />
                  </div>
                </div>
              </div>
            </div>
          );
        })
      ) : (
        <div className="card" style={{ textAlign: 'center', padding: 'var(--space-2xl)', color: 'var(--text-tertiary)' }}>
          No model data yet. Send requests to /analyze to populate metrics.
        </div>
      )}

      {/* Top Performing Models Table */}
      {insights?.top_performing_models && insights.top_performing_models.length > 0 && (
        <div className="card section-gap">
          <div className="card-header">
            <div className="card-title">Top Performing Models (30d)</div>
          </div>
          <table className="data-table">
            <thead>
              <tr>
                <th>Rank</th>
                <th>Model</th>
                <th>Avg Latency</th>
                <th>Success Rate</th>
                <th>Requests</th>
                <th>Score</th>
              </tr>
            </thead>
            <tbody>
              {insights.top_performing_models.map((m) => (
                <tr key={m.model_name}>
                  <td className="mono">#{m.rank}</td>
                  <td><span className="tag primary">{m.model_name}</span></td>
                  <td className="mono">{formatLatency(m.avg_latency_ms)}</td>
                  <td className="mono">{(m.success_rate * 100).toFixed(1)}%</td>
                  <td className="mono">{formatNumber(m.total_requests)}</td>
                  <td className="mono">{(m.performance_score * 100).toFixed(0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Model Selection Decision Chain */}
      {insights?.model_selection_decision_chains && insights.model_selection_decision_chains.length > 0 && (
        <div className="card section-gap">
          <div className="card-header">
            <div className="card-title">Recent Model Selection Decisions</div>
            <span className="tag">Last {insights.model_selection_decision_chains.length}</span>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Org</th>
                  <th>Model Used</th>
                  <th>Fallback?</th>
                  <th>Latency</th>
                  <th>Confidence</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {insights.model_selection_decision_chains.slice(0, 20).map((chain) => (
                  <tr key={chain.correlation_id}>
                    <td className="mono" style={{ fontSize: 'var(--font-size-xs)' }}>
                      {new Date(chain.timestamp).toLocaleTimeString()}
                    </td>
                    <td><span className="tag">{chain.org_id}</span></td>
                    <td><span className="tag primary">{chain.actual_model_used}</span></td>
                    <td>{chain.used_fallback ? <span className="tag warning">Yes</span> : <span className="tag success">No</span>}</td>
                    <td className="mono">{chain.response_time_ms ? formatLatency(chain.response_time_ms) : '—'}</td>
                    <td className="mono">{chain.model_confidence ? `${(chain.model_confidence * 100).toFixed(0)}%` : '—'}</td>
                    <td style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {chain.decision_reason || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}
