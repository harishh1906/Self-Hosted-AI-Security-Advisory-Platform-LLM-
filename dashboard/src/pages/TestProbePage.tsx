// ── Live Probe Page — Synthetic Canary Testing for LLM Pipeline ──
// Enterprise-grade: pre-built canary findings, auto-validation, probe history

import { useState, useCallback } from 'react';
import { FlaskConical, Send, CheckCircle, XCircle, AlertTriangle, Clock, ChevronDown, Trash2, Copy } from 'lucide-react';
import apiClient from '../api/client';
import { formatLatency } from '../utils/formatters';

interface AdvisoryResponse {
  advisory: {
    confidence: number;
    severity: string;
    risk_summary: string;
    business_impact: string;
    remediation_steps: string[];
  };
  risk_assessment: {
    risk_score: number;
    risk_level: string;
    sla: string;
    justification: string;
  };
}

const SLA_MS = 8000;
const MIN_CONFIDENCE = 0.5;

// ── Canary Finding Templates ──
const TEMPLATES = [
  {
    id: 'log4shell',
    label: '🔴 Log4Shell (CVE-2021-44228)',
    severity: 'Critical',
    scanner: 'vulnerability-scanner',
    title: 'Log4Shell Remote Code Execution',
    description: 'Apache Log4j2 JNDI injection vulnerability allows unauthenticated remote code execution via crafted log messages. CVSS 10.0. Affected versions: log4j-core 2.0-beta9 to 2.14.1.',
    org_id: 'probe-org',
  },
  {
    id: 'sqli',
    label: '🔴 SQL Injection (CWE-89)',
    severity: 'High',
    scanner: 'sast-scanner',
    title: 'SQL Injection in User Authentication Endpoint',
    description: "Unsanitized user input in the login endpoint is directly concatenated into SQL query: SELECT * FROM users WHERE username='$input'. Allows authentication bypass and data exfiltration.",
    org_id: 'probe-org',
  },
  {
    id: 'xss',
    label: '🟠 Stored XSS (CWE-79)',
    severity: 'High',
    scanner: 'dast-scanner',
    title: 'Stored Cross-Site Scripting in Comment Field',
    description: 'User-supplied HTML input in the comment field is rendered without sanitization. An attacker can inject <script> tags to steal session cookies or redirect users to malicious sites.',
    org_id: 'probe-org',
  },
  {
    id: 'idor',
    label: '🟠 IDOR (CWE-639)',
    severity: 'High',
    scanner: 'api-scanner',
    title: 'Insecure Direct Object Reference in User Profile API',
    description: 'The /api/users/{id}/profile endpoint does not verify that the authenticated user owns the requested profile. Any authenticated user can access any other user profile by changing the ID.',
    org_id: 'probe-org',
  },
  {
    id: 'ssrf',
    label: '🟠 SSRF (CWE-918)',
    severity: 'High',
    scanner: 'dast-scanner',
    title: 'Server-Side Request Forgery in Webhook Handler',
    description: 'The webhook URL parameter is fetched server-side without validation. Attackers can use this to access internal services including AWS metadata endpoint (169.254.169.254), databases, and internal APIs.',
    org_id: 'probe-org',
  },
  {
    id: 'secret',
    label: '🟡 Exposed Secret Key',
    severity: 'Medium',
    scanner: 'secret-scanner',
    title: 'Hardcoded AWS Access Key in Source Code',
    description: 'AWS access key (AKIA...) and secret key found hardcoded in src/config/aws.js. Key has S3 and EC2 full access permissions. The file has been committed to a public GitHub repository.',
    org_id: 'probe-org',
  },
  {
    id: 'path',
    label: '🟡 Path Traversal (CWE-22)',
    severity: 'Medium',
    scanner: 'sast-scanner',
    title: 'Path Traversal in File Download Endpoint',
    description: 'The file download endpoint concatenates user-supplied filename directly: /files/ + request.filename. No sanitization allows traversal attacks (../../etc/passwd) to read arbitrary system files.',
    org_id: 'probe-org',
  },
  {
    id: 'custom',
    label: '✏️ Custom Finding',
    severity: 'High',
    scanner: 'manual',
    title: '',
    description: '',
    org_id: 'probe-org',
  },
];

type Severity = 'Critical' | 'High' | 'Medium' | 'Low';

interface Finding {
  title: string;
  description: string;
  severity: Severity;
  scanner: string;
  org_id: string;
}

type ProbeStatus = 'idle' | 'running' | 'pass' | 'fail' | 'warn';

