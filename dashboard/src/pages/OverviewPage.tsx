// ── System Overview Dashboard ──

import {
  Cpu, Database, HardDrive, Zap,
  ArrowUpRight, ArrowDownRight, Activity, CheckCircle2,
  XCircle, AlertTriangle, RotateCcw, Gauge, BookOpen,
} from 'lucide-react';
import {
  AreaChart, Area, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell,
  ReferenceLine,
} from 'recharts';
import { useHealth, useMetrics, useModelHealth, useKnowledgeStats } from '../hooks/useQueries';
import { formatNumber, formatLatency, relativeTime, SLA_THRESHOLD_MS } from '../utils/formatters';
import { useRef, useEffect, useState } from 'react';

// ── Service Health Cards ──
function ServiceHealthStrip() {
  const { data, isLoading } = useHealth();
  if (isLoading || !data) {
    return (
      <div className="grid grid-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="service-card">
            <div className="skeleton" style={{ width: 44, height: 44, borderRadius: 12 }} />
            <div style={{ flex: 1 }}>
              <div className="skeleton" style={{ width: '60%', height: 16, marginBottom: 6 }} />
              <div className="skeleton" style={{ width: '40%', height: 12 }} />
            </div>
          </div>
        ))}
      </div>
    );
  }

  const services = data?.services || {};
  const circuit_breaker = data?.circuit_breaker;
  
  if (!services.ollama || !services.qdrant || !services.postgres) {
    return (
      <div className="grid grid-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="service-card degraded">
            <div className="service-card-info">
              <div className="service-card-name">Service Data Unavailable</div>
              <div className="service-card-detail">Check backend connection</div>
            </div>
          </div>
        ))}
      </div>
    );
  }
  const cards = [
    {
      name: 'Ollama LLM',
      icon: Cpu,
      className: 'ollama',
      status: services.ollama.status,
      detail: services.ollama.model_loaded
        ? `${services.ollama.model_name} · ${formatLatency(services.ollama.response_time_ms)}`
        : services.ollama.error ?? 'Model not loaded',
    },
    {
      name: 'Qdrant Vector DB',
      icon: Database,
      className: 'qdrant',
      status: services.qdrant.status,
      detail: services.qdrant.collection_exists
        ? `${services.qdrant.collection_name} · ${formatLatency(services.qdrant.response_time_ms)}`
        : services.qdrant.error ?? 'No collection',
    },
    {
      name: 'PostgreSQL',
      icon: HardDrive,
      className: 'postgres',
      status: services.postgres.status,
      detail: services.postgres.error ?? `Response: ${formatLatency(services.postgres.response_time_ms)}`,
    },
    {
      name: 'Circuit Breaker',
      icon: Zap,
      className: 'circuit',
      status: circuit_breaker?.state ?? 'closed',
      detail: circuit_breaker
        ? `${(circuit_breaker.failure_rate * 100).toFixed(1)}% failure rate · ${circuit_breaker.total_requests} requests`
        : 'No data',
    },
  ];

  return (
    <div className="grid grid-4">
      {cards.map((c) => {
        const Icon = c.icon;
        return (
          <div key={c.name} className="service-card">
            <div className={`service-card-icon ${c.className}`}>
              <Icon />
            </div>
            <div className="service-card-info">
              <div className="service-card-name">{c.name}</div>
              <div className="service-card-detail">{c.detail}</div>
            </div>
            <span className={`status-badge ${c.status}`}>
              <span className={`status-dot ${c.status}`} />
              {c.status}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ── KPI Metric Cards Row ──
function KPICards() {
  const { data, isLoading } = useMetrics();

  if (isLoading || !data) {
    return (
      <div className="grid grid-5">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="metric-card">
            <div className="skeleton" style={{ width: '50%', height: 12, marginBottom: 12 }} />
            <div className="skeleton" style={{ width: '70%', height: 32 }} />
          </div>
        ))}
      </div>
    );
  }

  const total = data.requests_total;
  const successRate = total > 0 ? ((data.success_count / total) * 100) : 0;

  const items = [
    { label: 'Total Requests', value: formatNumber(total), icon: Activity, colorClass: '' },
    { label: 'Successful', value: formatNumber(data.success_count), icon: CheckCircle2, colorClass: 'success' },
    { label: 'Throughput', value: `${data.requests_per_second}/s`, icon: Zap, colorClass: 'accent' },
    { label: 'Total Tokens', value: formatNumber(data.tokens_total), icon: BookOpen, colorClass: 'info' },
    { label: 'Failed', value: formatNumber(data.failures_total), icon: XCircle, colorClass: data.failures_total > 0 ? 'danger' : '' },
    { label: 'Degraded', value: formatNumber(data.degraded_total), icon: AlertTriangle, colorClass: data.degraded_total > 0 ? 'warning' : '' },
    { label: 'Fallbacks', value: formatNumber(data.fallback_count), icon: RotateCcw, colorClass: data.fallback_count > 0 ? 'warning' : '' },
    { label: 'Drift Events', value: formatNumber(data.drift_count), icon: Activity, colorClass: data.drift_count > 0 ? 'warning' : '' },
  ];

  return (
    <>
      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 'var(--space-md)' }}>
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <div key={item.label} className="metric-card">
              <div className="metric-label"><Icon size={14} />{item.label}</div>
              <div className={`metric-value ${item.colorClass}`}>{item.value}</div>
            </div>
          );
        })}
      </div>
      <div style={{ marginTop: 'var(--space-md)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--font-size-sm)', color: 'var(--text-tertiary)', marginBottom: 4 }}>
          <span>Success Rate</span>
          <span style={{ fontFamily: 'var(--font-mono)' }}>{successRate.toFixed(1)}%</span>
        </div>
        <div className="pct-bar-container">
          <div
            className={`pct-bar-fill ${successRate >= 95 ? 'success' : successRate >= 80 ? 'warning' : 'danger'}`}
            style={{ width: `${successRate}%` }}
          />
        </div>
      </div>
    </>
  );
}

