import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  MessageSquare,
  TrendingUp,
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
  BarChart,
  Bar,
  Cell,
  Legend,
} from 'recharts';
import { Card, KPICard } from '../shared/Card';
import { Button, Badge, Tabs } from '../shared/Button';
import { useApi } from '@/hooks/useApi';
import { api } from '@/services/api';
import {
  formatCurrency,
  formatPercent,
  formatDate,
  formatDateTime,
  cn,
} from '@/utils/format';
import type { PositionDeepDiveData, ValuationComparison, Greek, Dispute } from '@/types';

// ── Fallback data ──────────────────────────────────────────────

const fallbackPosition: PositionDeepDiveData = {
  position_id: 7,
  trade_id: 'FX-OPT-001',
  product_type: 'Barrier (DNT)',
  asset_class: 'FX',
  currency_pair: 'EUR/USD',
  notional: 50000000,
  notional_usd: 50000000,
  currency: 'EUR',
  trade_date: '2025-01-05',
  maturity_date: '2025-12-31',
  settlement_date: '2026-01-02',
  counterparty: 'Structured Products Client F',
  desk_mark: 425000,
  vc_fair_value: 306000,
  book_value_usd: 850000,
  difference: 119000,
  difference_pct: -28,
  exception_status: 'RED',
  fair_value_level: 'L3',
  pricing_source: 'Internal BS Model',
  fva_usd: 8500,
  valuation_date: '2025-02-14',
  created_at: '2025-01-05T10:00:00Z',
  updated_at: '2025-02-14T16:00:00Z',
  reserves: {
    fva: 8500,
    ava: 45200,
    model_reserve: 12100,
    day_1_pnl: 119000,
  },
  comparison_history: Array.from({ length: 20 }, (_, i) => {
    const d = new Date();
    d.setDate(d.getDate() - (19 - i));
    const deskMark = 425000 + (Math.random() - 0.5) * 10000;
    const vcValue = 306000 + (Math.random() - 0.5) * 8000;
    const diff = deskMark - vcValue;
    return {
      comparison_id: i + 1,
      position_id: 7,
      desk_mark: deskMark,
      vc_fair_value: vcValue,
      difference: diff,
      difference_pct: (diff / vcValue) * 100,
      status: Math.abs(diff / vcValue) > 0.15 ? 'RED' : Math.abs(diff / vcValue) > 0.05 ? 'AMBER' : 'GREEN',
      comparison_date: d.toISOString().split('T')[0],
      created_at: d.toISOString(),
    } as ValuationComparison;
  }),
  greeks: {
    position_id: 7,
    greeks: [
      { name: 'Delta', value: -15000, unit: 'USD per 1% spot move' },
      { name: 'Vega', value: -21000, unit: 'USD per 1% vol' },
      { name: 'Gamma', value: 450, unit: 'USD per (1% spot)^2' },
      { name: 'Theta', value: 120, unit: 'USD per day' },
      { name: 'Rho', value: -3200, unit: 'USD per 1% rate' },
    ],
  },
  disputes: [],
};

function StatusIcon({ status }: { status: string | null }) {
  switch (status) {
    case 'RED':
      return <XCircle size={16} className="text-red-500" />;
    case 'AMBER':
      return <AlertTriangle size={16} className="text-amber-500" />;
    case 'GREEN':
    default:
      return <CheckCircle2 size={16} className="text-green-500" />;
  }
}

