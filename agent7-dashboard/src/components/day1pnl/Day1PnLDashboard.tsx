import { useState, useMemo } from 'react';
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
  AreaChart,
  Area,
  Legend,
} from 'recharts';
import {
  AlertTriangle,
  CheckCircle,
  Shield,
  DollarSign,
  Clock,
  AlertOctagon,
  Calendar,
  Filter,
} from 'lucide-react';
import { Card, KPICard } from '../shared/Card';
import { Badge, Tabs } from '../shared/Button';
import { formatCurrency } from '@/utils/format';

// ── Types ───────────────────────────────────────────────────────

interface AmortizationEntry {
  period_date: string;
  amortization_amount: number;
  cumulative_recognized: number;
  remaining_deferred: number;
}

interface AccountingEntry {
  entry_id: string;
  entry_date: string;
  description: string;
  debit_account: string;
  credit_account: string;
  amount: number;
  position_id: number;
  entry_type: string;
}

interface RedFlag {
  flag_id: string;
  flag_name: string;
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'SEVERE';
  description: string;
  triggered: boolean;
  threshold?: string;
  actual_value?: string;
}

interface Day1PnLPosition {
  position_id: number;
  trade_id: string;
  transaction_price: number;
  fair_value: number;
  day1_pnl: number;
  day1_pnl_pct: number;
  classification: 'SUSPICIOUS' | 'NORMAL' | 'IDEAL';
  classification_reason: string;
  recognition_status: 'RECOGNIZED' | 'DEFERRED';
  recognized_amount: number;
  deferred_amount: number;
  reserve_balance: number;
  trade_date: string | null;
  maturity_date: string | null;
  amortization_method: string;
  amortization_schedule: AmortizationEntry[];
  accounting_entries: AccountingEntry[];
  red_flag_report?: {
    position_id: number;
    trade_id: string;
    total_flags_triggered: number;
    max_severity: string | null;
    flags: RedFlag[];
    requires_escalation: boolean;
    escalation_reason: string | null;
  };
  is_expired: boolean;
  released_on_expiry: boolean;
}

// ── Fallback Data ───────────────────────────────────────────────

