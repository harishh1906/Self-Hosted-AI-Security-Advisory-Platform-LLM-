import { useState, useEffect } from 'react';
import { Save, RefreshCcw, Clock, Cpu, Gauge, Zap, AlertCircle } from 'lucide-react';
import apiClient from '../api/client';

interface ConfigItem {
  key: string;
  value: any;
  description: string;
  updated_at: string;
}

const DEFAULTS: Record<string, any> = {
  fetcher_interval_hours: 6,
  ingester_interval_seconds: 60,
  primary_model: 'gemma4:e2b',
  fallback_model: 'mistral:7b-instruct',
  sla_threshold_ms: 8000,
};

export default function SettingsPage() {
  const [configs, setConfigs] = useState<ConfigItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadConfigs();
  }, []);

  const loadConfigs = async () => {
    try {
      setLoading(true);
      const data = await apiClient.getConfig();
      setConfigs(data);
      setError(null);
    } catch (err) {
      setError('Failed to load system configuration. Showing defaults — saves will still apply.');
    } finally {
      setLoading(false);
    }
  };

  const updateConfig = async (key: string, newValue: any) => {
    try {
      setSaving(key);
      await apiClient.updateConfig(key, newValue);
      setConfigs(prev => {
        const exists = prev.some(c => c.key === key);
        const now = new Date().toISOString();
        if (exists) {
          return prev.map(c => c.key === key ? { ...c, value: newValue, updated_at: now } : c);
        }
        return [...prev, { key, value: newValue, description: '', updated_at: now }];
      });
      setError(null);
    } catch (err) {
      setError(`Failed to update ${key}. Please check your connection.`);
    } finally {
      setSaving(null);
    }
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '60vh', color: 'var(--text-tertiary)' }}>
        <RefreshCcw className="spinner" size={32} />
      </div>
    );
  }

  const getConfigValue = (key: string) => {
    const found = configs.find(c => c.key === key);
    return found !== undefined ? found.value : DEFAULTS[key];
  };

  return (
    <div className="page-content fade-in">
      <div style={{ marginBottom: 'var(--space-xl)' }}>
        <h1 className="page-title">Enterprise Settings</h1>
        <p className="page-subtitle">Manage background workers, LLM routing, and system-wide performance SLAs.</p>
      </div>

      {error && (
        <div style={{ 
          padding: '12px 16px', borderRadius: 12, background: 'rgba(239, 68, 68, 0.1)', 
          border: '1px solid rgba(239, 68, 68, 0.2)', color: 'var(--color-danger-light)',
          marginBottom: 'var(--space-lg)', display: 'flex', alignItems: 'center', gap: 12,
          fontSize: 'var(--font-size-sm)'
        }}>
          <AlertCircle size={18} />
          {error}
        </div>
      )}

      <div className="grid grid-2">
        {/* ── Worker Automation ── */}
        <div className="card">
          <div className="card-header">
            <h2 className="card-title"><Zap size={18} /> Worker Automation</h2>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-lg)' }}>
            <SettingRow
              label="Knowledge Fetcher Interval"
              description="Frequency for fetching NVD/CISA KEV vulnerability feeds."
              icon={<Clock size={16} />}
              value={getConfigValue('fetcher_interval_hours')}
              suffix="hours"
              min={1} max={24}
              onSave={(val: any) => updateConfig('fetcher_interval_hours', val)}
              loading={saving === 'fetcher_interval_hours'}
            />
            <SettingRow
              label="Knowledge Ingester Rate"
              description="Polling frequency for the knowledge inbox volume."
              icon={<RefreshCcw size={16} />}
              value={getConfigValue('ingester_interval_seconds')}
              suffix="seconds"
              min={10} max={300}
              onSave={(val: any) => updateConfig('ingester_interval_seconds', val)}
              loading={saving === 'ingester_interval_seconds'}
            />
          </div>
        </div>

        {/* ── LLM Governance ── */}
        <div className="card">
          <div className="card-header">
            <h2 className="card-title"><Cpu size={18} /> LLM Governance</h2>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-lg)' }}>
            <SettingRow
              label="Primary Model"
              description="The default model used for generating security advisories."
              icon={<Cpu size={16} />}
              value={getConfigValue('primary_model')}
              isSelect
              options={['gemma4:e2b', 'mistral:7b-instruct', 'llama3:8b', 'phi3:latest']}
              onSave={(val: any) => updateConfig('primary_model', val)}
              loading={saving === 'primary_model'}
            />
            <SettingRow
              label="Fallback Model"
              description="Model used if the primary model fails or is overloaded."
              icon={<Zap size={16} />}
              value={getConfigValue('fallback_model')}
              isSelect
              options={['mistral:7b-instruct', 'llama3:8b', 'phi3:latest']}
              onSave={(val: any) => updateConfig('fallback_model', val)}
              loading={saving === 'fallback_model'}
            />
          </div>
        </div>

        {/* ── Performance SLAs ── */}
        <div className="card">
          <div className="card-header">
            <h2 className="card-title"><Gauge size={18} /> Performance SLAs</h2>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-lg)' }}>
            <SettingRow
              label="Inference SLA Threshold"
              description="Target latency. Verbosity reduction triggers if average exceeds this."
              icon={<Clock size={16} />}
              value={getConfigValue('sla_threshold_ms')}
              suffix="ms"
              min={1000} max={30000} step={500}
              onSave={(val: any) => updateConfig('sla_threshold_ms', val)}
              loading={saving === 'sla_threshold_ms'}
            />
          </div>
        </div>

        {/* ── System Status ── */}
        <div className="card" style={{ background: 'rgba(59, 130, 246, 0.05)', border: '1px solid rgba(59, 130, 246, 0.2)' }}>
          <div className="card-header">
            <h2 className="card-title" style={{ color: 'var(--brand-primary-light)' }}><AlertCircle size={18} /> Deployment Status</h2>
          </div>
          <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
            <p style={{ marginBottom: 12 }}>All settings are persisted to the cluster database and hot-reloaded by workers within 60 seconds.</p>
            {configs.length > 0 ? (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--color-success-light)', fontWeight: 600, marginBottom: 8 }}>
                  <div className="pulse-dot" style={{ width: 8, height: 8 }} />
                  Cluster Config Synchronized
                </div>
                <div style={{ color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', fontSize: 'var(--font-size-xs)' }}>
                  Last updated: {new Date(
                    Math.max(...configs.map(c => new Date(c.updated_at).getTime()))
                  ).toLocaleString()}
                </div>
              </>
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--color-danger-light)', fontWeight: 600 }}>
                <AlertCircle size={14} />
                Config unavailable
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function SettingRow({ label, description, icon, value, suffix, min, max, step, onSave, loading, isSelect, options }: any) {
  const [localValue, setLocalValue] = useState(value);

  useEffect(() => {
    setLocalValue(value);
  }, [value]);

  return (
    <div style={{ padding: 'var(--space-md)', borderRadius: 12, background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
        <div style={{ display: 'flex', gap: 12 }}>
          <div style={{ color: 'var(--brand-primary-light)', marginTop: 2 }}>{icon}</div>
          <div>
            <div style={{ fontWeight: 600, fontSize: 'var(--font-size-base)', color: 'var(--text-primary)' }}>{label}</div>
            <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)', maxWidth: 300 }}>{description}</div>
          </div>
        </div>
        <button 
          onClick={() => onSave(localValue)} 
          disabled={loading || localValue === value}
          style={{ 
            padding: '6px 12px', borderRadius: 8, border: 'none', 
            background: localValue === value ? 'transparent' : 'var(--brand-primary)', 
            color: '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6,
            transition: 'all 0.2s', fontSize: 'var(--font-size-xs)', fontWeight: 600
          }}
        >
          {loading ? <RefreshCcw size={14} className="spinner" /> : <Save size={14} />}
          {localValue === value ? 'Saved' : 'Deploy'}
        </button>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        {isSelect ? (
          <select 
            value={localValue} 
            onChange={(e) => setLocalValue(e.target.value)}
            style={{ 
              flex: 1, padding: '8px 12px', background: 'rgba(0,0,0,0.2)', 
              border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, 
              color: 'var(--text-primary)', outline: 'none' 
            }}
          >
            {options.map((opt: string) => <option key={opt} value={opt}>{opt}</option>)}
          </select>
        ) : (
          <>
            <input 
              type="range" 
              min={min} max={max} step={step || 1}
              value={localValue} 
              onChange={(e) => setLocalValue(Number(e.target.value))}
              style={{ flex: 1, accentColor: 'var(--brand-primary)' }}
            />
            <div style={{ width: 80, textAlign: 'right', fontFamily: 'var(--font-mono)', fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
              {localValue} {suffix}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

