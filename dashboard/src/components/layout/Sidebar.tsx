// ── Sidebar Navigation ──

import { NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  Activity,
  Cpu,
  Timer,
  DollarSign,
  ShieldAlert,
  Building2,
  ScrollText,
  FlaskConical,
  Settings,
} from 'lucide-react';

type NavSection = { section: string };
type NavItem = { to: string; icon: React.ComponentType; label: string };

const navItems: (NavSection | NavItem)[] = [
  { section: 'Monitor' },
  { to: '/', icon: LayoutDashboard, label: 'Overview' },
  { to: '/requests', icon: Activity, label: 'Requests & Load' },
  { to: '/models', icon: Cpu, label: 'Model Intelligence' },
  { to: '/latency', icon: Timer, label: 'Latency' },
  { section: 'Analytics' },
  { to: '/cost', icon: DollarSign, label: 'Cost & Tokens' },
  { to: '/drift', icon: ShieldAlert, label: 'Drift & Quality' },
  { section: 'Governance' },
  { to: '/orgs', icon: Building2, label: 'Organizations' },
  { to: '/policies', icon: ScrollText, label: 'Policies' },
  { to: '/probe', icon: FlaskConical, label: 'Live Probe' },
  { section: 'System' },
  { to: '/settings', icon: Settings, label: 'Settings' },
];

export default function Sidebar() {
  const location = useLocation();

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="sidebar-logo-icon">V</div>
        <div>
          <div className="sidebar-logo-text">Virtue-AI</div>
          <div className="sidebar-logo-sub">Control Plane</div>
        </div>
      </div>
      <nav className="sidebar-nav">
        {navItems.map((item, i) => {
          if ('section' in item) {
            return (
              <div key={i} className="sidebar-section-label">
                {item.section}
              </div>
            );
          }
          const isActive = location.pathname === item.to;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={`nav-link ${isActive ? 'active' : ''}`}
            >
              <item.icon />
              {item.label}
            </NavLink>
          );
        })}
      </nav>
    </aside>
  );
}