const fallbackPositions: Day1PnLPosition[] = [
  {
    position_id: 101, trade_id: 'TRD-2025-0301', transaction_price: 1250000, fair_value: 1180000,
    day1_pnl: 70000, day1_pnl_pct: 5.93, classification: 'NORMAL', classification_reason: 'Day 1 P&L is 5.9% of FV — within normal range',
    recognition_status: 'RECOGNIZED', recognized_amount: 70000, deferred_amount: 0, reserve_balance: 0,
    trade_date: '2025-01-15', maturity_date: '2026-01-15', amortization_method: 'STRAIGHT_LINE',
    amortization_schedule: [], accounting_entries: [
      { entry_id: 'a1', entry_date: '2025-01-15', description: 'Day 1 P&L recognized', debit_account: 'Trading Revenue', credit_account: 'Day 1 P&L Reserve', amount: 70000, position_id: 101, entry_type: 'RESERVE_CREATION' },
    ],
    red_flag_report: { position_id: 101, trade_id: 'TRD-2025-0301', total_flags_triggered: 0, max_severity: null, flags: [], requires_escalation: false, escalation_reason: null },
    is_expired: false, released_on_expiry: false,
  },
  {
    position_id: 102, trade_id: 'TRD-2025-0302', transaction_price: 5400000, fair_value: 4200000,
    day1_pnl: 1200000, day1_pnl_pct: 28.57, classification: 'SUSPICIOUS', classification_reason: 'Day 1 P&L is 28.6% of FV — exceeds 20% threshold',
    recognition_status: 'DEFERRED', recognized_amount: 0, deferred_amount: 1200000, reserve_balance: 900000,
    trade_date: '2025-02-01', maturity_date: '2027-02-01', amortization_method: 'STRAIGHT_LINE',
    amortization_schedule: [
      { period_date: '2025-03-01', amortization_amount: 50000, cumulative_recognized: 50000, remaining_deferred: 1150000 },
      { period_date: '2025-04-01', amortization_amount: 50000, cumulative_recognized: 100000, remaining_deferred: 1100000 },
      { period_date: '2025-05-01', amortization_amount: 50000, cumulative_recognized: 150000, remaining_deferred: 1050000 },
      { period_date: '2025-06-01', amortization_amount: 50000, cumulative_recognized: 200000, remaining_deferred: 1000000 },
      { period_date: '2025-07-01', amortization_amount: 50000, cumulative_recognized: 250000, remaining_deferred: 950000 },
      { period_date: '2025-08-01', amortization_amount: 50000, cumulative_recognized: 300000, remaining_deferred: 900000 },
    ],
    accounting_entries: [
      { entry_id: 'b1', entry_date: '2025-02-01', description: 'Day 1 P&L reserve creation — position #102', debit_account: 'Trading Revenue', credit_account: 'Day 1 P&L Reserve', amount: 1200000, position_id: 102, entry_type: 'RESERVE_CREATION' },
      { entry_id: 'b2', entry_date: '2025-03-01', description: 'Day 1 P&L amortization', debit_account: 'Day 1 P&L Reserve', credit_account: 'Trading Revenue', amount: 50000, position_id: 102, entry_type: 'AMORTIZATION' },
      { entry_id: 'b3', entry_date: '2025-04-01', description: 'Day 1 P&L amortization', debit_account: 'Day 1 P&L Reserve', credit_account: 'Trading Revenue', amount: 50000, position_id: 102, entry_type: 'AMORTIZATION' },
    ],
    red_flag_report: {
      position_id: 102, trade_id: 'TRD-2025-0302', total_flags_triggered: 2, max_severity: 'SEVERE',
      flags: [
        { flag_id: 'RF1', flag_name: 'Client Overpaid for Derivative', severity: 'SEVERE', description: 'Premium 28.6% above market FV — significantly exceeds 20% threshold', triggered: true, threshold: '20%', actual_value: '28.6%' },
        { flag_id: 'RF4', flag_name: 'Earnings Manipulation Risk', severity: 'HIGH', description: 'Large Day 1 gain on illiquid product', triggered: true },
      ],
      requires_escalation: true, escalation_reason: 'SEVERE: Client Overpaid for Derivative',
    },
    is_expired: false, released_on_expiry: false,
  },
  {
    position_id: 103, trade_id: 'TRD-2025-0303', transaction_price: 890000, fair_value: 885000,
    day1_pnl: 5000, day1_pnl_pct: 0.56, classification: 'IDEAL', classification_reason: 'Day 1 P&L is 0.6% of FV — minimal difference',
    recognition_status: 'RECOGNIZED', recognized_amount: 5000, deferred_amount: 0, reserve_balance: 0,
    trade_date: '2025-01-20', maturity_date: '2025-07-20', amortization_method: 'STRAIGHT_LINE',
    amortization_schedule: [], accounting_entries: [],
    red_flag_report: { position_id: 103, trade_id: 'TRD-2025-0303', total_flags_triggered: 0, max_severity: null, flags: [], requires_escalation: false, escalation_reason: null },
    is_expired: false, released_on_expiry: false,
  },
  {
    position_id: 104, trade_id: 'TRD-2024-0815', transaction_price: 3200000, fair_value: 2800000,
    day1_pnl: 400000, day1_pnl_pct: 14.29, classification: 'NORMAL', classification_reason: 'Day 1 P&L is 14.3% of FV — within normal range',
    recognition_status: 'DEFERRED', recognized_amount: 0, deferred_amount: 400000, reserve_balance: 0,
    trade_date: '2024-08-15', maturity_date: '2025-02-15', amortization_method: 'FV_CONVERGENCE',
    amortization_schedule: [
      { period_date: '2024-09-15', amortization_amount: 114286, cumulative_recognized: 114286, remaining_deferred: 285714 },
      { period_date: '2024-10-15', amortization_amount: 95238, cumulative_recognized: 209524, remaining_deferred: 190476 },
      { period_date: '2024-11-15', amortization_amount: 76190, cumulative_recognized: 285714, remaining_deferred: 114286 },
      { period_date: '2024-12-15', amortization_amount: 57143, cumulative_recognized: 342857, remaining_deferred: 57143 },
      { period_date: '2025-01-15', amortization_amount: 38095, cumulative_recognized: 380952, remaining_deferred: 19048 },
      { period_date: '2025-02-15', amortization_amount: 19048, cumulative_recognized: 400000, remaining_deferred: 0 },
    ],
    accounting_entries: [
      { entry_id: 'c1', entry_date: '2024-08-15', description: 'Day 1 P&L reserve creation — position #104', debit_account: 'Trading Revenue', credit_account: 'Day 1 P&L Reserve', amount: 400000, position_id: 104, entry_type: 'RESERVE_CREATION' },
      { entry_id: 'c7', entry_date: '2025-02-15', description: 'Day 1 P&L reserve released on expiry', debit_account: 'Day 1 P&L Reserve', credit_account: 'Trading Revenue', amount: 0, position_id: 104, entry_type: 'EXPIRY_RELEASE' },
    ],
    red_flag_report: { position_id: 104, trade_id: 'TRD-2024-0815', total_flags_triggered: 0, max_severity: null, flags: [], requires_escalation: false, escalation_reason: null },
    is_expired: true, released_on_expiry: true,
  },
  {
    position_id: 105, trade_id: 'TRD-2025-0220', transaction_price: 7800000, fair_value: 6100000,
    day1_pnl: 1700000, day1_pnl_pct: 27.87, classification: 'SUSPICIOUS', classification_reason: 'SEVERE red flag: Client Overpaid for Derivative',
    recognition_status: 'DEFERRED', recognized_amount: 0, deferred_amount: 1700000, reserve_balance: 1700000,
    trade_date: '2025-02-20', maturity_date: '2028-02-20', amortization_method: 'ACCELERATED_RELEASE',
    amortization_schedule: [
      { period_date: '2025-03-20', amortization_amount: 850000, cumulative_recognized: 850000, remaining_deferred: 850000 },
      { period_date: '2025-04-20', amortization_amount: 425000, cumulative_recognized: 1275000, remaining_deferred: 425000 },
      { period_date: '2025-05-20', amortization_amount: 212500, cumulative_recognized: 1487500, remaining_deferred: 212500 },
    ],
    accounting_entries: [
      { entry_id: 'd1', entry_date: '2025-02-20', description: 'Day 1 P&L reserve creation — position #105', debit_account: 'Trading Revenue', credit_account: 'Day 1 P&L Reserve', amount: 1700000, position_id: 105, entry_type: 'RESERVE_CREATION' },
      { entry_id: 'd2', entry_date: '2025-03-20', description: 'Day 1 P&L amortization', debit_account: 'Day 1 P&L Reserve', credit_account: 'Trading Revenue', amount: 850000, position_id: 105, entry_type: 'AMORTIZATION' },
    ],
    red_flag_report: {
      position_id: 105, trade_id: 'TRD-2025-0220', total_flags_triggered: 3, max_severity: 'SEVERE',
      flags: [
        { flag_id: 'RF1', flag_name: 'Client Overpaid for Derivative', severity: 'SEVERE', description: 'Premium 27.9% above FV', triggered: true, threshold: '20%', actual_value: '27.9%' },
        { flag_id: 'RF2', flag_name: 'No Observable Market', severity: 'HIGH', description: 'Level 3 — no observable market inputs', triggered: true },
        { flag_id: 'RF3', flag_name: 'Bank Has Information Advantage', severity: 'MEDIUM', description: 'Asymmetric information on exotic product', triggered: true },
      ],
      requires_escalation: true, escalation_reason: 'SEVERE: Client Overpaid for Derivative',
    },
    is_expired: false, released_on_expiry: false,
  },
  {
    position_id: 106, trade_id: 'TRD-2025-0110', transaction_price: 2100000, fair_value: 2080000,
    day1_pnl: 20000, day1_pnl_pct: 0.96, classification: 'IDEAL', classification_reason: 'Day 1 P&L is 1.0% of FV — minimal difference',
    recognition_status: 'RECOGNIZED', recognized_amount: 20000, deferred_amount: 0, reserve_balance: 0,
    trade_date: '2025-01-10', maturity_date: '2026-01-10', amortization_method: 'STRAIGHT_LINE',
    amortization_schedule: [], accounting_entries: [],
    red_flag_report: { position_id: 106, trade_id: 'TRD-2025-0110', total_flags_triggered: 0, max_severity: null, flags: [], requires_escalation: false, escalation_reason: null },
    is_expired: false, released_on_expiry: false,
  },
  {
    position_id: 107, trade_id: 'TRD-2025-0205', transaction_price: 4500000, fair_value: 4100000,
    day1_pnl: 400000, day1_pnl_pct: 9.76, classification: 'NORMAL', classification_reason: 'Day 1 P&L is 9.8% of FV — within normal range',
    recognition_status: 'DEFERRED', recognized_amount: 0, deferred_amount: 400000, reserve_balance: 350000,
    trade_date: '2025-02-05', maturity_date: '2026-08-05', amortization_method: 'STRAIGHT_LINE',
    amortization_schedule: [
      { period_date: '2025-03-05', amortization_amount: 22222, cumulative_recognized: 22222, remaining_deferred: 377778 },
      { period_date: '2025-04-05', amortization_amount: 22222, cumulative_recognized: 44444, remaining_deferred: 355556 },
      { period_date: '2025-05-05', amortization_amount: 22222, cumulative_recognized: 66667, remaining_deferred: 333333 },
    ],
    accounting_entries: [
      { entry_id: 'e1', entry_date: '2025-02-05', description: 'Day 1 P&L reserve creation — position #107', debit_account: 'Trading Revenue', credit_account: 'Day 1 P&L Reserve', amount: 400000, position_id: 107, entry_type: 'RESERVE_CREATION' },
      { entry_id: 'e2', entry_date: '2025-03-05', description: 'Day 1 P&L amortization', debit_account: 'Day 1 P&L Reserve', credit_account: 'Trading Revenue', amount: 22222, position_id: 107, entry_type: 'AMORTIZATION' },
    ],
    red_flag_report: { position_id: 107, trade_id: 'TRD-2025-0205', total_flags_triggered: 1, max_severity: 'MEDIUM', flags: [
      { flag_id: 'RF6', flag_name: 'Frequent Re-marks', severity: 'MEDIUM', description: 'Position revalued 4 times in 30 days', triggered: true, threshold: '3 re-marks / 30 days', actual_value: '4 re-marks' },
    ], requires_escalation: false, escalation_reason: null },
    is_expired: false, released_on_expiry: false,
  },
  {
    position_id: 108, trade_id: 'TRD-2025-0125', transaction_price: 1600000, fair_value: 1590000,
    day1_pnl: 10000, day1_pnl_pct: 0.63, classification: 'IDEAL', classification_reason: 'Day 1 P&L is 0.6% of FV — minimal difference',
    recognition_status: 'RECOGNIZED', recognized_amount: 10000, deferred_amount: 0, reserve_balance: 0,
    trade_date: '2025-01-25', maturity_date: '2025-07-25', amortization_method: 'STRAIGHT_LINE',
    amortization_schedule: [], accounting_entries: [],
    red_flag_report: { position_id: 108, trade_id: 'TRD-2025-0125', total_flags_triggered: 0, max_severity: null, flags: [], requires_escalation: false, escalation_reason: null },
    is_expired: false, released_on_expiry: false,
  },
];