interface ProbeResult {
  id: string;
  templateLabel: string;
  finding: Finding;
  status: ProbeStatus;
  latency_ms: number;
  confidence?: number;
  severity_result?: string;
  risk_score?: number;
  risk_summary?: string;
  remediation_count?: number;
  error?: string;
  timestamp: Date;
  validations: { label: string; pass: boolean; value: string }[];
}

function statusIcon(status: ProbeStatus, size = 18) {
  if (status === 'pass')   return <CheckCircle size={size} style={{ color: 'var(--success)' }} />;
  if (status === 'fail')   return <XCircle size={size} style={{ color: 'var(--danger)' }} />;
  if (status === 'warn')   return <AlertTriangle size={size} style={{ color: 'var(--warning)' }} />;
  if (status === 'running') return <div className="spinner" style={{ width: size, height: size }} />;
  return null;
}

function statusColor(status: ProbeStatus) {
  if (status === 'pass')   return 'var(--success)';
  if (status === 'fail')   return 'var(--danger)';
  if (status === 'warn')   return 'var(--warning)';
  return 'var(--text-tertiary)';
}

export default function TestProbePage() {
  const [selectedTemplate, setSelectedTemplate] = useState(TEMPLATES[0]);
  const [finding, setFinding] = useState<Finding>({
    title: TEMPLATES[0].title,
    description: TEMPLATES[0].description,
    severity: TEMPLATES[0].severity as Severity,
    scanner: TEMPLATES[0].scanner,
    org_id: TEMPLATES[0].org_id,
  });
  const [running, setRunning] = useState(false);
  const [history, setHistory] = useState<ProbeResult[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);

  const pickTemplate = useCallback((t: typeof TEMPLATES[0]) => {
    setSelectedTemplate(t);
    setFinding({
      title: t.title,
      description: t.description,
      severity: t.severity as Severity,
      scanner: t.scanner,
      org_id: t.org_id,
    });
  }, []);

  const fireProbe = useCallback(async (isSilentArg: any = false) => {
    const isSilent = isSilentArg === true;
    if (!isSilent && running) return;
    if (!isSilent) setRunning(true);
    const probeId = `probe-${Date.now()}`;
    const start = performance.now();

    try {
      const resp = await apiClient.analyzeProbe(finding) as unknown as AdvisoryResponse;
      const latency_ms = Math.round(performance.now() - start);
      const advisory = resp?.advisory;
      const risk_assessment = resp?.risk_assessment;

      const confidence = advisory?.confidence ?? 0;
      const risk_score = risk_assessment?.risk_score ?? 0;
      const slaPassed = latency_ms <= SLA_MS;
      const confPassed = confidence >= MIN_CONFIDENCE;
      const hasRemediation = (advisory?.remediation_steps?.length ?? 0) > 0;

      const validations = [
        { label: `Latency ≤ ${SLA_MS / 1000}s SLA`, pass: slaPassed, value: formatLatency(latency_ms) },
        { label: `Confidence ≥ ${MIN_CONFIDENCE}`, pass: confPassed, value: confidence?.toFixed(2) ?? 'n/a' },
        { label: 'Has remediation steps', pass: hasRemediation, value: hasRemediation ? `${advisory?.remediation_steps?.length} steps` : 'none' },
        { label: 'Risk score present', pass: risk_score > 0, value: risk_score?.toString() ?? 'n/a' },
      ];

      const allPass = validations.every(v => v.pass);

      const result: ProbeResult = {
        id: probeId,
        templateLabel: selectedTemplate.label,
        finding,
        status: allPass ? 'pass' : 'warn',
        latency_ms,
        confidence,
        severity_result: advisory?.severity,
        risk_score: risk_score,
        risk_summary: advisory?.risk_summary,
        remediation_count: advisory?.remediation_steps?.length,
        timestamp: new Date(),
        validations,
      };

      if (!isSilent) {
        setHistory(h => [result, ...h].slice(0, 20));
        setExpanded(probeId);
      }
      return result;
    } catch (err: unknown) {
      const latency_ms = Math.round(performance.now() - start);
      const result: ProbeResult = {
        id: probeId,
        templateLabel: selectedTemplate.label,
        finding,
        status: 'fail',
        latency_ms,
        error: err instanceof Error ? err.message : String(err),
        timestamp: new Date(),
        validations: [{ label: 'Request succeeded', pass: false, value: 'error' }],
      };
      if (!isSilent) {
        setHistory(h => [result, ...h].slice(0, 20));
        setExpanded(probeId);
      }
      return result;
    } finally {
      if (!isSilent) setRunning(false);
    }
  }, [running, finding, selectedTemplate]);

  const runLoadTest = useCallback(async (count: number) => {
    if (running) return;
    setRunning(true);
    const start = performance.now();
    const finished: ProbeResult[] = [];
    
    // Concurrency limit: Since backend is serialized, we only want a few in flight 
    // to avoid hit the 3-minute queue timeout.
    const CONCURRENCY = 2;
    const queue = Array.from({ length: count });
    
    const worker = async () => {
      while (queue.length > 0) {
        queue.pop();
        const res = await fireProbe(true);
        if (res) finished.push(res);
      }
    };

    // Start workers
    const workers = Array.from({ length: CONCURRENCY }).map(() => worker());
    await Promise.all(workers);
    
    const totalLatency = performance.now() - start;
    const passCount = finished.filter(r => r?.status === 'pass').length;
    const warnCount = finished.filter(r => r?.status === 'warn').length;
    const failCount = finished.filter(r => r?.status === 'fail').length;

    const loadTestResult: ProbeResult = {
      id: `load-${Date.now()}`,
      templateLabel: `⚡ Load Test (${count} reqs)`,
      finding,
      status: passCount === count ? 'pass' : passCount > 0 ? 'warn' : 'fail',
      latency_ms: Math.round(totalLatency),
      timestamp: new Date(),
      validations: [
        { label: 'Completed', pass: finished.length === count, value: `${finished.length}/${count}` },
        { label: 'Passed (SLA met)', pass: passCount > 0, value: passCount.toString() },
        { label: 'Degraded (Slow)', pass: warnCount === 0, value: warnCount.toString() },
        { label: 'Failed', pass: failCount === 0, value: failCount.toString() },
        { label: 'Throughput', pass: true, value: `${(count / (totalLatency / 1000)).toFixed(2)} req/s` },
      ],
      risk_summary: `Load test completed in ${formatLatency(totalLatency)}. Results: ${passCount}/${count} passed.`,
    };
    
    setHistory(h => [loadTestResult, ...h].slice(0, 20));
    setExpanded(loadTestResult.id);
    setRunning(false);
  }, [running, finding, fireProbe]);

  const passCount = history.filter(r => r.status === 'pass').length;
  const failCount = history.filter(r => r.status === 'fail').length;
  const warnCount = history.filter(r => r.status === 'warn').length;
  const avgLatency = history.length
    ? Math.round(history.reduce((a, r) => a + r.latency_ms, 0) / history.length)
    : 0;

  return (
    <div className="page-content">
      {/* ── Header ── */}
      <div className="page-header">
        <div>
          <div className="page-title"><FlaskConical size={20} /> Live Probe</div>
          <div className="page-subtitle">Synthetic canary testing — validate the full LLM advisory pipeline end-to-end</div>
        </div>
        {history.length > 0 && (
          <div style={{ display: 'flex', gap: 'var(--space-sm)', alignItems: 'center' }}>
            <span style={{ color: 'var(--success)', fontSize: 'var(--font-size-sm)', fontWeight: 600 }}>✓ {passCount} Pass</span>
            <span style={{ color: 'var(--warning)', fontSize: 'var(--font-size-sm)', fontWeight: 600 }}>⚠ {warnCount} Warn</span>
            <span style={{ color: 'var(--danger)', fontSize: 'var(--font-size-sm)', fontWeight: 600 }}>✗ {failCount} Fail</span>
            {avgLatency > 0 && <span className="tag">Avg {formatLatency(avgLatency)}</span>}
            <button className="btn-ghost" onClick={() => setHistory([])} title="Clear history"><Trash2 size={14}/></button>
          </div>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '380px 1fr', gap: 'var(--space-lg)', alignItems: 'start' }}>

        {/* ── Left: Probe Builder ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-md)' }}>
          <div className="card">
            <div className="card-header">
              <div className="card-title">Finding Template</div>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-xs)' }}>
              {TEMPLATES.map(t => (
                <button
                  key={t.id}
                  onClick={() => pickTemplate(t)}
                  style={{
                    padding: '10px 14px',
                    borderRadius: 8,
                    border: `1px solid ${selectedTemplate.id === t.id ? 'rgba(99,102,241,0.6)' : 'rgba(255,255,255,0.06)'}`,
                    background: selectedTemplate.id === t.id ? 'rgba(99,102,241,0.12)' : 'transparent',
                    color: selectedTemplate.id === t.id ? 'var(--accent)' : 'var(--text-secondary)',
                    cursor: 'pointer',
                    textAlign: 'left',
                    fontSize: 'var(--font-size-sm)',
                    transition: 'all 0.15s',
                  }}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>

          <div className="card">
            <div className="card-header">
              <div className="card-title">Finding Details</div>
              <span className="tag">{finding.severity}</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-sm)' }}>
              <div>
                <label style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)', marginBottom: 4, display: 'block' }}>TITLE</label>
                <input
                  value={finding.title}
                  onChange={e => setFinding(f => ({ ...f, title: e.target.value }))}
                  placeholder="Finding title..."
                  style={{
                    width: '100%', padding: '8px 12px', background: 'rgba(255,255,255,0.05)',
                    border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8,
                    color: 'var(--text-primary)', fontSize: 'var(--font-size-sm)',
                    outline: 'none', boxSizing: 'border-box',
                  }}
                />
              </div>
              <div>
                <label style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)', marginBottom: 4, display: 'block' }}>DESCRIPTION</label>
                <textarea
                  value={finding.description}
                  onChange={e => setFinding(f => ({ ...f, description: e.target.value }))}
                  placeholder="Describe the vulnerability..."
                  rows={5}
                  style={{
                    width: '100%', padding: '8px 12px', background: 'rgba(255,255,255,0.05)',
                    border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8,
                    color: 'var(--text-primary)', fontSize: 'var(--font-size-sm)',
                    outline: 'none', resize: 'vertical', boxSizing: 'border-box',
                    fontFamily: 'inherit',
                  }}
                />
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-sm)' }}>
                <div>
                  <label style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)', marginBottom: 4, display: 'block' }}>SEVERITY</label>
                  <select
                    value={finding.severity}
                    onChange={e => setFinding(f => ({ ...f, severity: e.target.value as Severity }))}
                    style={{
                      width: '100%', padding: '8px 12px', background: 'rgba(255,255,255,0.05)',
                      border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8,
                      color: 'var(--text-primary)', fontSize: 'var(--font-size-sm)',
                      outline: 'none', boxSizing: 'border-box',
                    }}
                  >
                    <option value="Critical">Critical</option>
                    <option value="High">High</option>
                    <option value="Medium">Medium</option>
                    <option value="Low">Low</option>
                  </select>
                </div>
                <div>
                  <label style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)', marginBottom: 4, display: 'block' }}>ORG ID</label>
                  <input
                    value={finding.org_id}
                    onChange={e => setFinding(f => ({ ...f, org_id: e.target.value }))}
                    style={{
                      width: '100%', padding: '8px 12px', background: 'rgba(255,255,255,0.05)',
                      border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8,
                      color: 'var(--text-primary)', fontSize: 'var(--font-size-sm)',
                      outline: 'none', boxSizing: 'border-box',
                    }}
                  />
                </div>
              </div>

              <div style={{ display: 'flex', gap: 'var(--space-sm)' }}>
                <button
                  onClick={() => fireProbe()}
                  disabled={running || !finding.title || !finding.description}
                  style={{
                    flex: 1,
                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                    padding: '12px 20px', borderRadius: 10, border: 'none', cursor: running ? 'not-allowed' : 'pointer',
                    background: running ? 'rgba(99,102,241,0.4)' : 'linear-gradient(135deg, #6366f1, #8b5cf6)',
                    color: '#fff', fontWeight: 700, fontSize: 'var(--font-size-sm)',
                    transition: 'all 0.2s', opacity: (!finding.title || !finding.description) ? 0.5 : 1,
                  }}
                >
                  {running
                    ? <><div className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} /> Sending…</>
                    : <><Send size={16} /> Fire Probe</>
                  }
                </button>
              </div>

              <div style={{ borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: 'var(--space-sm)' }}>
                <label style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)', marginBottom: 4, display: 'block' }}>LOAD TEST (STRESS TESTING)</label>
                <div style={{ fontSize: 10, color: 'var(--text-tertiary)', marginBottom: 8, fontStyle: 'italic' }}>
                  Note: Requests are queued due to hardware serialization lock (Quadro P1000).
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
                  {[10, 25, 50].map(n => (
                    <button
                      key={n}
                      onClick={() => runLoadTest(n)}
                      disabled={running}
                      className="btn-ghost"
                      style={{
                        padding: '8px', borderRadius: 8, fontSize: 'var(--font-size-xs)',
                        border: '1px solid rgba(99,102,241,0.2)',
                        background: 'rgba(99,102,241,0.05)',
                      }}
                    >
                      {n} reqs
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* ── Right: Probe History ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-md)' }}>
          {history.length === 0 && (
            <div className="card" style={{ textAlign: 'center', padding: 'var(--space-2xl)', color: 'var(--text-tertiary)' }}>
              <FlaskConical size={48} style={{ opacity: 0.3, margin: '0 auto var(--space-md)' }} />
              <div style={{ fontWeight: 600, marginBottom: 8 }}>No probes fired yet</div>
              <div style={{ fontSize: 'var(--font-size-sm)' }}>Pick a template and click <strong>Fire Probe</strong> to test the full LLM pipeline</div>
            </div>
          )}

          {history.map(result => (
            <div
              key={result.id}
              className="card"
              style={{ borderColor: `${statusColor(result.status)}33` }}
            >
              {/* Result header */}
              <div
                style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-sm)', cursor: 'pointer' }}
                onClick={() => setExpanded(expanded === result.id ? null : result.id)}
              >
                {statusIcon(result.status, 20)}
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, fontSize: 'var(--font-size-sm)', color: 'var(--text-primary)' }}>
                    {result.templateLabel}
                  </div>
                  <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)' }}>
                    {result.timestamp.toLocaleTimeString()} · {formatLatency(result.latency_ms)}
                    {result.confidence !== undefined && ` · Confidence ${(result.confidence * 100).toFixed(0)}%`}
                  </div>
                </div>
                {/* Validation pills */}
                <div style={{ display: 'flex', gap: 4 }}>
                  {result.validations.map((v, i) => (
                    <span key={i} style={{
                      width: 10, height: 10, borderRadius: '50%',
                      background: v.pass ? 'var(--success)' : 'var(--danger)',
                      display: 'inline-block',
                    }} />
                  ))}
                </div>
                <ChevronDown size={16} style={{ color: 'var(--text-tertiary)', transform: expanded === result.id ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} />
              </div>

              {/* Expanded detail */}
              {expanded === result.id && (
                <div style={{ marginTop: 'var(--space-md)', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: 'var(--space-md)' }}>

                  {/* Validation checklist */}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 8, marginBottom: 'var(--space-md)' }}>
                    {result.validations.map((v, i) => (
                      <div key={i} style={{
                        display: 'flex', alignItems: 'center', gap: 8,
                        padding: '8px 12px', borderRadius: 8,
                        background: v.pass ? 'rgba(16,185,129,0.08)' : 'rgba(239,68,68,0.08)',
                        border: `1px solid ${v.pass ? 'rgba(16,185,129,0.2)' : 'rgba(239,68,68,0.2)'}`,
                      }}>
                        {v.pass
                          ? <CheckCircle size={14} style={{ color: 'var(--success)' }} />
                          : <XCircle size={14} style={{ color: 'var(--danger)' }} />
                        }
                        <div>
                          <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>{v.label}</div>
                          <div style={{ fontSize: 'var(--font-size-sm)', fontWeight: 600, color: v.pass ? 'var(--success)' : 'var(--danger)' }}>{v.value}</div>
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Error message */}
                  {result.error && (
                    <div style={{
                      padding: '12px 16px', borderRadius: 8,
                      background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)',
                      color: 'var(--danger)', fontSize: 'var(--font-size-sm)', marginBottom: 'var(--space-md)',
                    }}>
                      ✗ {result.error}
                    </div>
                  )}

                  {/* Advisory content */}
                  {result.risk_summary && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em' }}>LLM Advisory Response</span>
                        <div style={{ display: 'flex', gap: 8 }}>
                          {result.severity_result && <span className="tag">{result.severity_result}</span>}
                          {result.risk_score !== undefined && <span className="tag">Risk {result.risk_score}</span>}
                          {result.remediation_count !== undefined && <span className="tag">{result.remediation_count} steps</span>}
                          <button
                            className="btn-ghost"
                            onClick={() => navigator.clipboard.writeText(result.risk_summary ?? '')}
                            title="Copy response"
                          >
                            <Copy size={12} />
                          </button>
                        </div>
                      </div>
                      <div style={{
                        padding: '14px 16px', borderRadius: 10,
                        background: 'rgba(99,102,241,0.06)',
                        border: '1px solid rgba(99,102,241,0.15)',
                        fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)',
                        lineHeight: 1.7, maxHeight: 300, overflowY: 'auto',
                      }}>
                        {result.risk_summary}
                      </div>
                      <div style={{ display: 'flex', gap: 8, fontSize: 11, color: 'var(--text-tertiary)' }}>
                        <Clock size={12} />
                        <span>Response time: <strong style={{ color: result.latency_ms > SLA_MS ? 'var(--danger)' : 'var(--success)' }}>{formatLatency(result.latency_ms)}</strong></span>
                        <span>· SLA: {SLA_MS / 1000}s</span>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
