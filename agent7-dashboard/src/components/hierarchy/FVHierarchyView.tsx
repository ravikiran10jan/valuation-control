import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import {
  Layers,
  Eye,
  AlertTriangle,
  FileText,
  BarChart3,
} from 'lucide-react';
import { Card, KPICard } from '../shared/Card';
import { Badge } from '../shared/Button';
import { useApi } from '@/hooks/useApi';
import { api } from '@/services/api';
import {
  formatCurrency,
  formatNumber,
  cn,
} from '@/utils/format';
import type { FVHierarchySummary } from '@/types';

// ── Fallback data ──────────────────────────────────────────────

const fallbackHierarchy: FVHierarchySummary[] = [
  {
    level: 'L1',
    position_count: 1245,
    book_value: 6800000000,
    pct_of_total: 54.4,
    characteristics: 'Quoted prices in active markets for identical instruments',
    disclosure_level: 'Standard',
    audit_intensity: 'Low',
  },
  {
    level: 'L2',
    position_count: 987,
    book_value: 4200000000,
    pct_of_total: 33.6,
    characteristics: 'Observable inputs other than Level 1 quoted prices',
    disclosure_level: 'Enhanced',
    audit_intensity: 'Medium',
  },
  {
    level: 'L3',
    position_count: 255,
    book_value: 1500000000,
    pct_of_total: 12.0,
    characteristics: 'Unobservable inputs requiring significant judgment',
    disclosure_level: 'Full (IFRS 13.93)',
    audit_intensity: 'High -- Independent model validation required',
  },
];

const LEVEL_COLORS = {
  L1: '#10b981',
  L2: '#3b82f6',
  L3: '#ef4444',
};

const LEVEL_BG_COLORS = {
  L1: 'bg-green-50 border-green-200',
  L2: 'bg-blue-50 border-blue-200',
  L3: 'bg-red-50 border-red-200',
};

const LEVEL_ICONS = {
  L1: <Eye size={20} className="text-green-500" />,
  L2: <BarChart3 size={20} className="text-blue-500" />,
  L3: <AlertTriangle size={20} className="text-red-500" />,
};

const LEVEL_NAMES: Record<string, string> = {
  L1: 'Level 1 -- Quoted Prices',
  L2: 'Level 2 -- Observable Inputs',
  L3: 'Level 3 -- Unobservable Inputs',
};

// Fallback transfer data (used when backend is unavailable)
const fallbackTransfers = [
  { from: 'L2', to: 'L3', count: 8, reason: 'Market became illiquid' },
  { from: 'L3', to: 'L2', count: 3, reason: 'Observable prices became available' },
  { from: 'L1', to: 'L2', count: 5, reason: 'Delisted or reduced trading volume' },
  { from: 'L2', to: 'L1', count: 12, reason: 'Active market established' },
];

