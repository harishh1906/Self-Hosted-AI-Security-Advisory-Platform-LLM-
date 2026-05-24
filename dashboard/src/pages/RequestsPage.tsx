// ── Requests & Load Page ──

import { Activity, CheckCircle2, XCircle, AlertTriangle, RotateCcw } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { useMetrics } from '../hooks/useQueries';
import { formatNumber, formatPercent } from '../utils/formatters';

export default function RequestsPage() {
  const { data, isLoading } = useMetrics();

  if (isLoading || !data) {
    return (
      <div className="page-header">
        <h2 className="page-title">Requests & Load</h2>
        <p className="page-subtitle">Loading metrics...</p>
      </div>
    );
  }

  const total = data.requests_total;
  const barData = [
    { name: 'Success', value: data.success_count, color: '#10b981' },
    { name: 'Failed', value: data.failures_total, color: '#ef4444' },
    { name: 'Degraded', value: data.degraded_total, color: '#f59e0b' },
    { name: 'Fallback', value: data.fallback_count, color: '#6366f1' },
  ];

  const kpis = [
    { label: 'Total Requests', value: total, icon: Activity, color: '' },
    { label: 'Success Rate', value: total > 0 ? `${((data.success_count / total) * 100).toFixed(1)}%` : '—', icon: CheckCircle2, color: 'success' },
    { label: 'Failure Rate', value: total > 0 ? `${((data.failures_total / total) * 100).toFixed(1)}%` : '—', icon: XCircle, color: data.failures_total > 0 ? 'danger' : '' },
    { label: 'Degradation Rate', value: total > 0 ? `${((data.degraded_total / total) * 100).toFixed(1)}%` : '—', icon: AlertTriangle, color: data.degraded_total > 0 ? 'warning' : '' },
    { label: 'Fallback Rate', value: total > 0 ? `${((data.fallback_count / total) * 100).toFixed(1)}%` : '—', icon: RotateCcw, color: '' },
  ];

  return (
    <>
      <div className="page-header">
        <h2 className="page-title">Requests & Load</h2>
        <p className="page-subtitle">Request counters, success/failure rates, and load analysis</p>
      </div>

      <div className="grid grid-5">
        {kpis.map((k) => {
          const Icon = k.icon;
          return (
            <div key={k.label} className="metric-card">
              <div className="metric-label"><Icon size={14} /> {k.label}</div>
              <div className={`metric-value ${k.color}`}>{typeof k.value === 'number' ? formatNumber(k.value) : k.value}</div>
            </div>
          );
        })}
      </div>

      <div className="card section-gap">
        <div className="card-header">
          <div className="card-title"><Activity size={16} /> Request Distribution</div>
        </div>
        <div className="chart-container">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={barData} barSize={48}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="name" />
              <YAxis />
              <Tooltip contentStyle={{ background: '#1a1a35', border: '1px solid rgba(99,102,241,0.2)', borderRadius: 8 }} />
              <Bar dataKey="value" radius={[8, 8, 0, 0]}>
                {barData.map((entry, i) => (
                  <Cell key={i} fill={entry.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Detailed breakdown table */}
      <div className="card section-gap">
        <div className="card-header">
          <div className="card-title">Detailed Breakdown</div>
        </div>
        <table className="data-table">
          <thead>
            <tr>
              <th>Metric</th>
              <th>Count</th>
              <th>% of Total</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {[
              { name: 'Successful Requests', count: data.success_count, tagClass: 'success' },
              { name: 'Failed Requests', count: data.failures_total, tagClass: data.failures_total > 0 ? 'danger' : '' },
              { name: 'Degraded Requests', count: data.degraded_total, tagClass: data.degraded_total > 0 ? 'warning' : '' },
              { name: 'Fallback Events', count: data.fallback_count, tagClass: data.fallback_count > 0 ? 'warning' : '' },
            ].map((row) => (
              <tr key={row.name}>
                <td>{row.name}</td>
                <td className="mono">{formatNumber(row.count)}</td>
                <td className="mono">{formatPercent(row.count, total)}</td>
                <td><span className={`tag ${row.tagClass}`}>{row.count === 0 ? 'Clean' : row.tagClass === 'success' ? 'OK' : 'Alert'}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
