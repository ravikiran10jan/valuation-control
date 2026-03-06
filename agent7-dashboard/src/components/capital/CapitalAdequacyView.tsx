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
  Shield,
  AlertTriangle,
  CheckCircle2,
  Landmark,
  Scale,
} from 'lucide-react';
import { Card, KPICard } from '../shared/Card';
import { Badge } from '../shared/Button';
import { useApi } from '@/hooks/useApi';
import { api } from '@/services/api';
import {
  formatCurrency,
  cn,
} from '@/utils/format';
import type { CapitalAdequacy } from '@/types';

// ── Fallback data ──────────────────────────────────────────────

const fallbackCapital: CapitalAdequacy = {
  cet1_capital: 8500000000,
  total_rwa: 62000000000,
  cet1_ratio: 13.71,
  regulatory_minimum: 4.5,
  buffer_above_minimum: 9.21,
  ava_deduction: 125000000,
  components: {
    shareholders_equity: 6200000000,
    retained_earnings: 2800000000,
    aoci: -250000000,
    deductions: -250000000,
  },
  rwa_breakdown: {
    credit_risk: 38000000000,
    market_risk: 15000000000,
    operational_risk: 9000000000,
  },
};

const RWA_COLORS = ['#3b82f6', '#8b5cf6', '#f59e0b'];

// Capital ratio minimum thresholds (Basel III)
const RATIO_THRESHOLDS = [
  { label: 'CET1 Minimum', value: 4.5, color: '#ef4444' },
  { label: 'CET1 + Conservation Buffer', value: 7.0, color: '#f59e0b' },
  { label: 'CET1 + CCyB', value: 8.5, color: '#3b82f6' },
  { label: 'G-SIB Surcharge', value: 10.0, color: '#8b5cf6' },
];