// ── Classification colors ───────────────────────────────────────

const CLASS_CONFIG = {
  SUSPICIOUS: { color: 'text-red-700', bg: 'bg-red-50', border: 'border-red-200', badge: 'bg-red-100 text-red-800', icon: AlertOctagon, iconColor: 'text-red-500' },
  NORMAL:     { color: 'text-amber-700', bg: 'bg-amber-50', border: 'border-amber-200', badge: 'bg-amber-100 text-amber-800', icon: Shield, iconColor: 'text-amber-500' },
  IDEAL:      { color: 'text-green-700', bg: 'bg-green-50', border: 'border-green-200', badge: 'bg-green-100 text-green-800', icon: CheckCircle, iconColor: 'text-green-500' },
};

const SEVERITY_COLORS: Record<string, string> = {
  SEVERE: 'bg-red-100 text-red-800 border-red-300',
  HIGH:   'bg-orange-100 text-orange-800 border-orange-300',
  MEDIUM: 'bg-amber-100 text-amber-800 border-amber-300',
  LOW:    'bg-blue-100 text-blue-800 border-blue-300',
};

const METHOD_LABELS: Record<string, string> = {
  STRAIGHT_LINE: 'Straight Line',
  FV_CONVERGENCE: 'FV Convergence',
  ACCELERATED_RELEASE: 'Accelerated Release',
};

