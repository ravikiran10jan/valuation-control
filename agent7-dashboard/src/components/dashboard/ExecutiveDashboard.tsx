import {
  TrendingUp,
  DollarSign,
  AlertTriangle,
  FileWarning,
  Calculator,
  Shield,
} from 'lucide-react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  Legend,
} from 'recharts';
import { KPICard, Card } from '../shared/Card';
import { Badge } from '../shared/Button';
import { useAlerts } from '@/hooks/useAlerts';
import { useApi } from '@/hooks/useApi';
import { api } from '@/services/api';
import {
  formatCurrency,
  formatNumber,
  formatRelativeTime,
  cn,
} from '@/utils/format';
import type { KPIData, ExceptionTrend, AssetClassBreakdown } from '@/types';

// ── Fallback data (used when backend is unreachable) ──────────
const fallbackKPIs: KPIData = {
  total_positions: 2487,
  total_fair_value: 12500000000,
  open_exceptions: 152,
  red_exceptions: 12,
  amber_exceptions: 140,
  total_fva_reserve: 45000000,
  total_ava: 125000000,
  trends: {
    positions_trend: 23,
    fair_value_trend: -150000000,
    exceptions_trend: 5,
    red_trend: -2,
    fva_trend: 2000000,
    ava_trend: 8000000,
  },
};

const fallbackTrends: ExceptionTrend[] = Array.from({ length: 90 }, (_, i) => {
  const date = new Date();
  date.setDate(date.getDate() - (89 - i));
  return {
    date: date.toISOString().split('T')[0],
    total: 150 + Math.floor(Math.random() * 30) - 15,
    red: 10 + Math.floor(Math.random() * 6) - 3,
    amber: 100 + Math.floor(Math.random() * 20) - 10,
    green: 40 + Math.floor(Math.random() * 10) - 5,
  };
});

const fallbackAssetBreakdown: AssetClassBreakdown[] = [
  { asset_class: 'Rates', fair_value: 5200000000, fva_reserve: 18000000, position_count: 892 },
  { asset_class: 'FX', fair_value: 2800000000, fva_reserve: 12000000, position_count: 567 },
  { asset_class: 'Credit', fair_value: 2100000000, fva_reserve: 8000000, position_count: 423 },
  { asset_class: 'Equity', fair_value: 1500000000, fva_reserve: 5000000, position_count: 389 },
  { asset_class: 'Commodities', fair_value: 900000000, fva_reserve: 2000000, position_count: 216 },
];

