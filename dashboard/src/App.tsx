// ── App Root — Router + Query Provider ──

import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Layout from './components/layout/Layout';
import OverviewPage from './pages/OverviewPage';
import RequestsPage from './pages/RequestsPage';
import ModelsPage from './pages/ModelsPage';
import LatencyPage from './pages/LatencyPage';
import CostPage from './pages/CostPage';
import DriftPage from './pages/DriftPage';
import OrgsPage from './pages/OrgsPage';
import PoliciesPage from './pages/PoliciesPage';
import TestProbePage from './pages/TestProbePage';
import SettingsPage from './pages/SettingsPage';
import { SSEProvider } from './hooks/useSSE';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <SSEProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<Layout />}>
              <Route path="/" element={<OverviewPage />} />
              <Route path="/requests" element={<RequestsPage />} />
              <Route path="/models" element={<ModelsPage />} />
              <Route path="/latency" element={<LatencyPage />} />
              <Route path="/cost" element={<CostPage />} />
              <Route path="/drift" element={<DriftPage />} />
              <Route path="/orgs" element={<OrgsPage />} />
              <Route path="/policies" element={<PoliciesPage />} />
              <Route path="/probe" element={<TestProbePage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </SSEProvider>
    </QueryClientProvider>
  );
}
