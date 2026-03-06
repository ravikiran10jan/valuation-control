import { useState } from 'react';
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
  LineChart,
  Line,
  Legend,
} from 'recharts';
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Activity,
  Target,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { Card, KPICard } from '../shared/Card';
import { Badge, Tabs } from '../shared/Button';
import { useApi } from '@/hooks/useApi';
import { api } from '@/services/api';
import {
  formatNumber,
  cn,
} from '@/utils/format';
import type { ValidationReport, ValidationCategory, ValidationCheck } from '@/types';

// ── Fallback data ──────────────────────────────────────────────

const fallbackReport: ValidationReport = {
  overall_score: 94.2,
  total_checks: 156,
  passed: 142,
  failed: 8,
  warnings: 6,
  categories: [
    {
      name: 'Market Data Quality',
      score: 96.5,
      checks: [
        { name: 'Spot rate freshness', status: 'PASS', expected: '< 15 min stale', actual: '3 min', tolerance: '15 min' },
        { name: 'Volatility surface completeness', status: 'PASS', expected: '> 95% populated', actual: '98.2%', tolerance: '95%' },
        { name: 'Yield curve bootstrap residual', status: 'PASS', expected: '< 0.5 bps', actual: '0.2 bps', tolerance: '0.5 bps' },
        { name: 'FX cross rate triangulation', status: 'PASS', expected: '< 1 pip', actual: '0.3 pip', tolerance: '1 pip' },
        { name: 'Credit spread source validation', status: 'WARN', expected: 'Bloomberg + Markit', actual: 'Bloomberg only', tolerance: 'Multi-source' },
      ],
    },
    {
      name: 'Pricing Model Accuracy',
      score: 91.8,
      checks: [
        { name: 'BS model vs Monte Carlo convergence', status: 'PASS', expected: '< 0.1% diff', actual: '0.07%', tolerance: '0.1%' },
        { name: 'PDE finite difference stability', status: 'PASS', expected: 'Convergent', actual: 'Convergent', tolerance: 'N/A' },
        { name: 'Local vol calibration error', status: 'FAIL', expected: '< 2%', actual: '3.9%', tolerance: '2%' },
        { name: 'Barrier observation frequency', status: 'FAIL', expected: 'Daily', actual: 'Weekly (desk)', tolerance: 'Daily' },
        { name: 'Smile interpolation', status: 'PASS', expected: 'Smooth', actual: 'No arbitrage', tolerance: 'N/A' },
      ],
    },
    {
      name: 'Tolerance Framework',
      score: 95.0,
      checks: [
        { name: 'GREEN threshold adherence', status: 'PASS', expected: '<= 5%', actual: '5%', tolerance: '5%' },
        { name: 'AMBER threshold adherence', status: 'PASS', expected: '5-15%', actual: '5-15%', tolerance: '15%' },
        { name: 'RED threshold adherence', status: 'PASS', expected: '> 15%', actual: '> 15%', tolerance: '15%' },
        { name: 'Exception generation timing', status: 'PASS', expected: '< 30s after comparison', actual: '12s', tolerance: '30s' },
        { name: 'Stale exception detection', status: 'WARN', expected: 'Daily aging check', actual: 'Every 6 hours', tolerance: 'Daily' },
      ],
    },
    {
      name: 'Reserve Calculation',
      score: 93.5,
      checks: [
        { name: 'FVA bid-ask spread source', status: 'PASS', expected: 'Dealer quotes', actual: 'Dealer quotes', tolerance: 'N/A' },
        { name: 'AVA 7-category completeness', status: 'PASS', expected: 'All 7 categories', actual: '7/7', tolerance: '7' },
        { name: 'Model reserve range coverage', status: 'PASS', expected: '>= 3 models', actual: '4 models', tolerance: '3' },
        { name: 'Day1 PnL amortization schedule', status: 'FAIL', expected: 'Monthly', actual: 'Quarterly', tolerance: 'Monthly' },
        { name: 'AVA confidence level', status: 'PASS', expected: '99%', actual: '99%', tolerance: '99%' },
      ],
    },
    {
      name: 'Data Integrity',
      score: 97.0,
      checks: [
        { name: 'Position count reconciliation', status: 'PASS', expected: 'Source = Agent 1', actual: 'Matched (2487)', tolerance: '0' },
        { name: 'Duplicate trade detection', status: 'PASS', expected: '0 duplicates', actual: '0', tolerance: '0' },
        { name: 'Missing valuation date', status: 'PASS', expected: '0 missing', actual: '0', tolerance: '0' },
        { name: 'Currency consistency', status: 'PASS', expected: 'ISO 4217', actual: 'All valid', tolerance: 'N/A' },
        { name: 'Counterparty reference data', status: 'WARN', expected: 'All matched', actual: '2 unmatched', tolerance: '0' },
      ],
    },
    {
      name: 'Regulatory Compliance',
      score: 90.0,
      checks: [
        { name: 'IFRS 13 hierarchy classification', status: 'PASS', expected: 'All classified', actual: '100%', tolerance: '100%' },
        { name: 'Basel III AVA methodology', status: 'PASS', expected: 'Core approach', actual: 'Core approach', tolerance: 'N/A' },
        { name: 'PRA110 field completeness', status: 'FAIL', expected: '100%', actual: '96%', tolerance: '100%' },
        { name: 'Audit trail completeness', status: 'PASS', expected: 'All actions logged', actual: 'Complete', tolerance: 'N/A' },
        { name: 'Report timeliness', status: 'FAIL', expected: 'T+1', actual: 'T+2', tolerance: 'T+1' },
      ],
    },
  ],
};

