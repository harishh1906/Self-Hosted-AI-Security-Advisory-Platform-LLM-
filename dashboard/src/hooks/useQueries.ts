// ── Query Hooks — Hybrid SSE + REST polling fallback ──
//
// CRITICAL: REST fallbacks for metrics/model-health are ONLY enabled when
// the SSE connection is confirmed down (!connected). This prevents the 504
// cascade where the fallback fires before SSE delivers its first push,
// hammering /internal/control-plane/model-health-summary (a slow endpoint)
// and disrupting the SSE stream itself via nginx upstream errors.

import { useQuery } from '@tanstack/react-query';
import { useSSE } from './useSSE';
import apiClient from '../api/client';
import type { MetricsResponse, ModelHealthSummary } from '../api/types';

// ── SSE-powered hooks with guarded REST fallback ──

/** Real-time metrics from SSE stream.
 *  REST fallback ONLY activates when SSE is fully disconnected. */
export function useMetrics() {
  const { data: sseData, connected } = useSSE();
  const sseMetrics: MetricsResponse | undefined = sseData?.metrics;

  const fallback = useQuery({
    queryKey: ['metrics-rest-fallback'],
    queryFn: () => apiClient.getMetrics(),
    refetchInterval: 15_000,
    staleTime: 10_000,
    // Only poll when SSE is confirmed disconnected AND has no cached data
    enabled: !connected && !sseMetrics,
    refetchOnWindowFocus: false,
    retry: 1,
  });

  return {
    data: sseMetrics ?? fallback.data,
    isLoading: !sseMetrics && fallback.isLoading,
    isError: !sseMetrics && fallback.isError,
    isLive: connected && !!sseMetrics,
  };
}

/** Real-time model health from SSE stream.
 *  REST fallback ONLY activates when SSE is confirmed disconnected.
 *  Critical: do NOT fire the REST fallback while SSE is connecting — the
 *  /internal/control-plane/model-health-summary endpoint is slow and its
 *  504 errors cascade into Nginx disrupting the SSE stream. */
export function useModelHealth() {
  const { data: sseData, connected } = useSSE();
  const sseModels: ModelHealthSummary[] | undefined = sseData?.models;

  const fallback = useQuery({
    queryKey: ['model-health-rest-fallback'],
    queryFn: () => apiClient.getModelHealth(),
    refetchInterval: 30_000,
    staleTime: 20_000,
    // Guard: only enable when SSE is confirmed down
    enabled: !connected && !sseModels,
    refetchOnWindowFocus: false,
    retry: 0,
  });

  return {
    data: sseModels ?? fallback.data,
    isLoading: !sseModels && (connected ? false : fallback.isLoading),
    isError: !sseModels && fallback.isError,
    isLive: connected && !!sseModels,
  };
}

// ── Rare-poll hooks ──

/** System health — polls every 60s */
export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: () => apiClient.getHealth(),
    refetchInterval: 60_000,
    staleTime: 5_000,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

/** Optimization insights — polls every 10 minutes */
export function useOptimizationInsights() {
  return useQuery({
    queryKey: ['optimizationInsights'],
    queryFn: () => apiClient.getOptimizationInsights(),
    refetchInterval: 600_000,
    staleTime: 300_000,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    retry: 0,
  });
}

/** Policy effectiveness — polls every 10 minutes */
export function usePolicyEffectiveness() {
  return useQuery({
    queryKey: ['policyEffectiveness'],
    queryFn: () => apiClient.getPolicyEffectiveness(),
    refetchInterval: 600_000,
    staleTime: 300_000,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    retry: 0,
  });
}

/** Knowledge base stats — polls every 60s */
export function useKnowledgeStats() {
  return useQuery({
    queryKey: ['knowledgeStats'],
    queryFn: () => apiClient.getKnowledgeStats(),
    refetchInterval: 60_000,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}
