import { useState } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  PieChart,
  Pie,
} from 'recharts';
import {
  DollarSign,
  Shield,
  TrendingDown,
  Layers,
} from 'lucide-react';
import { Card, KPICard } from '../shared/Card';
import { Badge, Tabs } from '../shared/Button';
import { useApi } from '@/hooks/useApi';
import { api } from '@/services/api';
import { formatCurrency } from '@/utils/format';
import type { ReserveWaterfallData } from '@/types';

// ── Fallback data ──────────────────────────────────────────────

const fallbackData: ReserveWaterfallData = {
  positions: [
    { position_id: 7, currency_pair: 'EUR/USD', asset_class: 'FX', notional_usd: 50000000, fva: 8500, ava: 45200, model_reserve: 12100, day1_deferred: 119000, total_reserve: 184800 },
    { position_id: 12, currency_pair: 'GBP/USD', asset_class: 'FX', notional_usd: 75000000, fva: 12300, ava: 38500, model_reserve: 8900, day1_deferred: 0, total_reserve: 59700 },
    { position_id: 23, currency_pair: 'USD/JPY', asset_class: 'FX', notional_usd: 100000000, fva: 15600, ava: 52100, model_reserve: 0, day1_deferred: 0, total_reserve: 67700 },
    { position_id: 34, currency_pair: 'US 10Y IRS', asset_class: 'Rates', notional_usd: 200000000, fva: 28400, ava: 85600, model_reserve: 15200, day1_deferred: 0, total_reserve: 129200 },
    { position_id: 45, currency_pair: 'EUR 5Y IRS', asset_class: 'Rates', notional_usd: 150000000, fva: 22100, ava: 64300, model_reserve: 0, day1_deferred: 0, total_reserve: 86400 },
    { position_id: 56, currency_pair: 'XAU/USD', asset_class: 'Commodities', notional_usd: 30000000, fva: 4200, ava: 18900, model_reserve: 5600, day1_deferred: 0, total_reserve: 28700 },
    { position_id: 67, currency_pair: 'CDX.NA.IG', asset_class: 'Credit', notional_usd: 80000000, fva: 11800, ava: 42700, model_reserve: 9400, day1_deferred: 85000, total_reserve: 148900 },
    { position_id: 78, currency_pair: 'SPX Options', asset_class: 'Equity', notional_usd: 60000000, fva: 9100, ava: 31200, model_reserve: 7800, day1_deferred: 0, total_reserve: 48100 },
  ],
  totals: {
    total_fva: 45000000,
    total_ava: 125000000,
    total_model_reserve: 18500000,
    total_day1_deferred: 8200000,
    grand_total: 196700000,
  },
};

const AVA_CATEGORIES = [
  { name: 'Market Price Uncertainty', value: 42500000, pct: 34 },
  { name: 'Close-Out Costs', value: 25000000, pct: 20 },
  { name: 'Model Risk', value: 22500000, pct: 18 },
  { name: 'Unearned Credit Spreads', value: 12500000, pct: 10 },
  { name: 'Investment & Funding', value: 10000000, pct: 8 },
  { name: 'Concentrated Positions', value: 7500000, pct: 6 },
  { name: 'Future Admin Costs', value: 5000000, pct: 4 },
];

const RESERVE_COLORS = {
  fva: '#8b5cf6',
  ava: '#3b82f6',
  model_reserve: '#10b981',
  day1_deferred: '#f59e0b',
};

const AVA_COLORS = ['#3b82f6', '#6366f1', '#8b5cf6', '#a78bfa', '#c4b5fd', '#ddd6fe', '#ede9fe'];