// ── Latency Panel ──
function LatencyPanel() {
  const { data } = useMetrics();
  if (!data) return null;

  const gauges = [
    { label: 'P50', value: data.p50_latency_ms ?? 0, color: '#6366f1' },
    { label: 'P95', value: data.p95_latency_ms ?? 0, color: '#06b6d4' },
    { label: 'P99', value: data.p99_latency_ms ?? 0, color: '#f59e0b' },
  ];
  const barData = gauges.map((g) => ({ name: g.label, value: g.value, fill: g.color }));

  return (
    <div className="card">
      <div className="card-header">
        <div className="card-title"><Gauge size={16} />Latency Percentiles</div>
        <span className="tag">SLA: {formatLatency(SLA_THRESHOLD_MS)}</span>
      </div>
      <div style={{ display: 'flex', gap: 'var(--space-xl)', marginBottom: 'var(--space-md)' }}>
        {gauges.map((g) => (
          <div key={g.label} style={{ textAlign: 'center', flex: 1 }}>
            <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)', marginBottom: 4 }}>{g.label}</div>
            <div style={{
              fontSize: 'var(--font-size-xl)', fontWeight: 800,
              fontFamily: 'var(--font-mono)',
              color: g.value > SLA_THRESHOLD_MS ? 'var(--color-danger)' : g.color,
            }}>
              {formatLatency(g.value)}
            </div>
          </div>
        ))}
      </div>
      <div className="chart-container sm">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={barData} barSize={32}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="name" />
            <YAxis tickFormatter={(v: number) => formatLatency(v)} />
            <Tooltip
              contentStyle={{ background: '#1a1a35', border: '1px solid rgba(99,102,241,0.2)', borderRadius: 8 }}
              formatter={((v: any) => [formatLatency(Number(v) || 0), 'Latency']) as any}
            />
            <ReferenceLine y={SLA_THRESHOLD_MS} stroke="#ef4444" strokeDasharray="4 4" label={{ value: 'SLA', fill: '#ef4444', fontSize: 11 }} />
            <Bar dataKey="value" radius={[6, 6, 0, 0]}>
              {barData.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 'var(--space-sm)', fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)' }}>
        <span>Min: {formatLatency(data.min_latency_ms ?? 0)}</span>
        <span>Avg: {formatLatency(data.avg_latency_ms)}</span>
        <span>Max: {formatLatency(data.max_latency_ms ?? 0)}</span>
      </div>
    </div>
  );
}

