// ── Organizations Page — Per-org analytics derived from decision chains ──

import { useMemo, useState } from 'react';
import { Building2, Activity, Zap, TrendingUp, ShieldAlert, Search } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { useOptimizationInsights, usePolicyEffectiveness } from '../hooks/useQueries';
import { formatNumber, formatLatency } from '../utils/formatters';

interface OrgStat {
  org_id: string;
  requests: number;
  fallbacks: number;
  fallback_rate: number;
  avg_latency_ms: number;
  avg_confidence: number | null;
}

export default function OrgsPage() {
  const { data: insights, isLoading } = useOptimizationInsights();
  const { data: policies } = usePolicyEffectiveness();
  const [search, setSearch] = useState('');

  // Build per-org stats from decision chains
  const orgStats: OrgStat[] = useMemo(() => {
    const chains = insights?.model_selection_decision_chains ?? [];
    const map = new Map<string, { requests: number; fallbacks: number; totalLatency: number; totalConf: number; confCount: number }>();

    for (const chain of chains) {
      const s = map.get(chain.org_id) ?? { requests: 0, fallbacks: 0, totalLatency: 0, totalConf: 0, confCount: 0 };
      s.requests++;
      if (chain.used_fallback) s.fallbacks++;
      if (chain.response_time_ms) s.totalLatency += chain.response_time_ms;
      if (chain.model_confidence != null) { s.totalConf += chain.model_confidence; s.confCount++; }
      map.set(chain.org_id, s);
    }

    return Array.from(map.entries())
      .map(([org_id, s]) => ({
        org_id,
        requests: s.requests,
        fallbacks: s.fallbacks,
        fallback_rate: s.requests > 0 ? s.fallbacks / s.requests : 0,
        avg_latency_ms: s.requests > 0 ? s.totalLatency / s.requests : 0,
        avg_confidence: s.confCount > 0 ? s.totalConf / s.confCount : null,
      }))
      .sort((a, b) => b.requests - a.requests);
  }, [insights]);

  // Per-org policy effectiveness (from separate endpoint)
  const orgPolicies = useMemo(() => {
    if (!policies) return {};
    const map: Record<string, typeof policies> = {};
    for (const p of policies) {
      if (!map[p.org_id]) map[p.org_id] = [];
      map[p.org_id].push(p);
    }
    return map;
  }, [policies]);

  if (isLoading) {
    return (
      <>
        <div className="page-header">
          <h2 className="page-title">Organizations</h2>
          <p className="page-subtitle">Loading org data…</p>
        </div>
        <div className="grid grid-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="metric-card">
              <div className="skeleton" style={{ width: '50%', height: 12, marginBottom: 12 }} />
              <div className="skeleton" style={{ width: '70%', height: 32 }} />
            </div>
          ))}
        </div>
      </>
    );
  }

  if (orgStats.length === 0) {
    return (
      <>
        <div className="page-header">
          <h2 className="page-title">Organizations</h2>
          <p className="page-subtitle">Multi-tenant view — per-org request volume, success rates, and latency</p>
        </div>
        <div className="card" style={{ textAlign: 'center', padding: 'var(--space-2xl)' }}>
          <Building2 size={48} style={{ color: 'var(--text-tertiary)', marginBottom: 16, display: 'block', margin: '0 auto var(--space-md)' }} />
          <h3 style={{ color: 'var(--text-secondary)', marginBottom: 8 }}>No organization data yet</h3>
          <p style={{ color: 'var(--text-tertiary)', fontSize: 'var(--font-size-sm)', maxWidth: 480, margin: '0 auto' }}>
            Organization metrics populate as different org_ids send requests to /analyze.
            Each org's request volume, fallback rate, latency, and confidence will appear here.
          </p>
        </div>
      </>
    );
  }

  const filteredOrgs = search.trim()
    ? orgStats.filter(o => o.org_id.toLowerCase().includes(search.trim().toLowerCase()))
    : orgStats;

  const totalRequests = orgStats.reduce((s, o) => s + o.requests, 0);
  const chartData = orgStats.slice(0, 10).map((o) => ({
    name: o.org_id.length > 14 ? o.org_id.slice(0, 12) + '…' : o.org_id,
    fullName: o.org_id,
    requests: o.requests,
  }));

  return (
    <>
      <div className="page-header">
        <h2 className="page-title">Organizations</h2>
        <p className="page-subtitle">Multi-tenant view — per-org request volume, fallback rates, latency, and confidence</p>
      </div>

      {/* Summary KPIs */}
      <div className="grid grid-4">
        <div className="metric-card">
          <div className="metric-label"><Building2 size={14} />Active Orgs</div>
          <div className="metric-value">{orgStats.length}</div>
          <div className="metric-subtext">last 30 days</div>
        </div>
        <div className="metric-card">
          <div className="metric-label"><Activity size={14} />Total Requests</div>
          <div className="metric-value">{formatNumber(totalRequests)}</div>
          <div className="metric-subtext">across all orgs</div>
        </div>
        <div className="metric-card">
          <div className="metric-label"><Zap size={14} />Avg Fallback Rate</div>
          <div className={`metric-value ${orgStats.some(o => o.fallback_rate > 0.1) ? 'warning' : ''}`}>
            {orgStats.length > 0
              ? `${(orgStats.reduce((s, o) => s + o.fallback_rate, 0) / orgStats.length * 100).toFixed(1)}%`
              : '—'}
          </div>
          <div className="metric-subtext">avg across orgs</div>
        </div>
        <div className="metric-card">
          <div className="metric-label"><TrendingUp size={14} />Avg Confidence</div>
          <div className="metric-value">
            {(() => {
              const orgsWithConf = orgStats.filter(o => o.avg_confidence != null);
              if (!orgsWithConf.length) return '—';
              const avg = orgsWithConf.reduce((s, o) => s + (o.avg_confidence ?? 0), 0) / orgsWithConf.length;
              return `${(avg * 100).toFixed(0)}%`;
            })()}
          </div>
          <div className="metric-subtext">avg confidence</div>
        </div>
      </div>

      {/* Requests by Org bar chart */}
      <div className="card section-gap">
        <div className="card-header">
          <div className="card-title"><Activity size={16} />Requests by Organization</div>
          <span className="tag">Top {Math.min(orgStats.length, 10)}</span>
        </div>
        <div className="chart-container">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} barSize={32}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
              <YAxis />
              <Tooltip
                contentStyle={{ background: '#1a1a35', border: '1px solid rgba(99,102,241,0.2)', borderRadius: 8 }}
                formatter={((v: any, name: any, props: any) => [formatNumber(Number(v) || 0), props.payload?.fullName ?? name]) as any}
              />
              <Bar dataKey="requests" radius={[6, 6, 0, 0]}>
                {chartData.map((_, i) => (
                  <Cell key={i} fill={`hsl(${240 + i * 15}, 70%, 65%)`} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Per-org detail table */}
      <div className="card section-gap">
        <div className="card-header">
          <div className="card-title"><ShieldAlert size={16} />Per-Organization Detail</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-sm)' }}>
            <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
              <Search size={12} style={{ position: 'absolute', left: 8, color: 'var(--text-tertiary)', pointerEvents: 'none' }} />
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Filter orgs…"
                style={{
                  paddingLeft: 26, paddingRight: 10, paddingTop: 6, paddingBottom: 6,
                  background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border-subtle)',
                  borderRadius: 8, color: 'var(--text-primary)', fontSize: 'var(--font-size-xs)',
                  outline: 'none', width: 140,
                }}
              />
            </div>
            <span className="tag">{filteredOrgs.length} of {orgStats.length} orgs</span>
          </div>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Organization</th>
                <th>Requests</th>
                <th>% of Total</th>
                <th>Fallbacks</th>
                <th>Fallback Rate</th>
                <th>Avg Latency</th>
                <th>Avg Confidence</th>
                <th>Policy Config</th>
              </tr>
            </thead>
            <tbody>
              {filteredOrgs.map((org) => {
                const pct = totalRequests > 0 ? (org.requests / totalRequests) * 100 : 0;
                const hasPolicies = orgPolicies[org.org_id]?.length ?? 0;
                return (
                  <tr key={org.org_id}>
                    <td><span className="tag primary">{org.org_id}</span></td>
                    <td className="mono">{formatNumber(org.requests)}</td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div style={{ flex: 1, height: 4, background: 'var(--bg-surface)', borderRadius: 2, maxWidth: 80 }}>
                          <div style={{ width: `${pct}%`, height: '100%', background: 'var(--brand-primary)', borderRadius: 2 }} />
                        </div>
                        <span className="mono">{pct.toFixed(1)}%</span>
                      </div>
                    </td>
                    <td className="mono">{org.fallbacks}</td>
                    <td>
                      <span className={`tag ${org.fallback_rate > 0.1 ? 'danger' : org.fallback_rate > 0 ? 'warning' : 'success'}`}>
                        {(org.fallback_rate * 100).toFixed(1)}%
                      </span>
                    </td>
                    <td className="mono">{formatLatency(org.avg_latency_ms)}</td>
                    <td className="mono">{org.avg_confidence != null ? `${(org.avg_confidence * 100).toFixed(0)}%` : '—'}</td>
                    <td><span className="tag">{hasPolicies} {hasPolicies === 1 ? 'policy' : 'policies'}</span></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
