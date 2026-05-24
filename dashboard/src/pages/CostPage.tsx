// ── Cost & Token Economics Page ──

import { DollarSign, Coins, FileText, TrendingUp, Zap } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { useOptimizationInsights, usePolicyEffectiveness } from '../hooks/useQueries';
import { formatNumber, formatLatency } from '../utils/formatters';

export default function CostPage() {
  const { data: insights, isLoading: insightsLoading } = useOptimizationInsights();
  const { data: policies, isLoading: policiesLoading } = usePolicyEffectiveness();

  const isLoading = insightsLoading || policiesLoading;

  // Aggregate token and latency stats across all policies from insights
  const policyPerf = insights?.policy_profile_effectiveness ?? [];
  const totalRequests = policyPerf.reduce((s, p) => s + p.request_count, 0);
  const avgConfidence = policyPerf.length > 0
    ? policyPerf.filter(p => p.avg_confidence != null).reduce((s, p) => s + (p.avg_confidence ?? 0), 0) /
      Math.max(policyPerf.filter(p => p.avg_confidence != null).length, 1)
    : null;
  const avgLatency = policyPerf.length > 0
    ? policyPerf.reduce((s, p) => s + p.avg_latency_ms, 0) / policyPerf.length
    : null;

  // Chart: requests per policy
  const policyChartData = policyPerf
    .sort((a, b) => b.request_count - a.request_count)
    .slice(0, 8)
    .map((p) => ({
      name: `Policy ${p.policy_id}`,
      requests: p.request_count,
      latency: Math.round(p.avg_latency_ms),
      confidence: p.avg_confidence != null ? Math.round(p.avg_confidence * 100) : 0,
    }));

  // Drift trend summary
  const driftTrend = insights?.drift_adjustment_trends;
  const fallback = insights?.fallback_usage_stats;

  if (isLoading) {
    return (
      <>
        <div className="page-header">
          <h2 className="page-title">Cost & Token Economics</h2>
          <p className="page-subtitle">Loading analytics…</p>
        </div>
        <div className="grid grid-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="metric-card">
              <div className="skeleton" style={{ width: '50%', height: 12, marginBottom: 12 }} />
              <div className="skeleton" style={{ width: '70%', height: 32 }} />
            </div>
          ))}
        </div>
      </>
    );
  }

  return (
    <>
      <div className="page-header">
        <h2 className="page-title">Cost & Token Economics</h2>
        <p className="page-subtitle">Policy-level request volume, latency economics, drift costs, and performance analytics</p>
      </div>

      {/* KPI Row */}
      <div className="grid grid-4">
        <div className="metric-card">
          <div className="metric-label"><FileText size={14} />Total Requests (30d)</div>
          <div className="metric-value">{formatNumber(totalRequests)}</div>
          <div className="metric-subtext">across {policyPerf.length} policies</div>
        </div>
        <div className="metric-card">
          <div className="metric-label"><TrendingUp size={14} />Avg Confidence</div>
          <div className="metric-value">{avgConfidence != null ? `${(avgConfidence * 100).toFixed(0)}%` : '—'}</div>
          <div className="metric-subtext">across all policies</div>
        </div>
        <div className="metric-card">
          <div className="metric-label"><Zap size={14} />Avg Latency</div>
          <div className="metric-value">{avgLatency != null ? formatLatency(avgLatency) : '—'}</div>
          <div className="metric-subtext">per request</div>
        </div>
        <div className="metric-card">
          <div className="metric-label"><DollarSign size={14} />Drift Events (30d)</div>
          <div className={`metric-value ${(driftTrend?.total_drift_events ?? 0) > 0 ? 'warning' : 'success'}`}>
            {driftTrend ? formatNumber(driftTrend.total_drift_events) : '—'}
          </div>
          <div className="metric-subtext">{driftTrend ? `${driftTrend.avg_events_per_day.toFixed(1)}/day avg` : ''}</div>
        </div>
      </div>

      {/* On-prem note */}
      <div className="card section-gap" style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-md)', padding: 'var(--space-md) var(--space-lg)' }}>
        <Coins size={28} style={{ color: 'var(--brand-primary-light)', flexShrink: 0 }} />
        <div>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>On-premises LLM — No direct token cost</div>
          <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-tertiary)' }}>
            Virtue-AI runs Gemma 4 e2b locally via Ollama. Token cost is server compute (electricity + hardware depreciation).
            Connect governance endpoints with <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--brand-primary-light)', fontSize: 'var(--font-size-xs)' }}>org_id</code> to view per-org token volumes from <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--brand-primary-light)', fontSize: 'var(--font-size-xs)' }}>/api/v1/ai/governance/policy-cost-summary</code>.
          </div>
        </div>
      </div>

      {/* Policy request volume chart */}
      {policyChartData.length > 0 && (
        <div className="card section-gap">
          <div className="card-header">
            <div className="card-title"><FileText size={16} />Requests by Policy Configuration</div>
            <span className="tag">{policyPerf.length} policies · 30 days</span>
          </div>
          <div className="chart-container">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={policyChartData} barSize={36}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis />
                <Tooltip contentStyle={{ background: '#1a1a35', border: '1px solid rgba(99,102,241,0.2)', borderRadius: 8 }} />
                <Bar dataKey="requests" radius={[6, 6, 0, 0]}>
                  {policyChartData.map((_, i) => (
                    <Cell key={i} fill={`hsl(${255 + i * 20}, 70%, 60%)`} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Policy effectiveness table */}
      {policies && policies.length > 0 && (
        <div className="card section-gap">
          <div className="card-header">
            <div className="card-title"><TrendingUp size={16} />Policy Effectiveness & Cost Drivers</div>
          </div>
          <table className="data-table">
            <thead>
              <tr>
                <th>Policy ID</th>
                <th>Org</th>
                <th>Requests</th>
                <th>Avg Confidence</th>
                <th>Avg Latency</th>
                <th>Drift Freq</th>
                <th>Tenant Rating</th>
              </tr>
            </thead>
            <tbody>
              {policies.map((p) => (
                <tr key={`${p.policy_id}-${p.org_id}`}>
                  <td className="mono">{p.policy_id}</td>
                  <td><span className="tag">{p.org_id}</span></td>
                  <td className="mono">{formatNumber(p.request_count)}</td>
                  <td className="mono">{p.avg_confidence != null ? `${(p.avg_confidence * 100).toFixed(0)}%` : '—'}</td>
                  <td className="mono">{p.avg_latency != null ? formatLatency(p.avg_latency) : '—'}</td>
                  <td>
                    <span className={`tag ${p.drift_frequency > 0.05 ? 'danger' : p.drift_frequency > 0 ? 'warning' : 'success'}`}>
                      {(p.drift_frequency * 100).toFixed(2)}%
                    </span>
                  </td>
                  <td className="mono">{p.tenant_rating_average != null ? `${p.tenant_rating_average.toFixed(1)} ★` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Fallback cost summary */}
      {fallback && (
        <div className="card section-gap">
          <div className="card-header">
            <div className="card-title"><Zap size={16} />Fallback & Drift Cost (30d)</div>
          </div>
          <div className="grid grid-3">
            <div className="metric-card">
              <div className="metric-label">Total Fallbacks</div>
              <div className={`metric-value ${fallback.total_fallbacks > 0 ? 'warning' : 'success'}`}>
                {formatNumber(fallback.total_fallbacks)}
              </div>
              <div className="metric-subtext">of {formatNumber(fallback.total_requests)} requests</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">Overall Fallback Rate</div>
              <div className={`metric-value ${fallback.overall_fallback_rate > 0.05 ? 'danger' : fallback.overall_fallback_rate > 0 ? 'warning' : 'success'}`}>
                {(fallback.overall_fallback_rate * 100).toFixed(2)}%
              </div>
              <div className="metric-subtext">Each fallback = extra inference cost</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">Avg Drift Events/Day</div>
              <div className={`metric-value ${(driftTrend?.avg_events_per_day ?? 0) > 1 ? 'warning' : 'success'}`}>
                {driftTrend?.avg_events_per_day.toFixed(1) ?? '—'}
              </div>
              <div className="metric-subtext">confidence adjustments</div>
            </div>
          </div>
        </div>
      )}

      {/* Top performing models */}
      {insights?.top_performing_models && insights.top_performing_models.length > 0 && (
        <div className="card section-gap">
          <div className="card-header">
            <div className="card-title"><TrendingUp size={16} />Top Performing Models (30d)</div>
          </div>
          <table className="data-table">
            <thead>
              <tr><th>Rank</th><th>Model</th><th>Avg Latency</th><th>Success Rate</th><th>Total Requests</th><th>Performance Score</th></tr>
            </thead>
            <tbody>
              {insights.top_performing_models.map((m) => (
                <tr key={m.model_name}>
                  <td className="mono">#{m.rank}</td>
                  <td><span className="tag primary">{m.model_name}</span></td>
                  <td className="mono">{formatLatency(m.avg_latency_ms)}</td>
                  <td className="mono">{(m.success_rate * 100).toFixed(1)}%</td>
                  <td className="mono">{formatNumber(m.total_requests)}</td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <div style={{ flex: 1, height: 4, background: 'var(--bg-surface)', borderRadius: 2, maxWidth: 80 }}>
                        <div style={{ width: `${m.performance_score * 100}%`, height: '100%', background: 'var(--brand-primary)', borderRadius: 2 }} />
                      </div>
                      <span className="mono" style={{ fontSize: 'var(--font-size-xs)' }}>{(m.performance_score * 100).toFixed(0)}</span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