// ── Model Health Panel ──
function ModelPanel() {
  const { data } = useModelHealth();
  if (!data || data.length === 0) {
    return (
      <div className="card">
        <div className="card-header">
          <div className="card-title"><Cpu size={16} />Model Health</div>
        </div>
        <div style={{ color: 'var(--text-tertiary)', textAlign: 'center', padding: 'var(--space-xl)', fontSize: 'var(--font-size-sm)' }}>
          No model data yet — model metrics appear once requests are processed
        </div>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="card-header">
        <div className="card-title"><Cpu size={16} />Model Health</div>
      </div>
      {data.map((m) => {
        const slaViolationRate = m.usage_count > 0 ? (m.sla_violations / m.usage_count) * 100 : 0;
        const trend = m.confidence_trend;
        return (
          <div key={m.model_name} style={{ marginBottom: 'var(--space-md)', paddingBottom: 'var(--space-md)', borderBottom: '1px solid rgba(99,102,241,0.07)' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span className="tag primary">{m.model_name}</span>
                <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)' }}>{relativeTime(m.last_used_at)}</span>
              </div>
              {trend?.is_declining
                ? <span className="status-badge degraded"><ArrowDownRight size={12} />Confidence ↓{trend.drop_percent.toFixed(1)}%</span>
                : trend
                ? <span className="status-badge healthy"><ArrowUpRight size={12} />Stable</span>
                : null
              }
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
              {[
                { label: 'Requests', value: formatNumber(m.usage_count) },
                { label: 'Avg Latency', value: formatLatency(m.avg_latency_ms), danger: m.avg_latency_ms > SLA_THRESHOLD_MS },
                { label: 'SLA Violations', value: `${m.sla_violations} (${slaViolationRate.toFixed(1)}%)`, danger: m.sla_violations > 0 },
                { label: 'Confidence', value: trend ? `${(trend.recent_avg * 100).toFixed(0)}%` : '—' },
              ].map((stat) => (
                <div key={stat.label}>
                  <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)' }}>{stat.label}</div>
                  <div style={{ fontSize: 'var(--font-size-md)', fontWeight: 700, fontFamily: 'var(--font-mono)', color: stat.danger ? 'var(--color-danger)' : undefined }}>
                    {stat.value}
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Knowledge Base Widget ──
function KnowledgeWidget() {
  const { data, isLoading } = useKnowledgeStats();

  if (isLoading || !data) {
    return (
      <div className="card">
        <div className="card-header">
          <div className="card-title"><BookOpen size={16} />Knowledge Base</div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 'var(--space-md)' }}>
          {[1, 2, 3].map((i) => (
            <div key={i}>
              <div className="skeleton" style={{ width: '60%', height: 12, marginBottom: 8 }} />
              <div className="skeleton" style={{ width: '40%', height: 24 }} />
            </div>
          ))}
        </div>
      </div>
    );
  }

  const { qdrant, ingestion } = data;
  const qdrantHealthy = ['green', 'healthy', 'ok'].includes(qdrant.status) && !qdrant.error;

  const stats = [
    { label: 'KB Documents', value: formatNumber(qdrant.points_count), sub: `${formatNumber(qdrant.vectors_count)} vectors` },
    { label: 'Ingestion Runs', value: formatNumber(ingestion.total_ingestion_runs), sub: `${formatNumber(ingestion.total_documents_created)} created` },
    { label: 'Last Sync', value: relativeTime(ingestion.last_ingestion_at), sub: ingestion.total_documents_updated > 0 ? `${formatNumber(ingestion.total_documents_updated)} updated` : 'No updates yet' },
  ];

  return (
    <div className="card">
      <div className="card-header">
        <div className="card-title"><BookOpen size={16} />Knowledge Base</div>
        <span className={`status-badge ${qdrantHealthy ? 'healthy' : 'degraded'}`}>
          <span className={`status-dot ${qdrantHealthy ? 'healthy' : 'degraded'}`} />
          {qdrant.collection}
        </span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 'var(--space-md)' }}>
        {stats.map((s) => (
          <div key={s.label}>
            <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)', marginBottom: 4 }}>{s.label}</div>
            <div style={{ fontSize: 'var(--font-size-xl)', fontWeight: 800, fontFamily: 'var(--font-mono)', color: 'var(--brand-primary-light)' }}>{s.value}</div>
            <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)', marginTop: 2 }}>{s.sub}</div>
          </div>
        ))}
      </div>
      {qdrant.error && (
        <div style={{ marginTop: 'var(--space-md)', padding: '8px 12px', borderRadius: 8, background: 'var(--color-danger-bg)', color: 'var(--color-danger-light)', fontSize: 'var(--font-size-xs)' }}>
          ⚠ {qdrant.error}
        </div>
      )}
    </div>
  );
}

// ── Request Rate Sparkline ──
function RequestSparkline() {
  const { data } = useMetrics();
  const historyRef = useRef<{ time: string; value: number }[]>([]);
  const [chartData, setChartData] = useState<{ time: string; value: number }[]>([]);
  const prevRef = useRef<number>(0);

  useEffect(() => {
    if (!data) return;
    const now = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const delta = prevRef.current > 0 ? Math.max(0, data.requests_total - prevRef.current) : 0;
    prevRef.current = data.requests_total;
    historyRef.current = [...historyRef.current.slice(-29), { time: now, value: delta * 4 }];
    setChartData([...historyRef.current]);
  }, [data]);

  if (chartData.length < 2) return null;

  return (
    <div className="card">
      <div className="card-header">
        <div className="card-title"><Activity size={16} />Requests Per Minute (estimated)</div>
      </div>
      <div className="chart-container sm">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData}>
            <defs>
              <linearGradient id="rpmGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="time" tick={{ fontSize: 10 }} />
            <YAxis tick={{ fontSize: 10 }} />
            <Tooltip contentStyle={{ background: '#1a1a35', border: '1px solid rgba(99,102,241,0.2)', borderRadius: 8 }} />
            <Area type="monotone" dataKey="value" stroke="#6366f1" fill="url(#rpmGrad)" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// ── Request Breakdown Donut ──
function RequestBreakdown() {
  const { data } = useMetrics();
  if (!data || data.requests_total === 0) return null;

  const pieData = [
    { name: 'Success', value: data.success_count, color: '#10b981' },
    { name: 'Failed', value: data.failures_total, color: '#ef4444' },
    { name: 'Degraded', value: data.degraded_total, color: '#f59e0b' },
  ].filter((d) => d.value > 0);

  return (
    <div className="card">
      <div className="card-header">
        <div className="card-title">Request Breakdown</div>
      </div>
      <div className="chart-container sm">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={pieData} cx="50%" cy="50%" innerRadius={50} outerRadius={72} dataKey="value" paddingAngle={3}>
              {pieData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
            </Pie>
            <Tooltip contentStyle={{ background: '#1a1a35', border: '1px solid rgba(99,102,241,0.2)', borderRadius: 8 }} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div style={{ display: 'flex', justifyContent: 'center', gap: 'var(--space-lg)', marginTop: 'var(--space-sm)' }}>
        {pieData.map((d) => (
          <div key={d.name} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 'var(--font-size-xs)' }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: d.color, display: 'inline-block' }} />
            <span style={{ color: 'var(--text-tertiary)' }}>{d.name}: {d.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main Overview Page ──
export default function OverviewPage() {
  return (
    <>
      <div className="page-header">
        <h2 className="page-title">System Overview</h2>
        <p className="page-subtitle">Real-time monitoring of all Virtue-AI services and metrics</p>
      </div>

      <ServiceHealthStrip />

      <div className="section-gap">
        <KPICards />
      </div>

      <div className="grid grid-2 section-gap">
        <LatencyPanel />
        <ModelPanel />
      </div>

      <div className="section-gap">
        <KnowledgeWidget />
      </div>

      <div className="grid grid-2 section-gap">
        <RequestSparkline />
        <RequestBreakdown />
      </div>
    </>
  );
}