export function CapitalAdequacyView() {
  const { data: capitalData, error } = useApi(
    () => api.getCapitalAdequacy(),
    [],
    fallbackCapital
  );

  const capital = capitalData ?? fallbackCapital;

  const cet1Components = [
    { name: "Shareholders' Equity", value: capital.components.shareholders_equity, fill: '#10b981' },
    { name: 'Retained Earnings', value: capital.components.retained_earnings, fill: '#3b82f6' },
    { name: 'AOCI', value: Math.abs(capital.components.aoci), fill: '#ef4444', negative: capital.components.aoci < 0 },
    { name: 'Deductions', value: Math.abs(capital.components.deductions), fill: '#64748b', negative: capital.components.deductions < 0 },
  ];

  const rwaComponents = [
    { name: 'Credit Risk', value: capital.rwa_breakdown.credit_risk, fill: RWA_COLORS[0] },
    { name: 'Market Risk', value: capital.rwa_breakdown.market_risk, fill: RWA_COLORS[1] },
    { name: 'Operational Risk', value: capital.rwa_breakdown.operational_risk, fill: RWA_COLORS[2] },
  ];

  // Gauge helper — ratio position on a 0-20% scale
  const maxRatio = 20;
  const ratioPosition = Math.min(capital.cet1_ratio / maxRatio * 100, 100);

  const isHealthy = capital.cet1_ratio >= 10;
  const isWarning = capital.cet1_ratio >= 7 && capital.cet1_ratio < 10;

  // AVA impact data
  const avaImpactPct = capital.total_rwa > 0
    ? (Number(capital.ava_deduction) / Number(capital.cet1_capital) * 100).toFixed(2)
    : '0';

  return (
    <div className="space-y-6">
      {error && (
        <div className="px-4 py-2 rounded-lg bg-amber-50 text-amber-700 text-sm border border-amber-200">
          Using cached data -- backend unavailable ({error})
        </div>
      )}

      {/* KPI Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard
          title="CET1 Capital"
          value={formatCurrency(capital.cet1_capital, true)}
          icon={<Landmark size={20} className="text-green-500" />}
        />
        <KPICard
          title="Total RWA"
          value={formatCurrency(capital.total_rwa, true)}
          icon={<Scale size={20} className="text-blue-500" />}
        />
        <KPICard
          title="CET1 Ratio"
          value={`${capital.cet1_ratio}%`}
          color={isHealthy ? 'green' : isWarning ? 'amber' : 'red'}
          icon={isHealthy ? <CheckCircle2 size={20} className="text-green-500" /> : <AlertTriangle size={20} className="text-amber-500" />}
        />
        <KPICard
          title="AVA Deduction"
          value={formatCurrency(capital.ava_deduction, true)}
          icon={<Shield size={20} className="text-purple-500" />}
        />
      </div>

      {/* Capital Ratio Gauge */}
      <Card title="Capital Ratio Analysis">
        <div className="space-y-8">
          {/* Visual Gauge */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-semibold text-enterprise-700">
                CET1 Ratio: {capital.cet1_ratio}%
              </h4>
              <Badge
                variant={isHealthy ? 'green' : isWarning ? 'amber' : 'red'}
              >
                {isHealthy ? 'Well Capitalized' : isWarning ? 'Adequately Capitalized' : 'Under Capitalized'}
              </Badge>
            </div>

            {/* Gauge Bar */}
            <div className="relative">
              <div className="h-8 bg-enterprise-100 rounded-full overflow-hidden relative">
                {/* Threshold markers */}
                {RATIO_THRESHOLDS.map((threshold) => (
                  <div
                    key={threshold.label}
                    className="absolute top-0 bottom-0 w-0.5"
                    style={{
                      left: `${(threshold.value / maxRatio) * 100}%`,
                      backgroundColor: threshold.color,
                    }}
                  />
                ))}
                {/* Current ratio fill */}
                <div
                  className={cn(
                    'h-full rounded-full transition-all duration-700',
                    isHealthy ? 'bg-green-500' : isWarning ? 'bg-amber-500' : 'bg-red-500'
                  )}
                  style={{ width: `${ratioPosition}%` }}
                />
              </div>

              {/* Threshold labels */}
              <div className="relative mt-2">
                {RATIO_THRESHOLDS.map((threshold) => (
                  <div
                    key={threshold.label}
                    className="absolute text-xs text-enterprise-500 -translate-x-1/2"
                    style={{ left: `${(threshold.value / maxRatio) * 100}%` }}
                  >
                    <div className="text-center">
                      <span className="font-mono" style={{ color: threshold.color }}>
                        {threshold.value}%
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Legend */}
            <div className="flex flex-wrap gap-4 mt-8 text-xs">
              {RATIO_THRESHOLDS.map((threshold) => (
                <div key={threshold.label} className="flex items-center gap-1.5">
                  <div
                    className="w-3 h-3 rounded-full"
                    style={{ backgroundColor: threshold.color }}
                  />
                  <span className="text-enterprise-600">{threshold.label} ({threshold.value}%)</span>
                </div>
              ))}
            </div>
          </div>

          {/* Buffer Analysis */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-4 border-t border-enterprise-200">
            <div className="p-4 bg-enterprise-50 rounded-lg border border-enterprise-200">
              <p className="text-sm text-enterprise-500">Buffer Above Minimum (4.5%)</p>
              <p className={cn(
                'text-2xl font-bold mt-1',
                capital.buffer_above_minimum > 5 ? 'text-green-600' :
                capital.buffer_above_minimum > 2 ? 'text-amber-600' : 'text-red-600'
              )}>
                +{capital.buffer_above_minimum}%
              </p>
              <p className="text-xs text-enterprise-400 mt-1">
                {formatCurrency(capital.cet1_capital - capital.total_rwa * 0.045, true)} excess capital
              </p>
            </div>
            <div className="p-4 bg-enterprise-50 rounded-lg border border-enterprise-200">
              <p className="text-sm text-enterprise-500">AVA Impact on CET1</p>
              <p className="text-2xl font-bold mt-1 text-purple-600">
                -{avaImpactPct}%
              </p>
              <p className="text-xs text-enterprise-400 mt-1">
                {formatCurrency(capital.ava_deduction, true)} deducted from CET1
              </p>
            </div>
            <div className="p-4 bg-enterprise-50 rounded-lg border border-enterprise-200">
              <p className="text-sm text-enterprise-500">CET1 Pre-AVA</p>
              <p className="text-2xl font-bold mt-1 text-enterprise-800">
                {capital.total_rwa > 0
                  ? ((Number(capital.cet1_capital) + Number(capital.ava_deduction)) / Number(capital.total_rwa) * 100).toFixed(2)
                  : '0.00'}%
              </p>
              <p className="text-xs text-enterprise-400 mt-1">
                Ratio before AVA deduction
              </p>
            </div>
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* CET1 Composition */}
        <Card title="CET1 Capital Composition">
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={cet1Components}
                layout="vertical"
              >
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
                  width={140}
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
                <Bar dataKey="value" name="Amount" radius={[0, 4, 4, 0]}>
                  {cet1Components.map((entry, idx) => (
                    <Cell key={`cet1-${idx}`} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-4 space-y-2 pt-4 border-t border-enterprise-200">
            {cet1Components.map((comp) => (
              <div key={comp.name} className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full" style={{ backgroundColor: comp.fill }} />
                  <span className="text-enterprise-600">{comp.name}</span>
                </div>
                <span className={cn(
                  'font-mono',
                  comp.negative ? 'text-red-600' : 'text-enterprise-800'
                )}>
                  {comp.negative ? '-' : ''}{formatCurrency(comp.value, true)}
                </span>
              </div>
            ))}
            <div className="flex items-center justify-between text-sm font-semibold pt-2 border-t border-enterprise-200">
              <span className="text-enterprise-700">Net CET1</span>
              <span className="font-mono text-enterprise-800">{formatCurrency(capital.cet1_capital, true)}</span>
            </div>
          </div>
        </Card>

        {/* RWA Breakdown */}
        <Card title="Risk-Weighted Assets Breakdown">
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={rwaComponents}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={90}
                  paddingAngle={2}
                  label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
                  labelLine={{ stroke: '#64748b' }}
                >
                  {rwaComponents.map((entry, idx) => (
                    <Cell key={`rwa-${idx}`} fill={entry.fill} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#ffffff',
                    border: '1px solid #e2e8f0',
                    borderRadius: '8px',
                  }}
                  formatter={(value: number) => formatCurrency(value, true)}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-4 space-y-2 pt-4 border-t border-enterprise-200">
            {rwaComponents.map((comp) => {
              const pct = capital.total_rwa > 0 ? (Number(comp.value) / Number(capital.total_rwa) * 100).toFixed(1) : '0';
              return (
                <div key={comp.name} className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full" style={{ backgroundColor: comp.fill }} />
                    <span className="text-enterprise-600">{comp.name}</span>
                  </div>
                  <div className="flex items-center gap-4">
                    <span className="font-mono text-enterprise-800">{formatCurrency(comp.value, true)}</span>
                    <span className="text-enterprise-500 w-12 text-right">{pct}%</span>
                  </div>
                </div>
              );
            })}
            <div className="flex items-center justify-between text-sm font-semibold pt-2 border-t border-enterprise-200">
              <span className="text-enterprise-700">Total RWA</span>
              <span className="font-mono text-enterprise-800">{formatCurrency(capital.total_rwa, true)}</span>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