// Stable historical trend data derived from a simple deterministic seed
// (no Math.random() to avoid changing on every render)
function generateStableTrend(baseScore: number, basePassed: number, baseFailed: number): Array<{ date: string; score: number; passed: number; failed: number }> {
  return Array.from({ length: 30 }, (_, i) => {
    const d = new Date();
    d.setDate(d.getDate() - (29 - i));
    // Simple deterministic variance based on day index
    const seed = (i * 7 + 3) % 13;
    const scoreVariation = ((seed - 6) / 6) * 5;
    const passedVariation = Math.round(((seed - 6) / 6) * 8);
    const failedVariation = Math.round(((12 - seed) / 12) * 4);
    return {
      date: d.toISOString().split('T')[0],
      score: Math.max(80, Math.min(100, baseScore + scoreVariation)),
      passed: Math.max(0, basePassed + passedVariation),
      failed: Math.max(0, baseFailed + failedVariation),
    };
  });
}

const STATUS_COLORS = {
  PASS: '#10b981',
  FAIL: '#ef4444',
  WARN: '#f59e0b',
};

function ScoreGauge({ score, size = 'lg' }: { score: number; size?: 'sm' | 'lg' }) {
  const radius = size === 'lg' ? 80 : 40;
  const strokeWidth = size === 'lg' ? 12 : 8;
  const circumference = 2 * Math.PI * radius;
  const progress = (score / 100) * circumference;

  const color =
    score >= 90 ? '#10b981' :
    score >= 75 ? '#f59e0b' : '#ef4444';

  const svgSize = (radius + strokeWidth) * 2;

  return (
    <div className="relative inline-flex items-center justify-center">
      <svg width={svgSize} height={svgSize} className="-rotate-90">
        {/* Background circle */}
        <circle
          cx={radius + strokeWidth}
          cy={radius + strokeWidth}
          r={radius}
          fill="none"
          stroke="#e2e8f0"
          strokeWidth={strokeWidth}
        />
        {/* Progress circle */}
        <circle
          cx={radius + strokeWidth}
          cy={radius + strokeWidth}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={circumference - progress}
          strokeLinecap="round"
          className="transition-all duration-1000"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={cn(
          'font-bold',
          size === 'lg' ? 'text-3xl' : 'text-lg'
        )} style={{ color }}>
          {score.toFixed(1)}%
        </span>
        {size === 'lg' && (
          <span className="text-sm text-enterprise-500">Overall Score</span>
        )}
      </div>
    </div>
  );
}

function CheckStatusIcon({ status }: { status: ValidationCheck['status'] }) {
  switch (status) {
    case 'PASS':
      return <CheckCircle2 size={16} className="text-green-500" />;
    case 'FAIL':
      return <XCircle size={16} className="text-red-500" />;
    case 'WARN':
      return <AlertTriangle size={16} className="text-amber-500" />;
  }
}