export function FVHierarchyView() {
  const { data: hierarchyData, error } = useApi(
    () => api.getFVHierarchy(),
    [],
    fallbackHierarchy
  );

  const { data: transfersData } = useApi(
    () => api.getFVLevelTransfers(),
    [],
    fallbackTransfers
  );

  const hierarchy = hierarchyData ?? fallbackHierarchy;
  const transferData = transfersData ?? fallbackTransfers;
  const totalPositions = hierarchy.reduce((s, h) => s + h.position_count, 0);
  const totalBookValue = hierarchy.reduce((s, h) => s + h.book_value, 0);

  const pieData = hierarchy.map((h) => ({
    name: h.level,
    value: h.book_value,
    fill: LEVEL_COLORS[h.level],
    count: h.position_count,
  }));

  const countData = hierarchy.map((h) => ({
    name: h.level,
    count: h.position_count,
    fill: LEVEL_COLORS[h.level],
  }));

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
          title="Total Positions"
          value={formatNumber(totalPositions)}
          icon={<Layers size={20} className="text-enterprise-500" />}
        />
        <KPICard
          title="Total Book Value"
          value={formatCurrency(totalBookValue, true)}
          icon={<BarChart3 size={20} className="text-blue-500" />}
        />
        {hierarchy.map((h) => (
          <KPICard
            key={h.level}
            title={`${h.level} Positions`}
            value={formatNumber(h.position_count)}
            trend={`${h.pct_of_total}% of total`}
            trendDirection="neutral"
            color={h.level === 'L3' ? 'red' : h.level === 'L2' ? 'default' : 'green'}
            icon={LEVEL_ICONS[h.level]}
          />
        ))}
      </div>

      {/* Level Detail Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {hierarchy.map((h) => (
          <div
            key={h.level}
            className={cn(
              'rounded-xl border p-6 shadow-enterprise-card',
              LEVEL_BG_COLORS[h.level]
            )}
          >
            <div className="flex items-start justify-between mb-4">
              <div>
                <h3 className="text-lg font-bold text-enterprise-800">{h.level}</h3>
                <p className="text-sm text-enterprise-600 mt-0.5">{LEVEL_NAMES[h.level]}</p>
              </div>
              {LEVEL_ICONS[h.level]}
            </div>

            <dl className="space-y-3">
              <div className="flex justify-between py-1.5">
                <dt className="text-sm text-enterprise-500">Positions</dt>
                <dd className="font-medium text-enterprise-800">{formatNumber(h.position_count)}</dd>
              </div>
              <div className="flex justify-between py-1.5">
                <dt className="text-sm text-enterprise-500">Book Value</dt>
                <dd className="font-mono font-medium text-enterprise-800">{formatCurrency(h.book_value, true)}</dd>
              </div>
              <div className="flex justify-between py-1.5">
                <dt className="text-sm text-enterprise-500">% of Total</dt>
                <dd className="font-medium text-enterprise-800">{h.pct_of_total}%</dd>
              </div>
              <div className="pt-3 border-t border-enterprise-200 space-y-2">
                <div>
                  <p className="text-xs font-semibold text-enterprise-600 uppercase tracking-wide">Characteristics</p>
                  <p className="text-sm text-enterprise-700 mt-0.5">{h.characteristics}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold text-enterprise-600 uppercase tracking-wide">Disclosure</p>
                  <p className="text-sm text-enterprise-700 mt-0.5">{h.disclosure_level}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold text-enterprise-600 uppercase tracking-wide">Audit Intensity</p>
                  <p className="text-sm text-enterprise-700 mt-0.5">{h.audit_intensity}</p>
                </div>
              </div>
            </dl>
          </div>
        ))}
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Book Value Distribution */}
        <Card title="Book Value by Level">
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={pieData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  innerRadius={50}
                  outerRadius={85}
                  paddingAngle={3}
                  label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
                  labelLine={{ stroke: '#64748b' }}
                >
                  {pieData.map((entry, idx) => (
                    <Cell key={`bv-${idx}`} fill={entry.fill} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#ffffff',
                    border: '1px solid #e2e8f0',
                    borderRadius: '8px',
                    boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)',
                  }}
                  formatter={(value: number) => formatCurrency(value, true)}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* Position Count by Level */}
        <Card title="Position Count by Level">
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={countData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis
                  dataKey="name"
                  stroke="#64748b"
                  tick={{ fontSize: 12, fill: '#64748b' }}
                />
                <YAxis
                  stroke="#64748b"
                  tick={{ fontSize: 12, fill: '#64748b' }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#ffffff',
                    border: '1px solid #e2e8f0',
                    borderRadius: '8px',
                  }}
                  formatter={(value: number) => formatNumber(value)}
                />
                <Bar dataKey="count" name="Positions" radius={[4, 4, 0, 0]}>
                  {countData.map((entry, idx) => (
                    <Cell key={`count-${idx}`} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      {/* Level Transfers */}
      <Card title="Level Transfer Tracking">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-enterprise-200 bg-enterprise-50">
                <th className="px-4 py-3 text-left text-enterprise-700 font-semibold">From</th>
                <th className="px-4 py-3 text-center text-enterprise-700 font-semibold">Direction</th>
                <th className="px-4 py-3 text-left text-enterprise-700 font-semibold">To</th>
                <th className="px-4 py-3 text-right text-enterprise-700 font-semibold">Positions</th>
                <th className="px-4 py-3 text-left text-enterprise-700 font-semibold">Reason</th>
                <th className="px-4 py-3 text-center text-enterprise-700 font-semibold">Impact</th>
              </tr>
            </thead>
            <tbody>
              {transferData.map((transfer, idx) => {
                const isUpgrade = (transfer.from === 'L3' && transfer.to === 'L2') ||
                  (transfer.from === 'L2' && transfer.to === 'L1') ||
                  (transfer.from === 'L3' && transfer.to === 'L1');
                return (
                  <tr key={idx} className="border-b border-enterprise-100 hover:bg-enterprise-50">
                    <td className="px-4 py-3">
                      <Badge
                        variant={transfer.from === 'L3' ? 'red' : transfer.from === 'L2' ? 'blue' : 'green'}
                        size="sm"
                      >
                        {transfer.from}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-center text-enterprise-500 text-lg">
                      &rarr;
                    </td>
                    <td className="px-4 py-3">
                      <Badge
                        variant={transfer.to === 'L3' ? 'red' : transfer.to === 'L2' ? 'blue' : 'green'}
                        size="sm"
                      >
                        {transfer.to}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-enterprise-800">
                      {transfer.count}
                    </td>
                    <td className="px-4 py-3 text-enterprise-600">{transfer.reason}</td>
                    <td className="px-4 py-3 text-center">
                      <Badge
                        variant={isUpgrade ? 'green' : 'amber'}
                        size="sm"
                      >
                        {isUpgrade ? 'Upgrade' : 'Downgrade'}
                      </Badge>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Disclosure Requirements */}
      <Card title="Disclosure Requirements by Level">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="p-4 bg-green-50 rounded-lg border border-green-200">
            <div className="flex items-center gap-2 mb-3">
              <FileText size={18} className="text-green-600" />
              <h4 className="font-semibold text-green-800">Level 1 Disclosure</h4>
            </div>
            <ul className="space-y-2 text-sm text-green-700">
              <li className="flex items-start gap-2">
                <span className="text-green-500 mt-0.5">&#x2022;</span>
                Fair value amounts by class
              </li>
              <li className="flex items-start gap-2">
                <span className="text-green-500 mt-0.5">&#x2022;</span>
                Transfers between levels
              </li>
              <li className="flex items-start gap-2">
                <span className="text-green-500 mt-0.5">&#x2022;</span>
                Standard valuation policy
              </li>
            </ul>
          </div>

          <div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
            <div className="flex items-center gap-2 mb-3">
              <FileText size={18} className="text-blue-600" />
              <h4 className="font-semibold text-blue-800">Level 2 Disclosure</h4>
            </div>
            <ul className="space-y-2 text-sm text-blue-700">
              <li className="flex items-start gap-2">
                <span className="text-blue-500 mt-0.5">&#x2022;</span>
                Description of valuation techniques
              </li>
              <li className="flex items-start gap-2">
                <span className="text-blue-500 mt-0.5">&#x2022;</span>
                Significant observable inputs
              </li>
              <li className="flex items-start gap-2">
                <span className="text-blue-500 mt-0.5">&#x2022;</span>
                Fair value amounts and transfers
              </li>
            </ul>
          </div>

          <div className="p-4 bg-red-50 rounded-lg border border-red-200">
            <div className="flex items-center gap-2 mb-3">
              <FileText size={18} className="text-red-600" />
              <h4 className="font-semibold text-red-800">Level 3 Disclosure (IFRS 13.93)</h4>
            </div>
            <ul className="space-y-2 text-sm text-red-700">
              <li className="flex items-start gap-2">
                <span className="text-red-500 mt-0.5">&#x2022;</span>
                Full reconciliation of movements
              </li>
              <li className="flex items-start gap-2">
                <span className="text-red-500 mt-0.5">&#x2022;</span>
                Unobservable inputs + sensitivity
              </li>
              <li className="flex items-start gap-2">
                <span className="text-red-500 mt-0.5">&#x2022;</span>
                Valuation process description
              </li>
              <li className="flex items-start gap-2">
                <span className="text-red-500 mt-0.5">&#x2022;</span>
                Inter-relationship of inputs
              </li>
            </ul>
          </div>
        </div>
      </Card>
    </div>
  );
}
