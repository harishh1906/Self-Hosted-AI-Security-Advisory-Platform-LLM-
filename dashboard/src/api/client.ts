// ── API Client — Central HTTP client for Virtue-AI backend ──

const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  body?: unknown;
  token?: string;
  /** Request timeout in ms. Default 30s. Pass 0 for no timeout (long-running LLM calls). */
  timeoutMs?: number;
}

const DEFAULT_TIMEOUT_MS = 30_000;

class ApiClient {
  private baseUrl: string;
  private token: string | null = null;
  private initPromise: Promise<void> | null = null;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
    this.token = localStorage.getItem('virtue_token');
    if (!this.token) {
      this.initPromise = this.autoLogin();
    }
  }

  private async autoLogin(): Promise<void> {
    try {
      const resp = await fetch(
        `${this.baseUrl}/login?username=virtue-dashboard&role=security_analyst`,
        { method: 'POST' }
      );
      if (resp.ok) {
        const data = await resp.json();
        this.setToken(data.access_token);
      }
    } catch {
      // Will retry on next 401
    }
  }

  private async ensureInit(): Promise<void> {
    if (this.initPromise) {
      await this.initPromise;
      this.initPromise = null;
    }
    if (!this.token) {
      await this.autoLogin();
    }
  }

  setToken(token: string) {
    this.token = token;
    localStorage.setItem('virtue_token', token);
  }

  clearToken() {
    this.token = null;
    localStorage.removeItem('virtue_token');
  }

  getToken(): string | null {
    return this.token;
  }

  async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    await this.ensureInit();

    const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    if (timeoutMs > 0) {
      timer = setTimeout(() => controller.abort(), timeoutMs);
    }

    const doFetch = (tok: string | null) => {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (tok) headers['Authorization'] = `Bearer ${tok}`;
      return fetch(`${this.baseUrl}${path}`, {
        method: options.method ?? 'GET',
        headers,
        body: options.body ? JSON.stringify(options.body) : undefined,
        signal: controller.signal,
      });
    };

    try {
      let response = await doFetch(options.token ?? this.token);

      if (response.status === 401) {
        this.clearToken();
        await this.autoLogin();
        response = await doFetch(this.token);
      }

      if (!response.ok) {
        throw new Error(`API ${response.status}: ${response.statusText}`);
      }

      return response.json();
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        throw new Error(`Request timed out after ${timeoutMs / 1000}s: ${path}`);
      }
      throw err;
    } finally {
      if (timer !== undefined) clearTimeout(timer);
    }
  }

  // ── Internal Endpoints ──
  getHealth() {
    return this.request<import('./types').HealthResponse>('/internal/health');
  }

  getSimpleHealth() {
    return this.request<{ status: string }>('/health');
  }

  async getMetrics(): Promise<import('./types').MetricsResponse> {
    const raw = await this.request<Record<string, number>>('/internal/metrics');
    return {
      ...raw,
      p95_latency_ms: raw['p95_latency_ms'] ?? raw['p95_latency'] ?? 0,
      p50_latency_ms: raw['p50_latency_ms'] ?? 0,
      p99_latency_ms: raw['p99_latency_ms'] ?? 0,
      avg_latency_ms: raw['avg_latency_ms'] ?? 0,
      min_latency_ms: raw['min_latency_ms'] ?? 0,
      max_latency_ms: raw['max_latency_ms'] ?? 0,
      requests_total: raw['requests_total'] ?? 0,
      success_count: raw['success_count'] ?? 0,
      failures_total: raw['failures_total'] ?? 0,
      degraded_total: raw['degraded_total'] ?? 0,
      fallback_count: raw['fallback_count'] ?? 0,
      drift_count: raw['drift_count'] ?? 0,
      tokens_total: raw['tokens_total'] ?? 0,
      requests_per_second: raw['requests_per_second'] ?? 0.0,
      latency_sample_count: raw['latency_sample_count'] ?? 0,
    } as import('./types').MetricsResponse;
  }

  async getModelHealth(): Promise<import('./types').ModelHealthSummary[]> {
    const raw = await this.request<{ models: import('./types').ModelHealthSummary[] }>(
      '/internal/control-plane/model-health-summary'
    );
    return raw.models ?? [];
  }

  getOptimizationInsights() {
    return this.request<import('./types').OptimizationInsights>('/internal/optimization-insights');
  }

  async getPolicyEffectiveness(): Promise<import('./types').PolicyEffectiveness[]> {
    const raw = await this.request<{ policies: import('./types').PolicyEffectiveness[] }>(
      '/internal/policy-effectiveness'
    );
    return raw.policies ?? [];
  }

  getKnowledgeStats() {
    return this.request<import('./types').KnowledgeStats>('/api/v1/knowledge/stats');
  }

  getModelOptimizationRecommendations(orgId: string) {
    return this.request<import('./types').ActiveModel[]>(
      `/api/v1/ai/governance/model-optimization-recommendations?org_id=${orgId}`
    );
  }

  // ── Governance Endpoints ──
  getPolicyCostSummary(orgId: string) {
    return this.request<import('./types').PolicyCostSummary[]>(
      `/api/v1/ai/governance/policy-cost-summary?org_id=${orgId}`
    );
  }

  getPolicyLatencySummary(orgId: string) {
    return this.request<import('./types').PolicyLatencySummary[]>(
      `/api/v1/ai/governance/policy-latency-summary?org_id=${orgId}`
    );
  }

  getPolicySuccessSummary(orgId: string) {
    return this.request<import('./types').PolicySuccessSummary[]>(
      `/api/v1/ai/governance/policy-success-summary?org_id=${orgId}`
    );
  }

  getActiveModels(orgId: string) {
    return this.request<import('./types').ActiveModel[]>(
      `/api/v1/ai/governance/active-models?org_id=${orgId}`
    );
  }

  getModelConfig() {
    return this.request<Record<string, unknown>>('/api/v1/ai/governance/model-config');
  }

  login(username: string) {
    return this.request<{ access_token: string; token_type: string }>(
      `/login?username=${encodeURIComponent(username)}`,
      { method: 'POST' }
    );
  }

  /** Fetch all system settings */
  getConfig() {
    return this.request<any[]>('/internal/config/');
  }

  /** Update a specific system setting */
  updateConfig(key: string, value: any, description?: string) {
    return this.request<any>(`/internal/config/${key}`, {
      method: 'PUT',
      body: { value, description },
    });
  }

  /** Fire a canary finding. LLM can take up to 300s — use extended timeout (320s). */
  analyzeProbe(finding: {
    title: string;
    description: string;
    severity: string;
    scanner: string;
    org_id: string;
  }) {
    return this.request<Record<string, unknown>>('/analyze', {
      method: 'POST',
      body: finding,
      timeoutMs: 320_000, // 320s — covers the 300s LLM_REQUEST_TIMEOUT + buffer
    });
  }
}

export const apiClient = new ApiClient(API_BASE);
export default apiClient;