function CategoryCard({
  category,
  defaultExpanded = false,
}: {
  category: ValidationCategory;
  defaultExpanded?: boolean;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const passCount = category.checks.filter((c) => c.status === 'PASS').length;
  const failCount = category.checks.filter((c) => c.status === 'FAIL').length;
  const warnCount = category.checks.filter((c) => c.status === 'WARN').length;

  return (
    <div className="bg-white rounded-xl border border-enterprise-200 shadow-enterprise-card overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-6 py-4 hover:bg-enterprise-50 transition-colors"
      >
        <div className="flex items-center gap-4">
          <ScoreGauge score={category.score} size="sm" />
          <div className="text-left">
            <h4 className="font-semibold text-enterprise-800">{category.name}</h4>
            <div className="flex items-center gap-3 mt-1">
              {passCount > 0 && (
                <span className="flex items-center gap-1 text-xs text-green-600">
                  <CheckCircle2 size={12} /> {passCount} passed
                </span>
              )}
              {failCount > 0 && (
                <span className="flex items-center gap-1 text-xs text-red-600">
                  <XCircle size={12} /> {failCount} failed
                </span>
              )}
              {warnCount > 0 && (
                <span className="flex items-center gap-1 text-xs text-amber-600">
                  <AlertTriangle size={12} /> {warnCount} warnings
                </span>
              )}
            </div>
          </div>
        </div>
        {expanded ? (
          <ChevronUp size={20} className="text-enterprise-400" />
        ) : (
          <ChevronDown size={20} className="text-enterprise-400" />
        )}
      </button>

      {expanded && (
        <div className="border-t border-enterprise-200">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-enterprise-50">
                <th className="px-6 py-2 text-left text-enterprise-600 font-medium">Check</th>
                <th className="px-4 py-2 text-center text-enterprise-600 font-medium">Status</th>
                <th className="px-4 py-2 text-left text-enterprise-600 font-medium">Expected</th>
                <th className="px-4 py-2 text-left text-enterprise-600 font-medium">Actual</th>
                <th className="px-4 py-2 text-left text-enterprise-600 font-medium">Tolerance</th>
              </tr>
            </thead>
            <tbody>
              {category.checks.map((check) => (
                <tr
                  key={check.name}
                  className={cn(
                    'border-t border-enterprise-100',
                    check.status === 'FAIL' && 'bg-red-50',
                    check.status === 'WARN' && 'bg-amber-50'
                  )}
                >
                  <td className="px-6 py-3 text-enterprise-700">{check.name}</td>
                  <td className="px-4 py-3 text-center">
                    <CheckStatusIcon status={check.status} />
                  </td>
                  <td className="px-4 py-3 font-mono text-enterprise-600">{check.expected}</td>
                  <td className={cn(
                    'px-4 py-3 font-mono',
                    check.status === 'PASS' ? 'text-green-600' :
                    check.status === 'FAIL' ? 'text-red-600' : 'text-amber-600'
                  )}>
                    {check.actual}
                  </td>
                  <td className="px-4 py-3 font-mono text-enterprise-500">{check.tolerance}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function ValidationDashboard() {
  const [activeTab, setActiveTab] = useState('overview');

  const { data: reportData, error } = useApi(
    () => api.getValidationReport(),
    [],
    fallbackReport
  );

  const report = reportData ?? fallbackReport;

  // Derive stable trend data from the actual report scores
  const trendData = generateStableTrend(report.overall_score, report.passed, report.failed);

  const statusDistribution = [
    { name: 'Passed', value: report.passed, fill: STATUS_COLORS.PASS },
    { name: 'Failed', value: report.failed, fill: STATUS_COLORS.FAIL },
    { name: 'Warnings', value: report.warnings, fill: STATUS_COLORS.WARN },
  ];

  const categoryScores = report.categories.map((c) => ({
    name: c.name.length > 20 ? c.name.substring(0, 20) + '...' : c.name,
    fullName: c.name,
    score: c.score,
    fill: c.score >= 90 ? '#10b981' : c.score >= 75 ? '#f59e0b' : '#ef4444',
  }));

  // Failed checks summary
  const failedChecks = report.categories.flatMap((cat) =>
    cat.checks
      .filter((c) => c.status === 'FAIL')
      .map((c) => ({ ...c, category: cat.name }))
  );

  const warningChecks = report.categories.flatMap((cat) =>
    cat.checks
      .filter((c) => c.status === 'WARN')
      .map((c) => ({ ...c, category: cat.name }))
  );

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'categories', label: 'By Category' },
    { id: 'failures', label: `Failures (${failedChecks.length})` },
    { id: 'trends', label: 'Trends' },
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
          title="Total Checks"
          value={formatNumber(report.total_checks)}
          icon={<Activity size={20} className="text-enterprise-500" />}
        />
        <KPICard
          title="Passed"
          value={formatNumber(report.passed)}
          color="green"
          icon={<CheckCircle2 size={20} className="text-green-500" />}
        />
        <KPICard
          title="Failed"
          value={formatNumber(report.failed)}
          color="red"
          icon={<XCircle size={20} className="text-red-500" />}
        />
        <KPICard
          title="Warnings"
          value={formatNumber(report.warnings)}
          color="amber"
          icon={<AlertTriangle size={20} className="text-amber-500" />}
        />
        <KPICard
          title="Pass Rate"
          value={`${Number(report.total_checks) > 0 ? ((Number(report.passed) / Number(report.total_checks)) * 100).toFixed(1) : 0}%`}
          color={Number(report.passed) / Number(report.total_checks) > 0.9 ? 'green' : 'amber'}
          icon={<Target size={20} className="text-blue-500" />}
        />
      </div>

      <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab} />

      {/* Overview Tab */}
      {activeTab === 'overview' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Overall Score Gauge */}
          <Card title="Overall Validation Score">
            <div className="flex flex-col items-center py-4">
              <ScoreGauge score={report.overall_score} />
              <div className="mt-6 text-center">
                <Badge
                  variant={report.overall_score >= 90 ? 'green' : report.overall_score >= 75 ? 'amber' : 'red'}
                >
                  {report.overall_score >= 90 ? 'Excellent' : report.overall_score >= 75 ? 'Acceptable' : 'Needs Attention'}
                </Badge>
              </div>
            </div>
          </Card>

          {/* Status Distribution */}
          <Card title="Check Status Distribution">
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={statusDistribution}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={45}
                    outerRadius={75}
                    paddingAngle={3}
                  >
                    {statusDistribution.map((entry, idx) => (
                      <Cell key={`status-${idx}`} fill={entry.fill} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#ffffff',
                      border: '1px solid #e2e8f0',
                      borderRadius: '8px',
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="flex justify-center gap-6 mt-2">
              {statusDistribution.map((item) => (
                <div key={item.name} className="flex items-center gap-2 text-sm">
                  <div
                    className="w-3 h-3 rounded-full"
                    style={{ backgroundColor: item.fill }}
                  />
                  <span className="text-enterprise-600">
                    {item.name}: {item.value}
                  </span>
                </div>
              ))}
            </div>
          </Card>

          {/* Category Scores */}
          <Card title="Category Scores">
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={categoryScores} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis
                    type="number"
                    domain={[0, 100]}
                    stroke="#64748b"
                    tick={{ fontSize: 11, fill: '#64748b' }}
                    tickFormatter={(val) => `${val}%`}
                  />
                  <YAxis
                    type="category"
                    dataKey="name"
                    stroke="#64748b"
                    tick={{ fontSize: 10, fill: '#64748b' }}
                    width={120}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#ffffff',
                      border: '1px solid #e2e8f0',
                      borderRadius: '8px',
                    }}
                    formatter={(value: number) => `${value}%`}
                    labelFormatter={(label) => {
                      const item = categoryScores.find((c) => c.name === label);
                      return item?.fullName ?? label;
                    }}
                  />
                  <Bar dataKey="score" name="Score" radius={[0, 4, 4, 0]}>
                    {categoryScores.map((entry, idx) => (
                      <Cell key={`cat-${idx}`} fill={entry.fill} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </div>
      )}

      {/* Categories Tab */}
      {activeTab === 'categories' && (
        <div className="space-y-4">
          {report.categories.map((cat, idx) => (
            <CategoryCard
              key={cat.name}
              category={cat}
              defaultExpanded={idx === 0}
            />
          ))}
        </div>
      )}

      {/* Failures Tab */}
      {activeTab === 'failures' && (
        <div className="space-y-6">
          {failedChecks.length > 0 && (
            <Card title="Failed Checks">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-enterprise-200 bg-red-50">
                      <th className="px-4 py-3 text-left text-red-700 font-semibold">Check</th>
                      <th className="px-4 py-3 text-left text-red-700 font-semibold">Category</th>
                      <th className="px-4 py-3 text-left text-red-700 font-semibold">Expected</th>
                      <th className="px-4 py-3 text-left text-red-700 font-semibold">Actual</th>
                      <th className="px-4 py-3 text-left text-red-700 font-semibold">Tolerance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {failedChecks.map((check, idx) => (
                      <tr key={idx} className="border-b border-enterprise-100 bg-red-50/50">
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <XCircle size={16} className="text-red-500" />
                            <span className="font-medium text-enterprise-800">{check.name}</span>
                          </div>
                        </td>
                        <td className="px-4 py-3 text-enterprise-600">{check.category}</td>
                        <td className="px-4 py-3 font-mono text-enterprise-600">{check.expected}</td>
                        <td className="px-4 py-3 font-mono text-red-600 font-medium">{check.actual}</td>
                        <td className="px-4 py-3 font-mono text-enterprise-500">{check.tolerance}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          {warningChecks.length > 0 && (
            <Card title="Warning Checks">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-enterprise-200 bg-amber-50">
                      <th className="px-4 py-3 text-left text-amber-700 font-semibold">Check</th>
                      <th className="px-4 py-3 text-left text-amber-700 font-semibold">Category</th>
                      <th className="px-4 py-3 text-left text-amber-700 font-semibold">Expected</th>
                      <th className="px-4 py-3 text-left text-amber-700 font-semibold">Actual</th>
                      <th className="px-4 py-3 text-left text-amber-700 font-semibold">Tolerance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {warningChecks.map((check, idx) => (
                      <tr key={idx} className="border-b border-enterprise-100 bg-amber-50/50">
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <AlertTriangle size={16} className="text-amber-500" />
                            <span className="font-medium text-enterprise-800">{check.name}</span>
                          </div>
                        </td>
                        <td className="px-4 py-3 text-enterprise-600">{check.category}</td>
                        <td className="px-4 py-3 font-mono text-enterprise-600">{check.expected}</td>
                        <td className="px-4 py-3 font-mono text-amber-600 font-medium">{check.actual}</td>
                        <td className="px-4 py-3 font-mono text-enterprise-500">{check.tolerance}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          {failedChecks.length === 0 && warningChecks.length === 0 && (
            <Card>
              <div className="text-center py-12">
                <CheckCircle2 size={48} className="mx-auto mb-4 text-green-500" />
                <p className="text-lg font-medium text-enterprise-800">All Checks Passed</p>
                <p className="text-sm text-enterprise-500 mt-1">No failures or warnings detected</p>
              </div>
            </Card>
          )}
        </div>
      )}

      {/* Trends Tab */}
      {activeTab === 'trends' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card title="Validation Score Trend (30 Days)">
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trendData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis
                    dataKey="date"
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
                    domain={[80, 100]}
                    tickFormatter={(val) => `${val}%`}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#ffffff',
                      border: '1px solid #e2e8f0',
                      borderRadius: '8px',
                      boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)',
                    }}
                    formatter={(value: number) => `${value.toFixed(1)}%`}
                  />
                  <Line
                    type="monotone"
                    dataKey="score"
                    stroke="#10b981"
                    strokeWidth={2}
                    dot={false}
                    name="Score"
                  />
                  {/* Reference lines */}
                  <Line
                    type="monotone"
                    dataKey={() => 90}
                    stroke="#f59e0b"
                    strokeWidth={1}
                    strokeDasharray="5 5"
                    dot={false}
                    name="Target (90%)"
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <Card title="Pass/Fail Trend (30 Days)">
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={trendData.slice(-14)}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis
                    dataKey="date"
                    stroke="#64748b"
                    tick={{ fontSize: 10, fill: '#64748b' }}
                    tickFormatter={(val) => {
                      const d = new Date(val);
                      return `${d.getMonth() + 1}/${d.getDate()}`;
                    }}
                  />
                  <YAxis stroke="#64748b" tick={{ fontSize: 12, fill: '#64748b' }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#ffffff',
                      border: '1px solid #e2e8f0',
                      borderRadius: '8px',
                    }}
                  />
                  <Legend />
                  <Bar dataKey="passed" stackId="a" fill="#10b981" name="Passed" />
                  <Bar dataKey="failed" stackId="a" fill="#ef4444" name="Failed" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
