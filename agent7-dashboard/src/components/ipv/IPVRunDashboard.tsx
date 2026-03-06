import { useState } from 'react';
import {
  Play,
  RefreshCw,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  ChevronRight,
  Activity,
  TrendingUp,
  AlertTriangle,
  Shield,
} from 'lucide-react';
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
} from 'recharts';
import { Card, KPICard } from '../shared/Card';
import { Button, Badge } from '../shared/Button';
import { useApi } from '@/hooks/useApi';
import { api } from '@/services/api';
import {
  formatCurrency,
  formatNumber,
  formatDate,
  formatDateTime,
  cn,
} from '@/utils/format';
import type { IPVRun, IPVLatestResult, IPVStepResult } from '@/types';

// ── Fallback data ──────────────────────────────────────────────

const fallbackLatest: IPVLatestResult = {
  total_positions: 2487,
  total_notional_usd: 85000000000,
  total_book_value_usd: 12500000000,
  green_count: 2323,
  amber_count: 152,
  red_count: 12,
  total_fva: 45000000,
  total_ava: 125000000,
  total_model_reserve: 18500000,
  total_day1_deferred: 8200000,
  ava_breakdown: {
    market_price_uncertainty: 42500000,
    close_out_costs: 25000000,
    model_risk: 22500000,
    unearned_credit_spreads: 12500000,
    investment_funding: 10000000,
    concentrated_positions: 7500000,
    future_admin_costs: 5000000,
    total: 125000000,
  },
  ipv_runs: [
    {
      run_id: 'IPV-2025-0214-001',
      run_date: '2025-02-14',
      status: 'COMPLETED',
      total_positions: 2487,
      completed_steps: 8,
      total_steps: 8,
      step_results: [
        { step_number: 1, step_name: 'Load Positions', status: 'COMPLETED', started_at: '2025-02-14T06:00:00Z', completed_at: '2025-02-14T06:01:30Z', results_count: 2487, errors_count: 0 },
        { step_number: 2, step_name: 'Fetch Market Data', status: 'COMPLETED', started_at: '2025-02-14T06:01:30Z', completed_at: '2025-02-14T06:03:00Z', results_count: 2487, errors_count: 3 },
        { step_number: 3, step_name: 'Independent Pricing', status: 'COMPLETED', started_at: '2025-02-14T06:03:00Z', completed_at: '2025-02-14T06:08:00Z', results_count: 2487, errors_count: 0 },
        { step_number: 4, step_name: 'Tolerance Check', status: 'COMPLETED', started_at: '2025-02-14T06:08:00Z', completed_at: '2025-02-14T06:09:00Z', results_count: 2487, errors_count: 0 },
        { step_number: 5, step_name: 'Exception Generation', status: 'COMPLETED', started_at: '2025-02-14T06:09:00Z', completed_at: '2025-02-14T06:09:30Z', results_count: 164, errors_count: 0 },
        { step_number: 6, step_name: 'Reserve Calculation', status: 'COMPLETED', started_at: '2025-02-14T06:09:30Z', completed_at: '2025-02-14T06:12:00Z', results_count: 2487, errors_count: 0 },
        { step_number: 7, step_name: 'Hierarchy Classification', status: 'COMPLETED', started_at: '2025-02-14T06:12:00Z', completed_at: '2025-02-14T06:12:30Z', results_count: 2487, errors_count: 0 },
        { step_number: 8, step_name: 'Report Generation', status: 'COMPLETED', started_at: '2025-02-14T06:12:30Z', completed_at: '2025-02-14T06:13:00Z', results_count: 4, errors_count: 0 },
      ],
      summary: {
        total_notional_usd: 85000000000,
        total_book_value_usd: 12500000000,
        green_count: 2323,
        amber_count: 152,
        red_count: 12,
        total_fva: 45000000,
        total_ava: 125000000,
        total_model_reserve: 18500000,
        total_day1_deferred: 8200000,
      },
    },
    {
      run_id: 'IPV-2025-0213-001',
      run_date: '2025-02-13',
      status: 'COMPLETED',
      total_positions: 2481,
      completed_steps: 8,
      total_steps: 8,
      step_results: [],
      summary: {
        total_notional_usd: 84500000000,
        total_book_value_usd: 12400000000,
        green_count: 2318,
        amber_count: 148,
        red_count: 15,
        total_fva: 44200000,
        total_ava: 124000000,
        total_model_reserve: 18200000,
        total_day1_deferred: 8100000,
      },
    },
    {
      run_id: 'IPV-2025-0212-001',
      run_date: '2025-02-12',
      status: 'COMPLETED',
      total_positions: 2475,
      completed_steps: 8,
      total_steps: 8,
      step_results: [],
      summary: {
        total_notional_usd: 84000000000,
        total_book_value_usd: 12350000000,
        green_count: 2310,
        amber_count: 150,
        red_count: 15,
        total_fva: 43800000,
        total_ava: 123000000,
        total_model_reserve: 18000000,
        total_day1_deferred: 8000000,
      },
    },
  ],
  exception_summary: {
    total_exceptions: 164,
    red_count: 12,
    amber_count: 152,
    avg_days_to_resolve: 2.3,
  },
};

