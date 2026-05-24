// ── Drift & AI Quality Page ──

import { ShieldAlert, TrendingDown, RotateCcw, Award } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { useOptimizationInsights } from '../hooks/useQueries';
import { formatNumber, formatLatency } from '../utils/formatters';

export default function DriftPage() {
  const { data: insights, isLoading } = useOptimizationInsights();

  if (isLoading || !insights) {
    return (
      <div className="page-header">
        <h2 className="page-title">Drift & AI Quality</h2>
        <p className="page-subtitle">Loading drift data...</p>
      </div>
    );
  }

  const { drift_adjustment_trends, fallback_usage_stats } = insights;

  // Build drift timeline chart data
  const driftChartData = Object.entries(drift_adjustment_trends.events_by_date || {})
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, count]) => ({
      date: date.slice(5), // MM-DD
      events: count,
    }));

  return (
    <>
      <div className="page-header">
        <h2 className="page-title">Drift & AI Quality</h2>
        <p className="page-subtitle">AI output drift tracking, fallback analysis, and quality metrics</p>
      </div>

      {/* KPI Row */}
      <div className="grid grid-4">
        <div className="metric-card">
          <div className="metric-label"><TrendingDown size={14} /> Drift Events (30d)</div>
          <div className={`metric-value ${drift_adjustment_trends.total_drift_events > 0 ? 'warning' : 'success'}`}>
            {drift_adjustment_trends.total_drift_events}
          </div>
          <div className="metric-subtext">{drift_adjustment_trends.avg_events_per_day.toFixed(1)}/day avg</div>
        </div>
        <div className="metric-card">
          <div className="metric-label"><RotateCcw size={14} /> Total Fallbacks</div>
          <div className={`metric-value ${fallback_usage_stats.total_fallbacks > 0 ? 'warning' : 'success'}`}>
            {fallback_usage_stats.total_fallbacks}
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Fallback Rate</div>
          <div className="metric-value">{(fallback_usage_stats.overall_fallback_rate * 100).toFixed(2)}%</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Total Requests (30d)</div>
          <div className="metric-value">{formatNumber(fallback_usage_stats.total_requests)}</div>
        </div>
      </div>

      {/* Drift Timeline */}
      {driftChartData.length > 0 && (
        <div className="card section-gap">
          <div className="card-header">
            <div className="card-title"><ShieldAlert size={16} /> Drift Events Timeline</div>
          </div>
          <div className="chart-container">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={driftChartData} barSize={16}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                <YAxis allowDecimals={false} />
                <Tooltip contentStyle={{ background: '#1a1a35', border: '1px solid rgba(99,102,241,0.2)', borderRadius: 8 }} />
                <Bar dataKey="events" fill="#f59e0b" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Fallback Models Breakdown */}
      {fallback_usage_stats.models_with_fallbacks.length > 0 && (
        <div className="card section-gap">
          <div className="card-header">
            <div className="card-title"><RotateCcw size={16} /> Models with Fallbacks</div>
          </div>
          <table className="data-table">
            <thead>
              <tr><th>Model</th><th>Fallback Count</th></tr>
            </thead>
            <tbody>
              {fallback_usage_stats.models_with_fallbacks.map((m) => (
                <tr key={m.model_name}>
                  <td><span className="tag primary">{m.model_name}</span></td>
                  <td className="mono">{m.fallback_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Top Models */}
      {insights.top_performing_models.length > 0 && (
        <div className="card section-gap">
          <div className="card-header">
            <div className="card-title"><Award size={16} /> Model Performance Ranking</div>
          </div>
          <table className="data-table">
            <thead>
              <tr><th>#</th><th>Model</th><th>Avg Latency</th><th>Success Rate</th><th>Score</th></tr>
            </thead>
            <tbody>
              {insights.top_performing_models.map((m) => (
                <tr key={m.model_name}>
                  <td className="mono">{m.rank}</td>
                  <td><span className="tag primary">{m.model_name}</span></td>
                  <td className="mono">{formatLatency(m.avg_latency_ms)}</td>
                  <td className="mono">{(m.success_rate * 100).toFixed(1)}%</td>
                  <td className="mono">{(m.performance_score * 100).toFixed(0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
