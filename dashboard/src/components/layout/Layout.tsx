// ── Layout Shell — Sidebar + Header + Content ──

import { Outlet, useLocation } from 'react-router-dom';
import Sidebar from './Sidebar';
import Header from './Header';

const pageTitles: Record<string, string> = {
  '/': 'System Overview',
  '/requests': 'Requests & Load',
  '/models': 'Model Intelligence',
  '/latency': 'Latency & Performance',
  '/cost': 'Cost & Token Economics',
  '/drift': 'Drift & AI Quality',
  '/orgs': 'Organizations',
  '/policies': 'Policy Governance',
  '/probe': 'Live Probe',
  '/settings': 'System Settings',
};

export default function Layout() {
  const location = useLocation();
  const title = pageTitles[location.pathname] || 'Dashboard';

  return (
    <div className="app-layout">
      <Sidebar />
      <div className="main-content">
        <Header title={title} />
        <main className="page fade-in" key={location.pathname}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