const RAG_COLORS = { green: '#10b981', amber: '#f59e0b', red: '#ef4444' };
const AVA_COLORS = ['#3b82f6', '#6366f1', '#8b5cf6', '#a78bfa', '#c4b5fd', '#ddd6fe', '#94a3b8'];
const AVA_LABELS: Record<string, string> = {
  market_price_uncertainty: 'Market Price Uncertainty',
  close_out_costs: 'Close-Out Costs',
  model_risk: 'Model Risk',
  unearned_credit_spreads: 'Unearned Credit Spreads',
  investment_funding: 'Investment & Funding',
  concentrated_positions: 'Concentrated Positions',
  future_admin_costs: 'Future Admin Costs',
};

function StepStatusIcon({ status }: { status: IPVStepResult['status'] }) {
  switch (status) {
    case 'COMPLETED':
      return <CheckCircle2 size={18} className="text-green-500" />;
    case 'RUNNING':
      return <Loader2 size={18} className="text-blue-500 animate-spin" />;
    case 'FAILED':
      return <XCircle size={18} className="text-red-500" />;
    case 'PENDING':
    default:
      return <Clock size={18} className="text-enterprise-400" />;
  }
}

function StepProgressTracker({ steps }: { steps: IPVStepResult[] }) {
  return (
    <div className="space-y-3">
      {steps.map((step, idx) => (
        <div key={step.step_number} className="relative">
          {idx < steps.length - 1 && (
            <div
              className={cn(
                'absolute left-[8px] top-8 w-0.5 h-full',
                step.status === 'COMPLETED' ? 'bg-green-300' : 'bg-enterprise-200'
              )}
            />
          )}
          <div className="flex items-start gap-3">
            <div className="flex-shrink-0 mt-0.5">
              <StepStatusIcon status={step.status} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-enterprise-400 font-mono">
                    Step {step.step_number}
                  </span>
                  <span className="font-medium text-sm text-enterprise-800">
                    {step.step_name}
                  </span>
                </div>
                <div className="flex items-center gap-3 text-xs text-enterprise-500">
                  {step.results_count !== undefined && (
                    <span>{formatNumber(step.results_count)} results</span>
                  )}
                  {(step.errors_count ?? 0) > 0 && (
                    <Badge variant="red" size="sm">
                      {step.errors_count} errors
                    </Badge>
                  )}
                  {step.status === 'COMPLETED' && (
                    <Badge variant="green" size="sm">Done</Badge>
                  )}
                  {step.status === 'RUNNING' && (
                    <Badge variant="blue" size="sm">Running</Badge>
                  )}
                </div>
              </div>
              {step.started_at && (
                <p className="text-xs text-enterprise-400 mt-0.5">
                  {formatDateTime(step.started_at)}
                  {step.completed_at && (
                    <>
                      {' '}&rarr; {formatDateTime(step.completed_at)}
                    </>
                  )}
                </p>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export function IPVRunDashboard() {
  const [triggerLoading, setTriggerLoading] = useState(false);
  const [triggerError, setTriggerError] = useState<string | null>(null);
  const [triggerSuccess, setTriggerSuccess] = useState(false);
  const [selectedRun, setSelectedRun] = useState<IPVRun | null>(null);

  const { data: latestData, error, refetch } = useApi(
    () => api.getIPVLatest(),
    [],
    fallbackLatest
  );

  const data = latestData ?? fallbackLatest;
  const currentRun = selectedRun ?? (data.ipv_runs.length > 0 ? data.ipv_runs[0] : null);

  const ragData = [
    { name: 'GREEN', value: data.green_count, fill: RAG_COLORS.green },
    { name: 'AMBER', value: data.amber_count, fill: RAG_COLORS.amber },
    { name: 'RED', value: data.red_count, fill: RAG_COLORS.red },
  ];

  const reserveData = [
    { name: 'FVA', value: data.total_fva },
    { name: 'AVA', value: data.total_ava },
    { name: 'Model Reserve', value: data.total_model_reserve },
    { name: 'Day1 Deferred', value: data.total_day1_deferred },
  ];

  const avaBreakdown = data.ava_breakdown;
  const avaData = avaBreakdown
    ? Object.entries(avaBreakdown)
        .filter(([key]) => key !== 'total')
        .map(([key, value]) => ({
          name: AVA_LABELS[key] || key,
          value: value as number,
          key,
        }))
    : [];

  const avaTotalFromBreakdown = avaBreakdown?.total ?? data.total_ava;

  const handleTriggerRun = async () => {
    setTriggerLoading(true);
    setTriggerError(null);
    setTriggerSuccess(false);
    try {
      await api.triggerIPVRun();
      setTriggerSuccess(true);
      refetch();
      setTimeout(() => setTriggerSuccess(false), 5000);
    } catch (e) {
      setTriggerError(e instanceof Error ? e.message : 'Failed to trigger IPV run');
    } finally {
      setTriggerLoading(false);
    }
  };

  const runStatusBadge = (status: IPVRun['status']) => {
    switch (status) {
      case 'COMPLETED':
        return <Badge variant="green">Completed</Badge>;
      case 'RUNNING':
        return <Badge variant="blue">Running</Badge>;
      case 'FAILED':
        return <Badge variant="red">Failed</Badge>;
      default:
        return <Badge>{status}</Badge>;
    }
  };

  return (
    <div className="space-y-6">
      {/* Error Banner */}
      {error && (
        <div className="px-4 py-2 rounded-lg bg-amber-50 text-amber-700 text-sm border border-amber-200">
          Using cached data -- backend unavailable ({error})
        </div>
      )}

      {/* Top Action Bar */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-enterprise-800">
            IPV Run Dashboard
          </h2>
          <p className="text-sm text-enterprise-500 mt-0.5">
            Independent Price Verification lifecycle management
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button variant="secondary" icon={<RefreshCw size={16} />} onClick={refetch}>
            Refresh
          </Button>
          <Button
            icon={triggerLoading ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
            onClick={handleTriggerRun}
            disabled={triggerLoading}
          >
            {triggerLoading ? 'Triggering...' : 'Trigger IPV Run'}
          </Button>
        </div>
      </div>

      {triggerError && (
        <div className="px-4 py-3 rounded-lg bg-red-50 text-red-700 text-sm border border-red-200 flex items-center justify-between">
          <span>{triggerError}</span>
          <button onClick={() => setTriggerError(null)} className="text-red-400 hover:text-red-600 ml-4">&times;</button>
        </div>
      )}
      {triggerSuccess && (
        <div className="px-4 py-3 rounded-lg bg-green-50 text-green-700 text-sm border border-green-200">
          IPV run triggered successfully. Results will appear below once complete.
        </div>
      )}

      {/* KPI Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8 gap-4">
        <KPICard
          title="Total Positions"
          value={formatNumber(data.total_positions)}
          icon={<Activity size={20} className="text-primary-500" />}
        />
        <KPICard
          title="Total Notional"
          value={formatCurrency(data.total_notional_usd, true)}
          icon={<TrendingUp size={20} className="text-blue-500" />}
        />
        <KPICard
          title="GREEN"
          value={formatNumber(data.green_count)}
          color="green"
          icon={<CheckCircle2 size={20} className="text-green-500" />}
        />
        <KPICard
          title="AMBER"
          value={formatNumber(data.amber_count)}
          color="amber"
          icon={<AlertTriangle size={20} className="text-amber-500" />}
        />
        <KPICard
          title="RED"
          value={formatNumber(data.red_count)}
          color="red"
          icon={<XCircle size={20} className="text-red-500" />}
        />
        <KPICard
          title="Total FVA"
          value={formatCurrency(data.total_fva, true)}
          icon={<Shield size={20} className="text-purple-500" />}
        />
        <KPICard
          title="Total AVA"
          value={formatCurrency(data.total_ava, true)}
          icon={<Shield size={20} className="text-blue-500" />}
        />
        <KPICard
          title="Model Reserve"
          value={formatCurrency(data.total_model_reserve, true)}
          icon={<Shield size={20} className="text-indigo-500" />}
        />
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Current Run Progress */}
        <div className="lg:col-span-2">
          <Card
            title={
              <div className="flex items-center gap-3">
                <span>
                  {currentRun ? `Run: ${currentRun.run_id}` : 'No IPV Runs'}
                </span>
                {currentRun && runStatusBadge(currentRun.status)}
              </div>
            }
            headerAction={
              currentRun && (
                <span className="text-sm text-enterprise-500">
                  {formatDate(currentRun.run_date)} &middot;{' '}
                  {formatNumber(currentRun.total_positions)} positions
                </span>
              )
            }
          >
            {currentRun && currentRun.step_results.length > 0 ? (
              <div className="space-y-6">
                {/* Progress Bar */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-enterprise-700">
                      Overall Progress
                    </span>
                    <span className="text-sm text-enterprise-500">
                      {currentRun.completed_steps} / {currentRun.total_steps} steps
                    </span>
                  </div>
                  <div className="h-3 bg-enterprise-100 rounded-full overflow-hidden">
                    <div
                      className={cn(
                        'h-full rounded-full transition-all duration-500',
                        currentRun.status === 'COMPLETED'
                          ? 'bg-green-500'
                          : currentRun.status === 'FAILED'
                          ? 'bg-red-500'
                          : 'bg-blue-500'
                      )}
                      style={{
                        width: `${(currentRun.completed_steps / currentRun.total_steps) * 100}%`,
                      }}
                    />
                  </div>
                </div>

                {/* Step-by-step tracker */}
                <StepProgressTracker steps={currentRun.step_results} />
              </div>
            ) : (
              <div className="text-center py-12 text-enterprise-500">
                <Clock size={48} className="mx-auto mb-4 text-enterprise-300" />
                <p className="text-lg font-medium">No detailed step data available</p>
                <p className="text-sm mt-1">Trigger a new IPV run to see step-by-step progress</p>
              </div>
            )}
          </Card>
        </div>

        {/* RAG Distribution */}
        <div className="space-y-6">
          <Card title="Position RAG Distribution">
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={ragData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={40}
                    outerRadius={70}
                    paddingAngle={2}
                  >
                    {ragData.map((entry, idx) => (
                      <Cell key={`rag-${idx}`} fill={entry.fill} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#ffffff',
                      border: '1px solid #e2e8f0',
                      borderRadius: '8px',
                      boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)',
                    }}
                    formatter={(value: number) => formatNumber(value)}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="flex justify-center gap-6 mt-2">
              {ragData.map((item) => (
                <div key={item.name} className="flex items-center gap-2 text-sm">
                  <div
                    className="w-3 h-3 rounded-full"
                    style={{ backgroundColor: item.fill }}
                  />
                  <span className="text-enterprise-600">
                    {item.name}: {formatNumber(item.value)}
                  </span>
                </div>
              ))}
            </div>
          </Card>

          <Card title="Reserve Breakdown">
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={reserveData} layout="vertical">
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
                    width={100}
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
                  <Bar dataKey="value" fill="#8b5cf6" name="Amount" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </div>
      </div>

      {/* AVA Breakdown */}
      {avaData.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <Card title="Additional Valuation Adjustments (AVA) — Basel III Art. 105">
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={avaData} layout="vertical" margin={{ left: 20, right: 20 }}>
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
                      width={160}
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
                    <Bar dataKey="value" name="AVA Amount" radius={[0, 4, 4, 0]}>
                      {avaData.map((_entry, idx) => (
                        <Cell key={`ava-${idx}`} fill={AVA_COLORS[idx % AVA_COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>
          </div>

          <Card title="AVA Category Detail">
            <div className="space-y-3">
              {avaData.map((item, idx) => {
                const pct = avaTotalFromBreakdown > 0
                  ? (item.value / avaTotalFromBreakdown) * 100
                  : 0;
                return (
                  <div key={item.key} className="space-y-1">
                    <div className="flex items-center justify-between text-sm">
                      <div className="flex items-center gap-2">
                        <div
                          className="w-2.5 h-2.5 rounded-full"
                          style={{ backgroundColor: AVA_COLORS[idx % AVA_COLORS.length] }}
                        />
                        <span className="text-enterprise-700">{item.name}</span>
                      </div>
                      <span className="font-mono text-enterprise-600 text-xs">
                        {formatCurrency(item.value, true)} ({Number(pct).toFixed(0)}%)
                      </span>
                    </div>
                    <div className="h-1.5 bg-enterprise-100 rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-500"
                        style={{
                          width: `${pct}%`,
                          backgroundColor: AVA_COLORS[idx % AVA_COLORS.length],
                        }}
                      />
                    </div>
                  </div>
                );
              })}
              <div className="pt-2 mt-2 border-t border-enterprise-200 flex items-center justify-between">
                <span className="text-sm font-semibold text-enterprise-800">Total AVA</span>
                <span className="font-mono font-semibold text-enterprise-800">
                  {formatCurrency(avaTotalFromBreakdown, true)}
                </span>
              </div>
            </div>
          </Card>
        </div>
      )}

      {/* Historical Runs */}
      <Card title="Historical IPV Runs">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-enterprise-200 bg-enterprise-50">
                <th className="px-4 py-3 text-left text-enterprise-700 font-semibold">Run ID</th>
                <th className="px-4 py-3 text-left text-enterprise-700 font-semibold">Date</th>
                <th className="px-4 py-3 text-left text-enterprise-700 font-semibold">Status</th>
                <th className="px-4 py-3 text-right text-enterprise-700 font-semibold">Positions</th>
                <th className="px-4 py-3 text-right text-enterprise-700 font-semibold">GREEN</th>
                <th className="px-4 py-3 text-right text-enterprise-700 font-semibold">AMBER</th>
                <th className="px-4 py-3 text-right text-enterprise-700 font-semibold">RED</th>
                <th className="px-4 py-3 text-right text-enterprise-700 font-semibold">Total Reserve</th>
                <th className="px-4 py-3 text-center text-enterprise-700 font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody>
              {(data.ipv_runs.length > 0 ? data.ipv_runs : []).map((run) => {
                const totalReserve =
                  (run.summary?.total_fva ?? 0) +
                  (run.summary?.total_ava ?? 0) +
                  (run.summary?.total_model_reserve ?? 0) +
                  (run.summary?.total_day1_deferred ?? 0);

                return (
                  <tr
                    key={run.run_id}
                    className={cn(
                      'border-b border-enterprise-100 hover:bg-enterprise-50 cursor-pointer transition-colors',
                      selectedRun?.run_id === run.run_id && 'bg-primary-50'
                    )}
                    onClick={() => setSelectedRun(run)}
                  >
                    <td className="px-4 py-3 font-mono text-enterprise-700">
                      {run.run_id}
                    </td>
                    <td className="px-4 py-3 text-enterprise-600">
                      {formatDate(run.run_date)}
                    </td>
                    <td className="px-4 py-3">{runStatusBadge(run.status)}</td>
                    <td className="px-4 py-3 text-right text-enterprise-700">
                      {formatNumber(run.total_positions)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className="text-green-600 font-medium">
                        {formatNumber(run.summary?.green_count ?? 0)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className="text-amber-600 font-medium">
                        {formatNumber(run.summary?.amber_count ?? 0)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className="text-red-600 font-medium">
                        {formatNumber(run.summary?.red_count ?? 0)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-enterprise-700">
                      {formatCurrency(totalReserve, true)}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <Button
                        variant="ghost"
                        size="sm"
                        icon={<ChevronRight size={14} />}
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedRun(run);
                        }}
                      >
                        View
                      </Button>
                    </td>
                  </tr>
                );
              })}
              {data.ipv_runs.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-4 py-12 text-center text-enterprise-500">
                    No IPV runs found. Click "Trigger IPV Run" to start one.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
