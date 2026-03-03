import { Outlet, NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  ListChecks,
  FileText,
  Bell,
  Settings,
  ChevronDown,
  Menu,
  Building2,
  AlertTriangle,
  Activity,
  DollarSign,
  Landmark,
  Layers,
  ShieldCheck,
  FlaskConical,
  Grid3X3,
  BookOpen,
} from 'lucide-react';
import { useState } from 'react';
import { useAlerts } from '@/hooks/useAlerts';
import { cn } from '@/utils/format';
import { AlertPanel } from '../alerts/AlertPanel';

const navigation = [
  { name: 'Executive Dashboard', href: '/', icon: LayoutDashboard },
  { name: 'IPV Runs', href: '/ipv', icon: Activity },
  { name: 'Analyst Workbench', href: '/workbench', icon: ListChecks },
  { name: 'Exceptions', href: '/exceptions', icon: AlertTriangle },
  { name: 'Reserves', href: '/reserves', icon: DollarSign },
  { name: 'Day 1 P&L', href: '/day1-pnl', icon: BookOpen },
  { name: 'Capital Adequacy', href: '/capital', icon: Landmark },
  { name: 'FV Hierarchy', href: '/hierarchy', icon: Layers },
  { name: 'Validation', href: '/validation', icon: ShieldCheck },
  { name: 'Pricing Simulator', href: '/simulator', icon: FlaskConical },
  { name: 'Model Applicability', href: '/applicability', icon: Grid3X3 },
  { name: 'Reports', href: '/reports', icon: FileText },
];

const pageNames: Record<string, string> = {
  '/': 'Executive Dashboard',
  '/ipv': 'IPV Run Dashboard',
  '/workbench': 'Analyst Workbench',
  '/exceptions': 'Exceptions',
  '/reserves': 'Reserve Waterfall',
  '/day1-pnl': 'Day 1 P&L Dashboard',
  '/capital': 'Capital Adequacy',
  '/hierarchy': 'Fair Value Hierarchy',
  '/validation': 'Validation Dashboard',
  '/simulator': 'Pricing Simulator',
  '/applicability': 'Model Applicability Matrix',
  '/reports': 'Reports',
  '/settings': 'Settings',
};

export function Layout() {
  const location = useLocation();
  const { unreadCount } = useAlerts();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [alertsOpen, setAlertsOpen] = useState(false);

  const currentPageName = pageNames[location.pathname] ||
    (location.pathname.startsWith('/positions/') ? 'Position Detail' : 'Valuation Control');

  return (
    <div className="flex h-screen bg-enterprise-50 text-enterprise-800">
      {/* Sidebar */}
      <aside
        className={cn(
          'flex flex-col bg-white border-r border-enterprise-200 transition-all duration-300 shadow-enterprise-sm',
          sidebarOpen ? 'w-64' : 'w-16'
        )}
      >
        {/* Logo */}
        <div className="flex h-16 items-center justify-between px-4 border-b border-enterprise-200">
          {sidebarOpen && (
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 bg-primary-600 rounded-lg flex items-center justify-center">
                <Building2 size={18} className="text-white" />
              </div>
              <span className="text-lg font-semibold text-enterprise-800">
                Valuation Control
              </span>
            </div>
          )}
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="p-2 rounded-lg hover:bg-enterprise-100 text-enterprise-500 transition-colors"
          >
            <Menu size={20} />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
          {navigation.map((item) => {
            const isActive = location.pathname === item.href;
            return (
              <NavLink
                key={item.name}
                to={item.href}
                className={cn(
                  'flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-150',
                  isActive
                    ? 'bg-primary-50 text-primary-700 font-medium border border-primary-200'
                    : 'text-enterprise-600 hover:bg-enterprise-100 hover:text-enterprise-800'
                )}
              >
                <item.icon size={20} className={isActive ? 'text-primary-600' : ''} />
                {sidebarOpen && <span>{item.name}</span>}
              </NavLink>
            );
          })}
        </nav>

        {/* Settings */}
        <div className="p-3 border-t border-enterprise-200">
          <NavLink
            to="/settings"
            className={cn(
              'flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors w-full',
              location.pathname === '/settings'
                ? 'bg-primary-50 text-primary-700 font-medium border border-primary-200'
                : 'text-enterprise-600 hover:bg-enterprise-100 hover:text-enterprise-800'
            )}
          >
            <Settings size={20} className={location.pathname === '/settings' ? 'text-primary-600' : ''} />
            {sidebarOpen && <span>Settings</span>}
          </NavLink>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="flex h-16 items-center justify-between px-6 border-b border-enterprise-200 bg-white shadow-enterprise-sm">
          <h1 className="text-xl font-semibold text-enterprise-800">
            {currentPageName}
          </h1>

          <div className="flex items-center gap-3">
            {/* Alerts */}
            <div className="relative">
              <button
                onClick={() => setAlertsOpen(!alertsOpen)}
                className="relative p-2.5 rounded-lg hover:bg-enterprise-100 text-enterprise-500 transition-colors"
              >
                <Bell size={20} />
                {unreadCount > 0 && (
                  <span className="absolute -top-0.5 -right-0.5 flex h-5 w-5 items-center justify-center rounded-full bg-red-500 text-white text-xs font-medium shadow-sm">
                    {unreadCount > 9 ? '9+' : unreadCount}
                  </span>
                )}
              </button>
              {alertsOpen && (
                <AlertPanel onClose={() => setAlertsOpen(false)} />
              )}
            </div>

            {/* Divider */}
            <div className="h-8 w-px bg-enterprise-200" />

            {/* User menu */}
            <button className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-enterprise-100 transition-colors">
              <div className="h-9 w-9 rounded-full bg-gradient-to-br from-primary-500 to-primary-700 flex items-center justify-center text-sm font-semibold text-white shadow-sm">
                RK
              </div>
              <div className="text-left">
                <p className="text-sm font-medium text-enterprise-800">Ravikiran</p>
                <p className="text-xs text-enterprise-500">Analyst</p>
              </div>
              <ChevronDown size={16} className="text-enterprise-400" />
            </button>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-auto p-6 bg-enterprise-50">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