// ── Component ───────────────────────────────────────────────────

export function Day1PnLDashboard() {
  const [activeTab, setActiveTab] = useState('overview');
  const [selectedPosition, setSelectedPosition] = useState<Day1PnLPosition | null>(null);
  const [classFilter, setClassFilter] = useState<string>('ALL');

  const positions = fallbackPositions;

  // Filtered positions
  const filtered = useMemo(
    () => classFilter === 'ALL' ? positions : positions.filter(p => p.classification === classFilter),
    [positions, classFilter]
  );

  // Summary stats
  const summary = useMemo(() => {
    const suspicious = positions.filter(p => p.classification === 'SUSPICIOUS');
    const normal = positions.filter(p => p.classification === 'NORMAL');
    const ideal = positions.filter(p => p.classification === 'IDEAL');
    return {
      total: positions.length,
      totalDay1PnL: positions.reduce((s, p) => s + p.day1_pnl, 0),
      totalDeferred: positions.reduce((s, p) => s + Math.abs(p.deferred_amount), 0),
      totalReserve: positions.reduce((s, p) => s + p.reserve_balance, 0),
      suspicious: suspicious.length,
      normal: normal.length,
      ideal: ideal.length,
      totalRedFlags: positions.reduce((s, p) => s + (p.red_flag_report?.total_flags_triggered ?? 0), 0),
      expired: positions.filter(p => p.is_expired).length,
    };
  }, [positions]);

  // Chart data — classification pie
  const classificationPie = [
    { name: 'Suspicious', value: summary.suspicious, fill: '#ef4444' },
    { name: 'Normal', value: summary.normal, fill: '#f59e0b' },
    { name: 'Ideal', value: summary.ideal, fill: '#22c55e' },
  ];

  // Chart data — reserve by position
  const reserveBar = positions
    .filter(p => p.reserve_balance > 0 || Math.abs(p.deferred_amount) > 0)
    .map(p => ({
      name: `#${p.position_id}`,
      reserve: p.reserve_balance,
      amortized: Math.abs(p.deferred_amount) - p.reserve_balance,
      classification: p.classification,
    }));

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'positions', label: 'Positions' },
    { id: 'amortization', label: 'Amortization' },
    { id: 'accounting', label: 'Accounting Entries' },
    { id: 'redflags', label: 'Red Flags' },
  ];

  return (
    <div className="space-y-6">
      {/* KPI Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
        <KPICard
          title="Total Day 1 P&L"
          value={formatCurrency(summary.totalDay1PnL, true)}
          icon={<DollarSign size={20} className="text-blue-500" />}
        />
        <KPICard
          title="Total Reserve"
          value={formatCurrency(summary.totalReserve, true)}
          icon={<Shield size={20} className="text-purple-500" />}
        />
        <KPICard
          title="Suspicious"
          value={String(summary.suspicious)}
          color="red"
          icon={<AlertOctagon size={20} className="text-red-500" />}
        />
        <KPICard
          title="Red Flags"
          value={String(summary.totalRedFlags)}
          color={summary.totalRedFlags > 0 ? 'red' : undefined}
          icon={<AlertTriangle size={20} className="text-orange-500" />}
        />
        <KPICard
          title="Expired / Released"
          value={String(summary.expired)}
          icon={<Clock size={20} className="text-gray-500" />}
        />
      </div>

      {/* Tabs */}
      <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab} />

      {/* ── Overview Tab ────────────────────────────────────────── */}
      {activeTab === 'overview' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Classification Pie */}
          <Card title="Day 1 P&L Classification">
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={classificationPie}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={55}
                    outerRadius={90}
                    paddingAngle={3}
                    label={({ name, value }) => `${name}: ${value}`}
                    labelLine={{ stroke: '#64748b' }}
                  >
                    {classificationPie.map((entry, idx) => (
                      <Cell key={`pie-${idx}`} fill={entry.fill} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ backgroundColor: '#fff', border: '1px solid #e2e8f0', borderRadius: '8px' }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-2 space-y-2">
              {classificationPie.map(item => (
                <div key={item.name} className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full" style={{ backgroundColor: item.fill }} />
                    <span className="text-enterprise-600">{item.name}</span>
                  </div>
                  <span className="font-mono text-enterprise-800">{item.value} positions</span>
                </div>
              ))}
            </div>
          </Card>

          {/* Reserve Balance Bar Chart */}
          <Card title="Reserve Balance by Position">
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={reserveBar}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="name" stroke="#64748b" tick={{ fontSize: 11 }} />
                  <YAxis stroke="#64748b" tick={{ fontSize: 11 }} tickFormatter={v => formatCurrency(v, true)} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#fff', border: '1px solid #e2e8f0', borderRadius: '8px' }}
                    formatter={(value: number) => formatCurrency(value)}
                  />
                  <Legend />
                  <Bar dataKey="reserve" name="Remaining Reserve" stackId="a" fill="#8b5cf6" radius={[0, 0, 0, 0]} />
                  <Bar dataKey="amortized" name="Amortized" stackId="a" fill="#c4b5fd" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>

          {/* Accounting Summary */}
          <Card title="Accounting Treatment" className="lg:col-span-2">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="p-4 rounded-lg bg-red-50 border border-red-200">
                <h4 className="text-sm font-semibold text-red-800 mb-2">Reserve Creation</h4>
                <div className="flex items-center gap-2 text-sm text-red-700">
                  <span className="font-mono font-semibold">Dr</span>
                  <span>Trading Revenue</span>
                </div>
                <div className="flex items-center gap-2 text-sm text-red-700 mt-1">
                  <span className="font-mono font-semibold">Cr</span>
                  <span>Day 1 P&L Reserve</span>
                </div>
                <div className="mt-2 text-xs text-red-600">
                  Total created: {formatCurrency(summary.totalDeferred)}
                </div>
              </div>
              <div className="p-4 rounded-lg bg-green-50 border border-green-200">
                <h4 className="text-sm font-semibold text-green-800 mb-2">Monthly Amortization</h4>
                <div className="flex items-center gap-2 text-sm text-green-700">
                  <span className="font-mono font-semibold">Dr</span>
                  <span>Day 1 P&L Reserve</span>
                </div>
                <div className="flex items-center gap-2 text-sm text-green-700 mt-1">
                  <span className="font-mono font-semibold">Cr</span>
                  <span>Trading Revenue</span>
                </div>
                <div className="mt-2 text-xs text-green-600">
                  Released to date: {formatCurrency(summary.totalDeferred - summary.totalReserve)}
                </div>
              </div>
              <div className="p-4 rounded-lg bg-blue-50 border border-blue-200">
                <h4 className="text-sm font-semibold text-blue-800 mb-2">Expiry Release</h4>
                <div className="flex items-center gap-2 text-sm text-blue-700">
                  <span className="font-mono font-semibold">Dr</span>
                  <span>Day 1 P&L Reserve</span>
                </div>
                <div className="flex items-center gap-2 text-sm text-blue-700 mt-1">
                  <span className="font-mono font-semibold">Cr</span>
                  <span>Trading Revenue</span>
                </div>
                <div className="mt-2 text-xs text-blue-600">
                  Expired: {summary.expired} positions
                </div>
              </div>
            </div>
          </Card>
        </div>
      )}

      {/* ── Positions Tab ───────────────────────────────────────── */}
      {activeTab === 'positions' && (
        <div className="space-y-4">
          {/* Filter bar */}
          <div className="flex items-center gap-3">
            <Filter size={16} className="text-enterprise-500" />
            <span className="text-sm text-enterprise-600">Filter:</span>
            {['ALL', 'SUSPICIOUS', 'NORMAL', 'IDEAL'].map(f => (
              <button
                key={f}
                onClick={() => setClassFilter(f)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  classFilter === f
                    ? f === 'SUSPICIOUS' ? 'bg-red-100 text-red-800 border border-red-300'
                    : f === 'NORMAL' ? 'bg-amber-100 text-amber-800 border border-amber-300'
                    : f === 'IDEAL' ? 'bg-green-100 text-green-800 border border-green-300'
                    : 'bg-primary-100 text-primary-800 border border-primary-300'
                    : 'bg-enterprise-100 text-enterprise-600 hover:bg-enterprise-200'
                }`}
              >
                {f === 'ALL' ? `All (${positions.length})` : `${f} (${positions.filter(p => p.classification === f).length})`}
              </button>
            ))}
          </div>

          <Card title={`Day 1 P&L Positions (${filtered.length})`}>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-enterprise-200 bg-enterprise-50">
                    <th className="px-4 py-3 text-left text-enterprise-700 font-semibold">Position</th>
                    <th className="px-4 py-3 text-left text-enterprise-700 font-semibold">Classification</th>
                    <th className="px-4 py-3 text-right text-enterprise-700 font-semibold">Txn Price</th>
                    <th className="px-4 py-3 text-right text-enterprise-700 font-semibold">Fair Value</th>
                    <th className="px-4 py-3 text-right text-enterprise-700 font-semibold">Day 1 P&L</th>
                    <th className="px-4 py-3 text-right text-enterprise-700 font-semibold">P&L %</th>
                    <th className="px-4 py-3 text-left text-enterprise-700 font-semibold">Status</th>
                    <th className="px-4 py-3 text-right text-enterprise-700 font-semibold">Reserve</th>
                    <th className="px-4 py-3 text-left text-enterprise-700 font-semibold">Method</th>
                    <th className="px-4 py-3 text-center text-enterprise-700 font-semibold">Flags</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map(pos => {
                    const cfg = CLASS_CONFIG[pos.classification];
                    return (
                      <tr
                        key={pos.position_id}
                        className={`border-b border-enterprise-100 hover:bg-enterprise-50 cursor-pointer ${
                          pos.classification === 'SUSPICIOUS' ? 'bg-red-50/30' : ''
                        }`}
                        onClick={() => setSelectedPosition(pos)}
                      >
                        <td className="px-4 py-3">
                          <div className="font-mono text-enterprise-700">#{pos.position_id}</div>
                          <div className="text-xs text-enterprise-500">{pos.trade_id}</div>
                        </td>
                        <td className="px-4 py-3">
                          <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium ${cfg.badge}`}>
                            <cfg.icon size={12} />
                            {pos.classification}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-enterprise-700">
                          {formatCurrency(pos.transaction_price)}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-enterprise-700">
                          {formatCurrency(pos.fair_value)}
                        </td>
                        <td className={`px-4 py-3 text-right font-mono font-medium ${pos.day1_pnl > 0 ? 'text-green-600' : 'text-red-600'}`}>
                          {formatCurrency(pos.day1_pnl)}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-enterprise-600">
                          {Number(pos.day1_pnl_pct).toFixed(1)}%
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-1.5">
                            <Badge
                              variant={pos.recognition_status === 'DEFERRED' ? 'amber' : 'default'}
                              size="sm"
                            >
                              {pos.recognition_status}
                            </Badge>
                            {pos.is_expired && (
                              <Badge variant="default" size="sm">EXPIRED</Badge>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-purple-600">
                          {pos.reserve_balance > 0 ? formatCurrency(pos.reserve_balance) : '-'}
                        </td>
                        <td className="px-4 py-3 text-xs text-enterprise-600">
                          {METHOD_LABELS[pos.amortization_method] ?? pos.amortization_method}
                        </td>
                        <td className="px-4 py-3 text-center">
                          {(pos.red_flag_report?.total_flags_triggered ?? 0) > 0 ? (
                            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${
                              pos.red_flag_report?.max_severity === 'SEVERE' ? 'bg-red-100 text-red-700'
                              : pos.red_flag_report?.max_severity === 'HIGH' ? 'bg-orange-100 text-orange-700'
                              : 'bg-amber-100 text-amber-700'
                            }`}>
                              <AlertTriangle size={10} />
                              {pos.red_flag_report?.total_flags_triggered}
                            </span>
                          ) : (
                            <span className="text-green-500"><CheckCircle size={14} /></span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Card>

          {/* Position Detail Panel */}
          {selectedPosition && (
            <Card title={`Position #${selectedPosition.position_id} — ${selectedPosition.trade_id}`}>
              <div className="space-y-4">
                {/* Classification Banner */}
                {selectedPosition.classification === 'SUSPICIOUS' && (
                  <div className="flex items-start gap-3 p-4 rounded-lg bg-red-50 border border-red-200">
                    <AlertOctagon size={20} className="text-red-500 mt-0.5 flex-shrink-0" />
                    <div>
                      <h4 className="font-semibold text-red-800">Suspicious — Escalation Required</h4>
                      <p className="text-sm text-red-700 mt-1">{selectedPosition.classification_reason}</p>
                      {selectedPosition.red_flag_report?.flags.filter(f => f.triggered).map(flag => (
                        <div key={flag.flag_id} className={`mt-2 px-3 py-2 rounded border text-sm ${SEVERITY_COLORS[flag.severity]}`}>
                          <span className="font-medium">[{flag.severity}] {flag.flag_name}</span>
                          <span className="block text-xs mt-0.5">{flag.description}</span>
                          {flag.threshold && (
                            <span className="block text-xs mt-0.5">Threshold: {flag.threshold} | Actual: {flag.actual_value}</span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Summary Grid */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="p-3 rounded-lg bg-enterprise-50">
                    <div className="text-xs text-enterprise-500">Transaction Price</div>
                    <div className="font-mono font-medium text-enterprise-800">{formatCurrency(selectedPosition.transaction_price)}</div>
                  </div>
                  <div className="p-3 rounded-lg bg-enterprise-50">
                    <div className="text-xs text-enterprise-500">Fair Value</div>
                    <div className="font-mono font-medium text-enterprise-800">{formatCurrency(selectedPosition.fair_value)}</div>
                  </div>
                  <div className="p-3 rounded-lg bg-enterprise-50">
                    <div className="text-xs text-enterprise-500">Day 1 P&L</div>
                    <div className={`font-mono font-medium ${selectedPosition.day1_pnl > 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {formatCurrency(selectedPosition.day1_pnl)} ({Number(selectedPosition.day1_pnl_pct).toFixed(1)}%)
                    </div>
                  </div>
                  <div className="p-3 rounded-lg bg-enterprise-50">
                    <div className="text-xs text-enterprise-500">Reserve Balance</div>
                    <div className="font-mono font-medium text-purple-600">{formatCurrency(selectedPosition.reserve_balance)}</div>
                  </div>
                </div>

                {/* Amortization Chart for selected position */}
                {selectedPosition.amortization_schedule.length > 0 && (
                  <div>
                    <h4 className="text-sm font-semibold text-enterprise-700 mb-2">
                      Amortization Schedule — {METHOD_LABELS[selectedPosition.amortization_method]}
                    </h4>
                    <div className="h-48">
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={selectedPosition.amortization_schedule}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                          <XAxis dataKey="period_date" stroke="#64748b" tick={{ fontSize: 10 }} />
                          <YAxis stroke="#64748b" tick={{ fontSize: 10 }} tickFormatter={v => formatCurrency(v, true)} />
                          <Tooltip
                            contentStyle={{ backgroundColor: '#fff', border: '1px solid #e2e8f0', borderRadius: '8px' }}
                            formatter={(value: number) => formatCurrency(value)}
                          />
                          <Area type="monotone" dataKey="remaining_deferred" name="Remaining Reserve" fill="#c4b5fd" stroke="#8b5cf6" fillOpacity={0.3} />
                          <Area type="monotone" dataKey="cumulative_recognized" name="Cumulative Released" fill="#bbf7d0" stroke="#22c55e" fillOpacity={0.3} />
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                )}

                <button
                  onClick={() => setSelectedPosition(null)}
                  className="text-sm text-primary-600 hover:text-primary-800"
                >
                  Close detail
                </button>
              </div>
            </Card>
          )}
        </div>
      )}

      {/* ── Amortization Tab ────────────────────────────────────── */}
      {activeTab === 'amortization' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card title="Straight Line">
              <div className="p-3 space-y-2">
                <div className="text-sm text-enterprise-600">Equal monthly amounts over the life of the instrument.</div>
                <div className="text-xs text-enterprise-500 mt-2">
                  Using: {positions.filter(p => p.amortization_method === 'STRAIGHT_LINE' && p.deferred_amount !== 0).length} positions
                </div>
              </div>
            </Card>
            <Card title="FV Convergence">
              <div className="p-3 space-y-2">
                <div className="text-sm text-enterprise-600">Front-weighted — larger releases early as FV converges to transaction price.</div>
                <div className="text-xs text-enterprise-500 mt-2">
                  Using: {positions.filter(p => p.amortization_method === 'FV_CONVERGENCE' && p.deferred_amount !== 0).length} positions
                </div>
              </div>
            </Card>
            <Card title="Accelerated Release">
              <div className="p-3 space-y-2">
                <div className="text-sm text-enterprise-600">Declining balance — 50% of remaining each period, aggressive front-loading.</div>
                <div className="text-xs text-enterprise-500 mt-2">
                  Using: {positions.filter(p => p.amortization_method === 'ACCELERATED_RELEASE' && p.deferred_amount !== 0).length} positions
                </div>
              </div>
            </Card>
          </div>

          {/* Amortization comparison chart */}
          <Card title="Amortization Schedules — All Deferred Positions">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-enterprise-200 bg-enterprise-50">
                    <th className="px-4 py-3 text-left text-enterprise-700 font-semibold">Position</th>
                    <th className="px-4 py-3 text-left text-enterprise-700 font-semibold">Method</th>
                    <th className="px-4 py-3 text-right text-enterprise-700 font-semibold">Total Deferred</th>
                    <th className="px-4 py-3 text-right text-enterprise-700 font-semibold">Amortized</th>
                    <th className="px-4 py-3 text-right text-enterprise-700 font-semibold">Remaining</th>
                    <th className="px-4 py-3 text-center text-enterprise-700 font-semibold">Periods</th>
                    <th className="px-4 py-3 text-center text-enterprise-700 font-semibold">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.filter(p => Math.abs(p.deferred_amount) > 0).map(pos => {
                    const amortized = Math.abs(pos.deferred_amount) - pos.reserve_balance;
                    const pctComplete = Math.abs(pos.deferred_amount) > 0
                      ? (amortized / Math.abs(pos.deferred_amount)) * 100 : 0;
                    return (
                      <tr key={pos.position_id} className="border-b border-enterprise-100 hover:bg-enterprise-50">
                        <td className="px-4 py-3 font-mono text-enterprise-700">#{pos.position_id}</td>
                        <td className="px-4 py-3 text-enterprise-600">{METHOD_LABELS[pos.amortization_method]}</td>
                        <td className="px-4 py-3 text-right font-mono text-enterprise-700">
                          {formatCurrency(Math.abs(pos.deferred_amount))}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-green-600">
                          {formatCurrency(amortized)}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-purple-600">
                          {formatCurrency(pos.reserve_balance)}
                        </td>
                        <td className="px-4 py-3 text-center text-enterprise-600">
                          {pos.amortization_schedule.length}
                        </td>
                        <td className="px-4 py-3 text-center">
                          <div className="w-full bg-enterprise-100 rounded-full h-2">
                            <div
                              className="bg-green-500 h-2 rounded-full transition-all"
                              style={{ width: `${Math.min(pctComplete, 100)}%` }}
                            />
                          </div>
                          <span className="text-xs text-enterprise-500">{pctComplete.toFixed(0)}%</span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}

      {/* ── Accounting Tab ──────────────────────────────────────── */}
      {activeTab === 'accounting' && (
        <div className="space-y-6">
          <Card title="Accounting Journal Entries — Day 1 P&L Reserve">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-enterprise-200 bg-enterprise-50">
                    <th className="px-4 py-3 text-left text-enterprise-700 font-semibold">Date</th>
                    <th className="px-4 py-3 text-left text-enterprise-700 font-semibold">Position</th>
                    <th className="px-4 py-3 text-left text-enterprise-700 font-semibold">Type</th>
                    <th className="px-4 py-3 text-left text-enterprise-700 font-semibold">Description</th>
                    <th className="px-4 py-3 text-left text-enterprise-700 font-semibold">Debit</th>
                    <th className="px-4 py-3 text-left text-enterprise-700 font-semibold">Credit</th>
                    <th className="px-4 py-3 text-right text-enterprise-700 font-semibold">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {positions
                    .flatMap(p => p.accounting_entries)
                    .sort((a, b) => a.entry_date.localeCompare(b.entry_date))
                    .map((entry, idx) => {
                      const typeColor = entry.entry_type === 'RESERVE_CREATION'
                        ? 'bg-red-100 text-red-700'
                        : entry.entry_type === 'EXPIRY_RELEASE'
                        ? 'bg-blue-100 text-blue-700'
                        : 'bg-green-100 text-green-700';
                      return (
                        <tr key={`${entry.entry_id}-${idx}`} className="border-b border-enterprise-100 hover:bg-enterprise-50">
                          <td className="px-4 py-3 font-mono text-enterprise-600 text-xs">
                            <Calendar size={12} className="inline mr-1" />
                            {entry.entry_date}
                          </td>
                          <td className="px-4 py-3 font-mono text-enterprise-700">#{entry.position_id}</td>
                          <td className="px-4 py-3">
                            <span className={`px-2 py-0.5 rounded text-xs font-medium ${typeColor}`}>
                              {entry.entry_type.replace(/_/g, ' ')}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-enterprise-600 text-xs">{entry.description}</td>
                          <td className="px-4 py-3">
                            <span className="text-xs text-red-600 font-medium">
                              Dr {entry.debit_account}
                            </span>
                          </td>
                          <td className="px-4 py-3">
                            <span className="text-xs text-green-600 font-medium">
                              Cr {entry.credit_account}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-right font-mono font-medium text-enterprise-800">
                            {formatCurrency(entry.amount)}
                          </td>
                        </tr>
                      );
                    })}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}

      {/* ── Red Flags Tab ───────────────────────────────────────── */}
      {activeTab === 'redflags' && (
        <div className="space-y-6">
          {/* Suspicious positions with red flags */}
          {positions
            .filter(p => (p.red_flag_report?.total_flags_triggered ?? 0) > 0)
            .map(pos => (
              <Card
                key={pos.position_id}
                title={
                  <div className="flex items-center gap-3">
                    <span>Position #{pos.position_id} — {pos.trade_id}</span>
                    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium ${CLASS_CONFIG[pos.classification].badge}`}>
                      <AlertTriangle size={12} />
                      {pos.classification}
                    </span>
                  </div>
                }
              >
                <div className="space-y-3">
                  <div className="flex items-center gap-6 text-sm text-enterprise-600">
                    <span>Day 1 P&L: <span className="font-mono font-medium text-enterprise-800">{formatCurrency(pos.day1_pnl)}</span> ({Number(pos.day1_pnl_pct).toFixed(1)}%)</span>
                    <span>Reserve: <span className="font-mono font-medium text-purple-600">{formatCurrency(pos.reserve_balance)}</span></span>
                  </div>

                  {pos.red_flag_report?.requires_escalation && (
                    <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-red-100 border border-red-300 text-red-800 text-sm">
                      <AlertOctagon size={16} />
                      <span className="font-semibold">ESCALATION REQUIRED:</span>
                      <span>{pos.red_flag_report.escalation_reason}</span>
                    </div>
                  )}

                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    {pos.red_flag_report?.flags.filter(f => f.triggered).map(flag => (
                      <div key={flag.flag_id} className={`p-3 rounded-lg border ${SEVERITY_COLORS[flag.severity]}`}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-medium text-sm">{flag.flag_name}</span>
                          <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-white/50">{flag.severity}</span>
                        </div>
                        <p className="text-xs">{flag.description}</p>
                        {flag.threshold && (
                          <div className="mt-2 flex gap-4 text-xs">
                            <span>Threshold: {flag.threshold}</span>
                            <span>Actual: {flag.actual_value}</span>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </Card>
            ))}

          {/* Positions with no flags */}
          {positions.filter(p => (p.red_flag_report?.total_flags_triggered ?? 0) === 0).length > 0 && (
            <Card title="Clean Positions (No Red Flags)">
              <div className="flex flex-wrap gap-2">
                {positions.filter(p => (p.red_flag_report?.total_flags_triggered ?? 0) === 0).map(pos => (
                  <div key={pos.position_id} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-green-50 border border-green-200 text-sm">
                    <CheckCircle size={14} className="text-green-500" />
                    <span className="font-mono text-green-800">#{pos.position_id}</span>
                    <span className="text-green-600">— {pos.classification}</span>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
