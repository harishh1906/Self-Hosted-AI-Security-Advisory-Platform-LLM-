// ── Policy Governance Page ──

import { useMemo } from 'react';
import { ScrollText, ShieldCheck, TrendingUp, Zap, Star } from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, ReferenceLine,
} from 'recharts';
import { usePolicyEffectiveness } from '../hooks/useQueries';
import { formatNumber, formatLatency } from '../utils/formatters';

export default function PoliciesPage() {
  const { data, isLoading } = usePolicyEffectiveness();

  const stats = useMemo(() => {
    if (!data || data.length === 0) return null;
    const totalRequests = data.reduce((s, p) => s + p.request_count, 0);
    const withConf = data.filter(p => p.avg_confidence != null);
    const avgConf = withConf.length > 0
      ? withConf.reduce((s, p) => s + (p.avg_confidence ?? 0), 0) / withConf.length
      : null;
    const withLatency = data.filter(p => p.avg_latency != null);
    const avgLatency = withLatency.length > 0
      ? withLatency.reduce((s, p) => s + (p.avg_latency ?? 0), 0) / withLatency.length
      : null;
    const avgDrift = data.reduce((s, p) => s + p.drift_frequency, 0) / data.length;
    const withRating = data.filter(p => p.tenant_rating_average != null);
    const avgRating = withRating.length > 0
      ? withRating.reduce((s, p) => s + (p.tenant_rating_average ?? 0), 0) / withRating.length
      : null;
    return { totalRequests, avgConf, avgLatency, avgDrift, avgRating };
  }, [data]);

  // Chart data — confidence by policy
  const confChartData = useMemo(() => {
    if (!data) return [];
    return data
      .filter(p => p.avg_confidence != null)
      .sort((a, b) => (b.avg_confidence ?? 0) - (a.avg_confidence ?? 0))
      .slice(0, 10)
      .map(p => ({
        name: `P-${p.policy_id}`,
        fullName: `Policy ${p.policy_id} (${p.org_id})`,
        confidence: Math.round((p.avg_confidence ?? 0) * 100),
        drift: Math.round(p.drift_frequency * 100 * 100) / 100,
      }));
  }, [data]);

  // Chart data — drift frequency by policy
  const driftChartData = useMemo(() => {
    if (!data) return [];
    return data
      .sort((a, b) => b.drift_frequency - a.drift_frequency)
      .slice(0, 10)
      .map(p => ({
        name: `P-${p.policy_id}`,
        fullName: `Policy ${p.policy_id} (${p.org_id})`,
        drift: Math.round(p.drift_frequency * 10000) / 100,
      }));
  }, [data]);

  if (isLoading) {
    return (
      <>
        <div className="page-header">
          <h2 className="page-title">Policy Governance</h2>
          <p className="page-subtitle">Loading policy data…</p>
        </div>
        <div className="grid grid-4">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="metric-card">
              <div className="skeleton" style={{ width: '50%', height: 12, marginBottom: 12 }} />
              <div className="skeleton" style={{ width: '70%', height: 32 }} />
            </div>
          ))}
        </div>
      </>
    );
  }

  if (!data || data.length === 0) {
    return (
      <>
        <div className="page-header">
          <h2 className="page-title">Policy Governance</h2>
          <p className="page-subtitle">Policy effectiveness, confidence trends, drift frequency, and tenant satisfaction</p>
        </div>
        <div className="card" style={{ textAlign: 'center', padding: 'var(--space-2xl)' }}>
          <ScrollText size={48} style={{ color: 'var(--text-tertiary)', marginBottom: 16, display: 'block', margin: '0 auto var(--space-md)' }} />
          <h3 style={{ color: 'var(--text-secondary)', marginBottom: 8 }}>No policy data yet</h3>
          <p style={{ color: 'var(--text-tertiary)', fontSize: 'var(--font-size-sm)', maxWidth: 480, margin: '0 auto' }}>
            Policy effectiveness data populates as organizations configure AI policy profiles
            and send requests through the advisory pipeline.
          </p>
        </div>
      </>
    );
  }

  return (
    <>
      <div className="page-header">
        <h2 className="page-title">Policy Governance</h2>
        <p className="page-subtitle">Policy effectiveness, confidence trends, drift frequency, and tenant satisfaction</p>
      </div>

      {/* KPI Row */}
      <div className="grid grid-4">
        <div className="metric-card">
          <div className="metric-label"><ScrollText size={14} />Active Policies</div>
          <div className="metric-value">{data.length}</div>
          <div className="metric-subtext">{formatNumber(stats?.totalRequests ?? 0)} total requests</div>
        </div>
        <div className="metric-card">
          <div className="metric-label"><TrendingUp size={14} />Avg Confidence</div>
          <div className="metric-value">
            {stats?.avgConf != null ? `${(stats.avgConf * 100).toFixed(0)}%` : '—'}
          </div>
          <div className="metric-subtext">across all policies</div>
        </div>
        <div className="metric-card">
          <div className="metric-label"><Zap size={14} />Avg Latency</div>
          <div className="metric-value">
            {stats?.avgLatency != null ? formatLatency(stats.avgLatency) : '—'}
          </div>
          <div className="metric-subtext">per request</div>
        </div>
        <div className="metric-card">
          <div className="metric-label"><Star size={14} />Avg Tenant Rating</div>
          <div className="metric-value">
            {stats?.avgRating != null ? `${stats.avgRating.toFixed(1)} ★` : '—'}
          </div>
          <div className="metric-subtext">
            {stats?.avgDrift != null
              ? <span className={`tag ${stats.avgDrift > 0.05 ? 'danger' : stats.avgDrift > 0 ? 'warning' : 'success'}`}>
                  {(stats.avgDrift * 100).toFixed(2)}% avg drift
                </span>
              : null}
          </div>
        </div>
      </div>

      {/* Charts row */}
      {confChartData.length > 0 && (
        <div className="grid grid-2 section-gap">
          {/* Confidence by policy */}
          <div className="card">
            <div className="card-header">
              <div className="card-title"><TrendingUp size={16} />Confidence by Policy</div>
              <span className="tag">Top {confChartData.length}</span>
            </div>
            <div className="chart-container sm">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={confChartData} barSize={28} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fontSize: 10 }} />
                  <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={40} />
                  <Tooltip
                    contentStyle={{ background: '#1a1a35', border: '1px solid rgba(99,102,241,0.2)', borderRadius: 8 }}
                    formatter={((v: number, _: string, props: any) => [`${v}%`, props.payload?.fullName]) as any}
                  />
                  <ReferenceLine x={50} stroke="#f59e0b" strokeDasharray="4 4" />
                  <Bar dataKey="confidence" radius={[0, 4, 4, 0]}>
                    {confChartData.map((entry, i) => (
                      <Cell key={i} fill={entry.confidence >= 70 ? '#10b981' : entry.confidence >= 50 ? '#f59e0b' : '#ef4444'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Drift frequency by policy */}
          <div className="card">
            <div className="card-header">
              <div className="card-title"><ShieldCheck size={16} />Drift Frequency by Policy</div>
              <span className="tag">Top {driftChartData.length}</span>
            </div>
            <div className="chart-container sm">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={driftChartData} barSize={28} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tickFormatter={v => `${v}%`} tick={{ fontSize: 10 }} />
                  <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={40} />
                  <Tooltip
                    contentStyle={{ background: '#1a1a35', border: '1px solid rgba(99,102,241,0.2)', borderRadius: 8 }}
                    formatter={((v: number, _: string, props: any) => [`${v}%`, props.payload?.fullName]) as any}
                  />
                  <ReferenceLine x={5} stroke="#ef4444" strokeDasharray="4 4" label={{ value: '5% threshold', fill: '#ef4444', fontSize: 10 }} />
                  <Bar dataKey="drift" radius={[0, 4, 4, 0]}>
                    {driftChartData.map((entry, i) => (
                      <Cell key={i} fill={entry.drift > 5 ? '#ef4444' : entry.drift > 0 ? '#f59e0b' : '#10b981'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      {/* Full policy table */}
      <div className="card section-gap">
        <div className="card-header">
          <div className="card-title"><ScrollText size={16} />Policy Effectiveness (30d)</div>
          <span className="tag">{data.length} {data.length === 1 ? 'policy' : 'policies'}</span>
        </div>
        <div style={{ overflowX: 'auto' }}>
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
              {data
                .slice()
                .sort((a, b) => b.request_count - a.request_count)
                .map(p => (
                  <tr key={`${p.policy_id}-${p.org_id}`}>
                    <td className="mono">
                      <span className="tag primary">P-{p.policy_id}</span>
                    </td>
                    <td><span className="tag">{p.org_id}</span></td>
                    <td className="mono">{formatNumber(p.request_count)}</td>
                    <td>
                      {p.avg_confidence != null ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <div style={{ flex: 1, height: 4, background: 'var(--bg-surface)', borderRadius: 2, maxWidth: 60 }}>
                            <div style={{
                              width: `${Math.min(p.avg_confidence * 100, 100)}%`,
                              height: '100%',
                              background: p.avg_confidence >= 0.7 ? 'var(--color-success)' : p.avg_confidence >= 0.5 ? 'var(--color-warning)' : 'var(--color-danger)',
                              borderRadius: 2,
                            }} />
                          </div>
                          <span className="mono">{(p.avg_confidence * 100).toFixed(0)}%</span>
                        </div>
                      ) : '—'}
                    </td>
                    <td className="mono">{p.avg_latency != null ? formatLatency(p.avg_latency) : '—'}</td>
                    <td>
                      <span className={`tag ${p.drift_frequency > 0.05 ? 'danger' : p.drift_frequency > 0 ? 'warning' : 'success'}`}>
                        {(p.drift_frequency * 100).toFixed(2)}%
                      </span>
                    </td>
                    <td className="mono">
                      {p.tenant_rating_average != null ? (
                        <span style={{ color: p.tenant_rating_average >= 4 ? 'var(--color-success)' : p.tenant_rating_average >= 3 ? 'var(--color-warning)' : 'var(--color-danger)' }}>
                          {p.tenant_rating_average.toFixed(1)} ★
                        </span>
                      ) : '—'}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
