import React, { createContext, useContext, useEffect, useRef, useState } from 'react';
import type { MetricsResponse, ModelHealthSummary } from '../api/types';
import apiClient from '../api/client';

export interface SSEPayload {
  metrics: MetricsResponse;
  models: ModelHealthSummary[];
  timestamp: string;
}

interface SSEState {
  data: SSEPayload | null;
  connected: boolean;
  error: string | null;
}

const SSEContext = createContext<SSEState>({
  data: null,
  connected: false,
  error: null,
});

const SSE_URL = '/internal/stream';
const RECONNECT_BASE_MS = 1_000;
const RECONNECT_MAX_MS = 30_000;

export const SSEProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [state, setState] = useState<SSEState>({
    data: null,
    connected: false,
    error: null,
  });

  const esRef = useRef<EventSource | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);
  const attemptRef = useRef(0);

  const connect = () => {
    if (!mountedRef.current) return;

    const token = apiClient.getToken();
    if (!token) {
      reconnectTimer.current = setTimeout(connect, 1000);
      return;
    }

    if (esRef.current) {
      esRef.current.close();
    }

    const url = `${SSE_URL}?token=${encodeURIComponent(token)}`;
    const es = new EventSource(url);
    esRef.current = es;

    es.onopen = () => {
      if (!mountedRef.current) return;
      attemptRef.current = 0;
      setState(s => ({ ...s, connected: true, error: null }));
    };

    es.onmessage = (event) => {
      if (!mountedRef.current) return;
      try {
        const payload: SSEPayload = JSON.parse(event.data);
        setState(s => ({ ...s, data: payload, connected: true }));
      } catch {
        // malformed push — ignore, keep connection alive
      }
    };

    es.onerror = () => {
      if (!mountedRef.current) return;
      es.close();
      setState(s => ({ ...s, connected: false, error: 'Stream disconnected — reconnecting…' }));
      // Exponential backoff: 1s → 2s → 4s → 8s → 16s → 30s (cap)
      const delay = Math.min(RECONNECT_BASE_MS * 2 ** attemptRef.current, RECONNECT_MAX_MS);
      attemptRef.current += 1;
      reconnectTimer.current = setTimeout(connect, delay);
    };
  };

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      esRef.current?.close();
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    };
  }, []);

  return (
    <SSEContext.Provider value={state}>
      {children}
    </SSEContext.Provider>
  );
};

export const useSSE = () => useContext(SSEContext);