export function ReserveWaterfall() {
  const [activeTab, setActiveTab] = useState('waterfall');

  const { data: reserveData, error } = useApi(
    () => api.getReservesDetail(),
    [],
    fallbackData
  );

  const data = reserveData ?? fallbackData;
  const totals = data.totals;

  // Waterfall chart data — shows how each component builds to grand total
  const waterfallData = [
    { name: 'FVA', value: totals.total_fva, fill: RESERVE_COLORS.fva },
    { name: 'AVA', value: totals.total_ava, fill: RESERVE_COLORS.ava },
    { name: 'Model Reserve', value: totals.total_model_reserve, fill: RESERVE_COLORS.model_reserve },
    { name: 'Day1 Deferred', value: totals.total_day1_deferred, fill: RESERVE_COLORS.day1_deferred },
    { name: 'Grand Total', value: totals.grand_total, fill: '#1e293b' },
  ];

  const tabs = [
    { id: 'waterfall', label: 'Reserve Waterfall' },
    { id: 'ava', label: 'AVA Breakdown' },
    { id: 'positions', label: 'By Position' },
  ];

  return (
    <div className="space-y-6">
      {error && (
        <div className="px-4 py-2 rounded-lg bg-amber-50 text-amber-700 text-sm border border-amber-200">
          Using cached data -- backend unavailable ({error})
        </div>
      )}

      {/* KPI Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
        <KPICard
          title="Total FVA"
          value={formatCurrency(totals.total_fva, true)}
          icon={<DollarSign size={20} className="text-purple-500" />}
        />
        <KPICard
          title="Total AVA"
          value={formatCurrency(totals.total_ava, true)}
          icon={<Shield size={20} className="text-blue-500" />}
        />
        <KPICard
          title="Model Reserve"
          value={formatCurrency(totals.total_model_reserve, true)}
          icon={<TrendingDown size={20} className="text-green-500" />}
        />
        <KPICard
          title="Day1 Deferred"
          value={formatCurrency(totals.total_day1_deferred, true)}
          icon={<Layers size={20} className="text-amber-500" />}
        />
        <KPICard
          title="Grand Total"
          value={formatCurrency(totals.grand_total, true)}
          color="red"
          icon={<DollarSign size={20} className="text-red-500" />}
        />
      </div>

      {/* Tabs */}
      <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab} />

      {/* Waterfall Tab */}
      {activeTab === 'waterfall' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card title="Reserve Composition">
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={waterfallData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis
                    dataKey="name"
                    stroke="#64748b"
                    tick={{ fontSize: 11, fill: '#64748b' }}
                  />
                  <YAxis
                    stroke="#64748b"
                    tick={{ fontSize: 12, fill: '#64748b' }}
                    tickFormatter={(val) => formatCurrency(val, true)}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#ffffff',
                      border: '1px solid #e2e8f0',
                      borderRadius: '8px',
                      boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)',
                    }}
                    formatter={(value: number) => formatCurrency(value)}
                  />
                  <Bar dataKey="value" name="Amount" radius={[4, 4, 0, 0]}>
                    {waterfallData.map((entry, idx) => (
                      <Cell key={`cell-${idx}`} fill={entry.fill} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <Card title="Reserve Mix">
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={waterfallData.slice(0, 4)}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={80}
                    paddingAngle={2}
                    label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
                    labelLine={{ stroke: '#64748b' }}
                  >
                    {waterfallData.slice(0, 4).map((entry, idx) => (
                      <Cell key={`pie-${idx}`} fill={entry.fill} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#ffffff',
                      border: '1px solid #e2e8f0',
                      borderRadius: '8px',
                    }}
                    formatter={(value: number) => formatCurrency(value)}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-4 space-y-2">
              {waterfallData.slice(0, 4).map((item) => {
                const pct = totals.grand_total > 0 ? (Number(item.value) / Number(totals.grand_total) * 100).toFixed(1) : '0';
                return (
                  <div key={item.name} className="flex items-center justify-between text-sm">
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full" style={{ backgroundColor: item.fill }} />
                      <span className="text-enterprise-600">{item.name}</span>
                    </div>
                    <div className="flex items-center gap-4">
                      <span className="font-mono text-enterprise-800">{formatCurrency(item.value, true)}</span>
                      <span className="text-enterprise-500 w-12 text-right">{pct}%</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>
        </div>
      )}

      {/* AVA Breakdown Tab */}
      {activeTab === 'ava' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card title="AVA by Category (Basel III Article 105)">
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={AVA_CATEGORIES} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis
                    type="number"
                    stroke="#64748b"
                    tick={{ fontSize: 11, fill: '#64748b' }}
                    tickFormatter={(val) => formatCurrency(val, true)}
                  />
                  <YAxis
                    type="category"
                    dataKey="name"
                    stroke="#64748b"
                    tick={{ fontSize: 11, fill: '#64748b' }}
                    width={170}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#ffffff',
                      border: '1px solid #e2e8f0',
                      borderRadius: '8px',
                    }}
                    formatter={(value: number) => formatCurrency(value)}
                  />
                  <Bar dataKey="value" name="AVA Amount" radius={[0, 4, 4, 0]}>
                    {AVA_CATEGORIES.map((_, idx) => (
                      <Cell key={`ava-${idx}`} fill={AVA_COLORS[idx]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <Card title="7 AVA Categories Detail">
            <div className="space-y-3">
              {AVA_CATEGORIES.map((cat, idx) => (
                <div key={cat.name} className="space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-enterprise-700">{cat.name}</span>
                    <span className="text-sm font-mono text-enterprise-800">
                      {formatCurrency(cat.value, true)} ({cat.pct}%)
                    </span>
                  </div>
                  <div className="h-2 bg-enterprise-100 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all"
                      style={{
                        width: `${cat.pct}%`,
                        backgroundColor: AVA_COLORS[idx],
                      }}
                    />
                  </div>
                </div>
              ))}
              <div className="flex items-center justify-between pt-3 border-t border-enterprise-200 mt-4">
                <span className="font-semibold text-enterprise-700">Total AVA</span>
                <span className="font-bold font-mono text-enterprise-800">
                  {formatCurrency(totals.total_ava, true)}
                </span>
              </div>
            </div>
          </Card>
        </div>
      )}

      {/* By Position Tab */}
      {activeTab === 'positions' && (
        <Card title="Reserve Breakdown by Position">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-enterprise-200 bg-enterprise-50">
                  <th className="px-4 py-3 text-left text-enterprise-700 font-semibold">Position</th>
                  <th className="px-4 py-3 text-left text-enterprise-700 font-semibold">Pair / Instrument</th>
                  <th className="px-4 py-3 text-left text-enterprise-700 font-semibold">Asset Class</th>
                  <th className="px-4 py-3 text-right text-enterprise-700 font-semibold">Notional</th>
                  <th className="px-4 py-3 text-right text-enterprise-700 font-semibold">FVA</th>
                  <th className="px-4 py-3 text-right text-enterprise-700 font-semibold">AVA</th>
                  <th className="px-4 py-3 text-right text-enterprise-700 font-semibold">Model Res.</th>
                  <th className="px-4 py-3 text-right text-enterprise-700 font-semibold">Day1</th>
                  <th className="px-4 py-3 text-right text-enterprise-700 font-semibold">Total</th>
                </tr>
              </thead>
              <tbody>
                {data.positions.map((pos) => (
                  <tr key={pos.position_id} className="border-b border-enterprise-100 hover:bg-enterprise-50">
                    <td className="px-4 py-3 font-mono text-enterprise-700">
                      #{pos.position_id}
                    </td>
                    <td className="px-4 py-3 text-enterprise-700">{pos.currency_pair}</td>
                    <td className="px-4 py-3">
                      <Badge variant="default" size="sm">{pos.asset_class}</Badge>
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-enterprise-700">
                      {formatCurrency(pos.notional_usd, true)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-purple-600">
                      {formatCurrency(pos.fva)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-blue-600">
                      {formatCurrency(pos.ava)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-green-600">
                      {formatCurrency(pos.model_reserve)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-amber-600">
                      {pos.day1_deferred > 0 ? formatCurrency(pos.day1_deferred) : '-'}
                    </td>
                    <td className="px-4 py-3 text-right font-mono font-medium text-enterprise-800">
                      {formatCurrency(pos.total_reserve)}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="bg-enterprise-50 border-t-2 border-enterprise-300">
                  <td colSpan={4} className="px-4 py-3 font-semibold text-enterprise-700">
                    Total ({data.positions.length} positions shown)
                  </td>
                  <td className="px-4 py-3 text-right font-mono font-semibold text-purple-700">
                    {formatCurrency(data.positions.reduce((s, p) => s + p.fva, 0))}
                  </td>
                  <td className="px-4 py-3 text-right font-mono font-semibold text-blue-700">
                    {formatCurrency(data.positions.reduce((s, p) => s + p.ava, 0))}
                  </td>
                  <td className="px-4 py-3 text-right font-mono font-semibold text-green-700">
                    {formatCurrency(data.positions.reduce((s, p) => s + p.model_reserve, 0))}
                  </td>
                  <td className="px-4 py-3 text-right font-mono font-semibold text-amber-700">
                    {formatCurrency(data.positions.reduce((s, p) => s + p.day1_deferred, 0))}
                  </td>
                  <td className="px-4 py-3 text-right font-mono font-bold text-enterprise-800">
                    {formatCurrency(data.positions.reduce((s, p) => s + p.total_reserve, 0))}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