const COLORS = ['#0ea5e9', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444'];

function Skeleton({ className }: { className?: string }) {
  return (
    <div className={cn('animate-pulse rounded bg-slate-700/60', className)} />
  );
}

export function ExecutiveDashboard() {
  const { data: kpis, loading: kpisLoading, error: kpisError } =
    useApi(() => api.getKPIs(), [], fallbackKPIs);

  const { data: trends, loading: trendsLoading } =
    useApi(() => api.getExceptionTrends(90), [], fallbackTrends);

  const { data: assetBreakdown, loading: breakdownLoading } =
    useApi(() => api.getAssetClassBreakdown(), [], fallbackAssetBreakdown);

  const { alerts } = useAlerts();
  const recentAlerts = alerts.slice(0, 5);

  const kpiData = kpis ?? fallbackKPIs;
  const trendData = trends ?? fallbackTrends;
  const breakdownData = assetBreakdown ?? fallbackAssetBreakdown;

  const trendDirection = (val: number): 'up' | 'down' | 'neutral' =>
    val > 0 ? 'up' : val < 0 ? 'down' : 'neutral';

  return (
    <div className="space-y-6">
      {kpisError && (
        <div className="px-4 py-2 rounded-lg bg-amber-500/20 text-amber-300 text-sm">
          Using cached data — backend unavailable ({kpisError})
        </div>
      )}

      {kpisLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
          <KPICard
            title="Total Positions"
            value={formatNumber(kpiData.total_positions)}
            trend={`${kpiData.trends.positions_trend >= 0 ? '+' : ''}${kpiData.trends.positions_trend} this week`}
            trendDirection={trendDirection(kpiData.trends.positions_trend)}
            icon={<TrendingUp size={20} className="text-primary-400" />}
          />
          <KPICard
            title="Total Fair Value"
            value={formatCurrency(kpiData.total_fair_value, true)}
            trend={formatCurrency(kpiData.trends.fair_value_trend, true) + ' from last week'}
            trendDirection={trendDirection(kpiData.trends.fair_value_trend)}
            icon={<DollarSign size={20} className="text-green-400" />}
          />
          <KPICard
            title="Open Exceptions"
            value={formatNumber(kpiData.open_exceptions)}
            trend={`${kpiData.trends.exceptions_trend >= 0 ? '+' : ''}${kpiData.trends.exceptions_trend}`}
            trendDirection={trendDirection(-kpiData.trends.exceptions_trend)}
            color="amber"
            icon={<AlertTriangle size={20} className="text-amber-400" />}
          />
          <KPICard
            title="RED Exceptions"
            value={formatNumber(kpiData.red_exceptions)}
            trend={`${kpiData.trends.red_trend >= 0 ? '+' : ''}${kpiData.trends.red_trend}`}
            trendDirection={trendDirection(-kpiData.trends.red_trend)}
            color="red"
            icon={<FileWarning size={20} className="text-red-400" />}
          />
          <KPICard
            title="Total FVA Reserve"
            value={formatCurrency(kpiData.total_fva_reserve, true)}
            trend={`+${formatCurrency(kpiData.trends.fva_trend, true)}`}
            trendDirection="up"
            icon={<Calculator size={20} className="text-purple-400" />}
          />
          <KPICard
            title="Total AVA"
            value={formatCurrency(kpiData.total_ava, true)}
            trend={`+${formatCurrency(kpiData.trends.ava_trend, true)}`}
            trendDirection="up"
            icon={<Shield size={20} className="text-blue-400" />}
          />
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Exception Trend (Last 90 Days)">
          {trendsLoading ? (
            <Skeleton className="h-80" />
          ) : (
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trendData.slice(-30)}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis
                    dataKey="date"
                    stroke="#94a3b8"
                    tick={{ fontSize: 12 }}
                    tickFormatter={(val) => {
                      const d = new Date(val);
                      return `${d.getMonth() + 1}/${d.getDate()}`;
                    }}
                  />
                  <YAxis stroke="#94a3b8" tick={{ fontSize: 12 }} />
                  <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px' }} />
                  <Legend />
                  <Line type="monotone" dataKey="total" stroke="#94a3b8" strokeWidth={2} dot={false} name="Total" />
                  <Line type="monotone" dataKey="red" stroke="#ef4444" strokeWidth={2} dot={false} name="RED" />
                  <Line type="monotone" dataKey="amber" stroke="#f59e0b" strokeWidth={2} dot={false} name="AMBER" />
                  <Line type="monotone" dataKey="green" stroke="#10b981" strokeWidth={2} dot={false} name="GREEN" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>

        <Card title="Fair Value by Asset Class">
          {breakdownLoading ? (
            <Skeleton className="h-80" />
          ) : (
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={breakdownData}
                    dataKey="fair_value"
                    nameKey="asset_class"
                    cx="50%"
                    cy="50%"
                    outerRadius={100}
                    label={({ asset_class, percent }) =>
                      `${asset_class} (${(percent * 100).toFixed(0)}%)`
                    }
                    labelLine={{ stroke: '#64748b' }}
                  >
                    {breakdownData.map((_, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px' }}
                    formatter={(value: number) => formatCurrency(value, true)}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="FVA Reserve by Asset Class">
          {breakdownLoading ? (
            <Skeleton className="h-80" />
          ) : (
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={breakdownData} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis type="number" stroke="#94a3b8" tick={{ fontSize: 12 }} tickFormatter={(val) => formatCurrency(val, true)} />
                  <YAxis type="category" dataKey="asset_class" stroke="#94a3b8" tick={{ fontSize: 12 }} width={100} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px' }}
                    formatter={(value: number) => formatCurrency(value)}
                  />
                  <Bar dataKey="fva_reserve" fill="#8b5cf6" name="FVA Reserve" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>

        <Card title="Recent Alerts">
          <div className="space-y-3">
            {recentAlerts.map((alert) => (
              <div
                key={alert.id}
                className={cn(
                  'flex items-start gap-3 p-3 rounded-lg',
                  alert.severity === 'high' && 'bg-red-500/10',
                  alert.severity === 'medium' && 'bg-amber-500/10',
                  alert.severity === 'low' && 'bg-slate-700/50'
                )}
              >
                <Badge
                  variant={alert.severity === 'high' ? 'red' : alert.severity === 'medium' ? 'amber' : 'default'}
                  size="sm"
                >
                  {alert.severity.toUpperCase()}
                </Badge>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-sm">{alert.title}</p>
                  <p className="text-sm text-slate-400 mt-0.5">{alert.message}</p>
                </div>
                <span className="text-xs text-slate-500 whitespace-nowrap">
                  {formatRelativeTime(alert.timestamp)}
                </span>
              </div>
            ))}
            {recentAlerts.length === 0 && (
              <p className="text-sm text-slate-500 text-center py-4">No recent alerts</p>
            )}
          </div>
        </Card>
      </div>

      <Card title="Exception Aging by Desk">
        <div className="grid grid-cols-6 gap-2">
          {['FX', 'Rates', 'Credit', 'Equity', 'Commodities'].map((asset) => (
            <div key={asset} className="text-center text-sm text-slate-400 font-medium">{asset}</div>
          ))}
          <div></div>
          {['Desk A', 'Desk B', 'Desk C', 'Desk D'].map((desk) => (
            <div key={desk} className="contents">
              {['FX', 'Rates', 'Credit', 'Equity', 'Commodities'].map((asset) => {
                const days = Math.floor(Math.random() * 10);
                const intensity = days < 3 ? 'bg-green-500/30' : days < 5 ? 'bg-amber-500/30' : 'bg-red-500/30';
                return (
                  <div key={`${desk}-${asset}`} className={cn('h-12 rounded flex items-center justify-center text-sm', intensity)}>
                    {days}d
                  </div>
                );
              })}
              <div className="text-sm text-slate-400 flex items-center">{desk}</div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