export function PositionDeepDive() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('overview');

  const positionId = parseInt(id ?? '7', 10);

  const { data: positionData, error } = useApi(
    () => api.getIPVPositionDetail(positionId),
    [positionId],
    fallbackPosition
  );

  const position = positionData ?? fallbackPosition;
  const reserves = position.reserves ?? { fva: 0, ava: 0, model_reserve: 0, day_1_pnl: 0 };
  const totalReserve = reserves.fva + reserves.ava + reserves.model_reserve + reserves.day_1_pnl;
  const greeksList: Greek[] = position.greeks?.greeks ?? [];
  const compHistory: ValuationComparison[] = position.comparison_history ?? [];
  const disputes: Dispute[] = position.disputes ?? [];

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'valuation', label: 'Desk Mark vs IPV' },
    { id: 'greeks', label: 'Greeks' },
    { id: 'reserves', label: 'Reserves' },
    { id: 'disputes', label: `Disputes (${disputes.length})` },
  ];

  const reserveBreakdownData = [
    { name: 'FVA', value: reserves.fva, fill: '#8b5cf6' },
    { name: 'AVA', value: reserves.ava, fill: '#3b82f6' },
    { name: 'Model Reserve', value: reserves.model_reserve, fill: '#10b981' },
    { name: 'Day1 P&L', value: reserves.day_1_pnl, fill: '#f59e0b' },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-4">
          <Button
            variant="ghost"
            icon={<ArrowLeft size={18} />}
            onClick={() => navigate(-1)}
          >
            Back
          </Button>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-enterprise-800">
                Position #{positionId}
              </h1>
              <Badge
                variant={
                  position.exception_status === 'RED'
                    ? 'red'
                    : position.exception_status === 'AMBER'
                    ? 'amber'
                    : 'green'
                }
              >
                {position.exception_status ?? 'GREEN'}
              </Badge>
              {position.fair_value_level && (
                <Badge variant="blue">{position.fair_value_level}</Badge>
              )}
            </div>
            <p className="text-sm text-enterprise-500 mt-1">
              {position.product_type} &middot; {position.currency_pair} &middot; {position.asset_class}
            </p>
          </div>
        </div>
      </div>

      {error && (
        <div className="px-4 py-2 rounded-lg bg-amber-50 text-amber-700 text-sm border border-amber-200">
          Using cached data -- backend unavailable ({error})
        </div>
      )}

      {/* KPI Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
        <KPICard
          title="Notional"
          value={formatCurrency(position.notional_usd, true)}
          icon={<TrendingUp size={20} className="text-blue-500" />}
        />
        <KPICard
          title="Desk Mark"
          value={formatCurrency(position.desk_mark)}
          icon={<TrendingUp size={20} className="text-enterprise-500" />}
        />
        <KPICard
          title="VC Fair Value"
          value={formatCurrency(position.vc_fair_value)}
          color={position.exception_status === 'RED' ? 'red' : position.exception_status === 'AMBER' ? 'amber' : 'green'}
          icon={<StatusIcon status={position.exception_status} />}
        />
        <KPICard
          title="Difference"
          value={`${formatCurrency(position.difference)} (${formatPercent(position.difference_pct)})`}
          color={position.exception_status === 'RED' ? 'red' : position.exception_status === 'AMBER' ? 'amber' : 'default'}
        />
        <KPICard
          title="Total Reserve"
          value={formatCurrency(totalReserve)}
          icon={<Shield size={20} className="text-purple-500" />}
        />
      </div>

      {/* Tabs */}
      <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab} />

      {/* Tab Content */}
      {activeTab === 'overview' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card title="Position Details">
            <dl className="space-y-3">
              {[
                ['Trade ID', position.trade_id],
                ['Product Type', position.product_type],
                ['Asset Class', position.asset_class],
                ['Currency Pair', position.currency_pair],
                ['Notional', formatCurrency(position.notional)],
                ['Currency', position.currency],
                ['Trade Date', formatDate(position.trade_date)],
                ['Maturity Date', formatDate(position.maturity_date)],
                ['Settlement Date', position.settlement_date ? formatDate(position.settlement_date) : 'N/A'],
                ['Counterparty', position.counterparty],
                ['Fair Value Level', position.fair_value_level ?? 'N/A'],
                ['Pricing Source', position.pricing_source ?? 'N/A'],
              ].map(([label, value], idx) => (
                <div
                  key={label}
                  className={cn(
                    'flex justify-between py-2',
                    idx < 11 && 'border-b border-enterprise-100'
                  )}
                >
                  <dt className="text-enterprise-500">{label}</dt>
                  <dd className="font-medium text-enterprise-800">{value}</dd>
                </div>
              ))}
            </dl>
          </Card>

          <Card title="Tolerance Check">
            <div className="space-y-6">
              <div className="flex items-center justify-between p-4 rounded-lg bg-enterprise-50 border border-enterprise-200">
                <div>
                  <p className="text-sm text-enterprise-500">Tolerance Result</p>
                  <div className="flex items-center gap-2 mt-1">
                    <StatusIcon status={position.exception_status} />
                    <span className="text-lg font-bold text-enterprise-800">
                      {position.exception_status ?? 'GREEN'}
                    </span>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-sm text-enterprise-500">Difference</p>
                  <p className={cn(
                    'text-lg font-bold',
                    position.exception_status === 'RED' ? 'text-red-600' :
                    position.exception_status === 'AMBER' ? 'text-amber-600' : 'text-green-600'
                  )}>
                    {formatPercent(position.difference_pct)}
                  </p>
                </div>
              </div>

              <div>
                <h4 className="text-sm font-semibold text-enterprise-700 mb-3">Tolerance Thresholds</h4>
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-sm">
                    <span className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full bg-green-500" />
                      GREEN
                    </span>
                    <span className="text-enterprise-500">&le; 5% difference</span>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full bg-amber-500" />
                      AMBER
                    </span>
                    <span className="text-enterprise-500">5% - 15% difference</span>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full bg-red-500" />
                      RED
                    </span>
                    <span className="text-enterprise-500">&gt; 15% difference</span>
                  </div>
                </div>
              </div>

              <div>
                <h4 className="text-sm font-semibold text-enterprise-700 mb-3">Valuation Timeline</h4>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-enterprise-500">Last Valued</span>
                    <span className="text-enterprise-800">{formatDateTime(position.updated_at)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-enterprise-500">Created</span>
                    <span className="text-enterprise-800">{formatDateTime(position.created_at)}</span>
                  </div>
                </div>
              </div>
            </div>
          </Card>
        </div>
      )}

      {activeTab === 'valuation' && (
        <div className="space-y-6">
          <Card title="Desk Mark vs IPV Price History">
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={compHistory}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis
                    dataKey="comparison_date"
                    stroke="#64748b"
                    tick={{ fontSize: 11, fill: '#64748b' }}
                    tickFormatter={(val) => {
                      const d = new Date(val);
                      return `${d.getMonth() + 1}/${d.getDate()}`;
                    }}
                  />
                  <YAxis
                    stroke="#64748b"
                    tick={{ fontSize: 12, fill: '#64748b' }}
                    tickFormatter={(val) => `$${(val / 1000).toFixed(0)}k`}
                    domain={['auto', 'auto']}
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
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="desk_mark"
                    stroke="#f59e0b"
                    strokeWidth={2}
                    dot={false}
                    name="Desk Mark"
                  />
                  <Line
                    type="monotone"
                    dataKey="vc_fair_value"
                    stroke="#3b82f6"
                    strokeWidth={2}
                    dot={false}
                    name="VC Fair Value"
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <Card title="Comparison History">
            <div className="overflow-x-auto max-h-96 overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-white">
                  <tr className="border-b border-enterprise-200 bg-enterprise-50">
                    <th className="px-4 py-3 text-left text-enterprise-700 font-semibold">Date</th>
                    <th className="px-4 py-3 text-right text-enterprise-700 font-semibold">Desk Mark</th>
                    <th className="px-4 py-3 text-right text-enterprise-700 font-semibold">VC Fair Value</th>
                    <th className="px-4 py-3 text-right text-enterprise-700 font-semibold">Difference</th>
                    <th className="px-4 py-3 text-right text-enterprise-700 font-semibold">Diff %</th>
                    <th className="px-4 py-3 text-center text-enterprise-700 font-semibold">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {compHistory.map((comp) => (
                    <tr key={comp.comparison_id} className="border-b border-enterprise-100 hover:bg-enterprise-50">
                      <td className="px-4 py-3 text-enterprise-600">
                        {formatDate(comp.comparison_date)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-enterprise-800">
                        {formatCurrency(comp.desk_mark)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-enterprise-800">
                        {formatCurrency(comp.vc_fair_value)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-enterprise-800">
                        {formatCurrency(comp.difference)}
                      </td>
                      <td className={cn(
                        'px-4 py-3 text-right font-mono',
                        comp.status === 'RED' ? 'text-red-600' :
                        comp.status === 'AMBER' ? 'text-amber-600' : 'text-green-600'
                      )}>
                        {formatPercent(comp.difference_pct)}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <Badge
                          variant={
                            comp.status === 'RED' ? 'red' :
                            comp.status === 'AMBER' ? 'amber' : 'green'
                          }
                          size="sm"
                        >
                          {comp.status}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}

      {activeTab === 'greeks' && (
        <Card title="Greeks Summary">
          {greeksList.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-enterprise-200 bg-enterprise-50">
                    <th className="px-4 py-3 text-left text-enterprise-700 font-semibold">Greek</th>
                    <th className="px-4 py-3 text-right text-enterprise-700 font-semibold">Value</th>
                    <th className="px-4 py-3 text-right text-enterprise-700 font-semibold">Unit</th>
                  </tr>
                </thead>
                <tbody>
                  {greeksList.map((greek) => (
                    <tr key={greek.name} className="border-b border-enterprise-100">
                      <td className="px-4 py-3 font-medium text-enterprise-800">
                        {greek.name}
                      </td>
                      <td className={cn(
                        'px-4 py-3 text-right font-mono',
                        greek.value >= 0 ? 'text-green-600' : 'text-red-600'
                      )}>
                        {formatCurrency(greek.value)}
                      </td>
                      <td className="px-4 py-3 text-right text-enterprise-500">
                        {greek.unit}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-12 text-enterprise-500">
              <p>No Greeks data available for this position.</p>
              <p className="text-sm mt-1">Greeks are computed by the Pricing Engine (Agent 2).</p>
            </div>
          )}
        </Card>
      )}

      {activeTab === 'reserves' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card title="Reserve Breakdown">
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={reserveBreakdownData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis
                    dataKey="name"
                    stroke="#64748b"
                    tick={{ fontSize: 12, fill: '#64748b' }}
                  />
                  <YAxis
                    stroke="#64748b"
                    tick={{ fontSize: 12, fill: '#64748b' }}
                    tickFormatter={(val) => `$${(val / 1000).toFixed(0)}k`}
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
                    {reserveBreakdownData.map((entry, idx) => (
                      <Cell key={`cell-${idx}`} fill={entry.fill} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <Card title="Reserve Detail">
            <dl className="space-y-3">
              <div className="flex justify-between py-2 border-b border-enterprise-100">
                <dt className="text-enterprise-500">FVA (Funding Valuation Adjustment)</dt>
                <dd className="font-mono font-medium text-enterprise-800">{formatCurrency(reserves.fva)}</dd>
              </div>
              <div className="flex justify-between py-2 border-b border-enterprise-100">
                <dt className="text-enterprise-500">AVA (Additional Valuation Adjustment)</dt>
                <dd className="font-mono font-medium text-enterprise-800">{formatCurrency(reserves.ava)}</dd>
              </div>
              <div className="flex justify-between py-2 border-b border-enterprise-100">
                <dt className="text-enterprise-500">Model Reserve</dt>
                <dd className="font-mono font-medium text-enterprise-800">{formatCurrency(reserves.model_reserve)}</dd>
              </div>
              <div className="flex justify-between py-2 border-b border-enterprise-100">
                <dt className="text-enterprise-500">Day 1 P&L (Deferred)</dt>
                <dd className="font-mono font-medium text-enterprise-800">{formatCurrency(reserves.day_1_pnl)}</dd>
              </div>
              <div className="flex justify-between py-2 bg-enterprise-50 rounded-lg px-3 mt-2">
                <dt className="font-semibold text-enterprise-700">Total Reserve</dt>
                <dd className="font-bold font-mono text-enterprise-800">{formatCurrency(totalReserve)}</dd>
              </div>
            </dl>
          </Card>
        </div>
      )}

      {activeTab === 'disputes' && (
        <Card title="Dispute History">
          {disputes.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-enterprise-200 bg-enterprise-50">
                    <th className="px-4 py-3 text-left text-enterprise-700 font-semibold">Dispute ID</th>
                    <th className="px-4 py-3 text-left text-enterprise-700 font-semibold">State</th>
                    <th className="px-4 py-3 text-left text-enterprise-700 font-semibold">VC Analyst</th>
                    <th className="px-4 py-3 text-left text-enterprise-700 font-semibold">Desk Trader</th>
                    <th className="px-4 py-3 text-right text-enterprise-700 font-semibold">Difference</th>
                    <th className="px-4 py-3 text-left text-enterprise-700 font-semibold">Created</th>
                    <th className="px-4 py-3 text-left text-enterprise-700 font-semibold">Resolution</th>
                  </tr>
                </thead>
                <tbody>
                  {disputes.map((dispute) => (
                    <tr key={dispute.dispute_id} className="border-b border-enterprise-100 hover:bg-enterprise-50">
                      <td className="px-4 py-3 font-mono text-enterprise-700">
                        #{dispute.dispute_id}
                      </td>
                      <td className="px-4 py-3">
                        <Badge
                          variant={
                            dispute.state.includes('RESOLVED') ? 'green' :
                            dispute.state === 'ESCALATED' ? 'red' : 'blue'
                          }
                          size="sm"
                        >
                          {dispute.state.replace(/_/g, ' ')}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-enterprise-600">{dispute.vc_analyst}</td>
                      <td className="px-4 py-3 text-enterprise-600">{dispute.desk_trader ?? 'N/A'}</td>
                      <td className="px-4 py-3 text-right font-mono text-enterprise-800">
                        {dispute.difference != null ? formatCurrency(dispute.difference) : 'N/A'}
                      </td>
                      <td className="px-4 py-3 text-enterprise-600">{formatDate(dispute.created_date)}</td>
                      <td className="px-4 py-3 text-enterprise-600">
                        {dispute.resolution_type ?? 'Pending'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-12 text-enterprise-500">
              <MessageSquare size={48} className="mx-auto mb-4 text-enterprise-300" />
              <p className="text-lg font-medium">No disputes for this position</p>
              <p className="text-sm mt-1">Disputes are created when tolerance breaches occur</p>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
