import { useState, useEffect, useCallback, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Play,
  FileText,
  AlertTriangle,
  Download,
  MessageSquare,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { DisputePanel } from '../disputes/DisputePanel';
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
  Legend,
} from 'recharts';
import { Card } from '../shared/Card';
import { Button, Badge, Tabs } from '../shared/Button';
import {
  formatCurrency,
  formatPercent,
  formatDate,
  formatDateTime,
  cn,
} from '@/utils/format';
import type { ValuationMethod, Greek, PnLAttribution, PositionHistory, PositionReserveResult, AVAComponentsDetail, AmortizationEntry, PositionDeepDiveData } from '@/types';
import { api } from '@/services/api';
import { useApi } from '@/hooks/useApi';

// FX position detail data from IPV_FX_Model — EUR/USD Barrier (DNT)
const fallbackPosition = {
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
  fair_value_level: 'L3',
  pricing_source: 'Internal BS Model',
  trader: 'FX Options Desk',
  desk: 'FX Exotic Options',
  desk_mark: 425000,
  vc_fair_value: 306000,
  book_value_usd: 850000,
  difference: 119000,
  difference_pct: -28,
  exception_status: 'RED' as const,
  valuation_date: '2025-02-14',
  last_valued: '2025-02-14T16:00:00Z',
  market_data: {
    spot: { value: 1.0823, source: 'WM/Reuters 4pm Fix' },
    lower_barrier: 1.05,
    upper_barrier: 1.12,
    volatility: { value: 6.8, source: 'Bloomberg OVML' },
    survival_probability: 0.72,
    time_to_expiry: 0.8767,
    domestic_rate: { value: 5.25, source: 'Fed Funds' },
    foreign_rate: { value: 4.25, source: 'ECB Depo' },
  },
  transaction_price: 425000,
};

const fallbackValuationMethods: ValuationMethod[] = [
  { method: 'Black-Scholes (Closed-Form)', value: 306000 },
  { method: 'Monte Carlo (50k paths, daily obs)', value: 306213, diff_pct: 0.07 },
  { method: 'PDE Finite Difference', value: 305800, diff_pct: -0.07 },
  { method: 'Local Vol (Dupire)', value: 318000, diff_pct: 3.9 },
  { method: 'Desk Mark (Client Quote)', value: 425000, diff_pct: 38.9 },
];

const fallbackGreeks: Greek[] = [
  { name: 'Delta', value: -15000, unit: 'USD per 1% spot move' },
  { name: 'Vega', value: -21000, unit: 'USD per 1% vol' },
  { name: 'Gamma', value: 450, unit: 'USD per (1% spot)^2' },
  { name: 'Theta', value: 120, unit: 'USD per day' },
];

const fallbackPnLAttribution: PnLAttribution[] = Array.from({ length: 30 }, (_, i) => {
  const date = new Date();
  date.setDate(date.getDate() - (29 - i));
  return {
    date: date.toISOString().split('T')[0],
    delta: (Math.random() - 0.5) * 20000,
    vega: (Math.random() - 0.5) * 15000,
    theta: Math.random() * 5000,
    unexplained: (Math.random() - 0.5) * 5000,
  };
});

const fallbackMCConvergence = Array.from({ length: 10 }, (_, i) => ({
  paths: (i + 1) * 5000,
  value: 306000 + (Math.random() - 0.5) * 2000 * (10 - i) / 10,
}));

const fallbackHistory: PositionHistory[] = [
  {
    id: '1',
    date: '2025-02-14T17:00:00Z',
    user: 'David Liu',
    action: 'Escalated to Manager',
    details: 'VC response: Term sheet specifies daily observation, not weekly. VC model uses daily obs which gives lower survival probability (72%). Breach stands.',
  },
  {
    id: '2',
    date: '2025-02-14T16:30:00Z',
    user: 'Desk Trader',
    action: 'Disputed VC valuation',
    details: 'Using weekly observation for barrier monitoring. Client quote of $420k supports desk mark. Vol surface from OVML is stale.',
  },
  {
    id: '3',
    date: '2025-02-14T16:00:00Z',
    user: 'system',
    action: 'RED exception created',
    details: 'Desk premium $425k vs VC model $306k (-28%). Level 3 position. Vol surface calibration uncertainty +/-5%.',
  },
  {
    id: '4',
    date: '2025-02-14T16:00:00Z',
    user: 'system',
    action: 'IPV completed',
    details: 'VC Fair Value: $306,000 (Black-Scholes closed-form). Spot=1.0823, Vol=6.8%, Barriers=[1.05, 1.12], T=0.8767Y',
  },
  {
    id: '5',
    date: '2025-01-05T10:00:00Z',
    user: 'system',
    action: 'Position created',
    details: 'Trade booked: EUR 50M EUR/USD Double-No-Touch Barrier, barriers [1.05, 1.12], expiry 31-Dec-2025',
  },
];

const fallbackDocuments = [
  { name: 'EUR_USD_DNT_Term_Sheet.pdf', uploaded: '2025-01-05' },
  { name: 'BS_Model_Output_14Feb2025.xlsx', uploaded: '2025-02-14' },
  { name: 'Desk_Trader_Justification.docx', uploaded: '2025-02-14' },
  { name: 'Dealer_Quotes_GS_JPM_Barclays.pdf', uploaded: '2025-02-14' },
  { name: 'Vol_Surface_Calibration_Report.xlsx', uploaded: '2025-02-14' },
];

// AVA category human-readable labels (Basel III Article 105)
const AVA_CATEGORY_LABELS: Record<keyof AVAComponentsDetail, string> = {
  mpu: 'Market Price Uncertainty',
  close_out: 'Close-Out Costs',
  model_risk: 'Model Risk',
  credit_spreads: 'Unearned Credit Spreads',
  funding: 'Investment & Funding Costs',
  concentration: 'Concentrated Positions',
  admin: 'Future Administrative Costs',
};

// Mock dispute data for the position
const fallbackDispute = {
  dispute_id: 1,
  exception_id: 101,
  position_id: 7,
  state: 'DESK_RESPONDED' as const,
  vc_position: 'Term sheet specifies daily observation, not weekly. VC model uses daily obs which gives lower survival probability (72%). The desk mark of $425k significantly overstates fair value.',
  desk_position: 'Using weekly observation for barrier monitoring per client agreement. Client quote of $420k supports desk mark. Vol surface from OVML is stale - should use dealer quotes.',
  vc_analyst: 'david.liu@bank.com',
  desk_trader: 'fx.trader@bank.com',
  desk_mark: 425000,
  vc_fair_value: 306000,
  difference: 119000,
  difference_pct: -28,
  resolution_type: null,
  final_mark: null,
  audit_trail: [
    {
      action: 'DESK_RESPONDED',
      actor: 'fx.trader@bank.com',
      detail: 'Desk provided response with proposed mark of $380,000',
      timestamp: '2025-02-14T17:00:00Z',
      from_state: 'DESK_REVIEWING',
    },
    {
      action: 'INITIATED',
      actor: 'david.liu@bank.com',
      detail: 'Dispute initiated for EUR/USD DNT Barrier valuation difference',
      timestamp: '2025-02-14T16:30:00Z',
      from_state: null,
    },
  ],
  created_date: '2025-02-14',
  resolved_date: null,
  created_at: '2025-02-14T16:30:00Z',
  updated_at: '2025-02-14T17:00:00Z',
};

// Current user context (would come from auth in real app)
const fallbackCurrentUser = {
  email: 'david.liu@bank.com',
  name: 'David Liu',
  role: 'VC' as const,
};

export function PositionDetail() {
  const { positionId } = useParams();
  const navigate = useNavigate();
  const positionIdNum = Number(positionId) || fallbackPosition.position_id;

  const [activeTab, setActiveTab] = useState('overview');
  const [reserveData, setReserveData] = useState<PositionReserveResult | null>(null);
  const [reserveLoading, setReserveLoading] = useState(false);
  const [avaExpanded, setAvaExpanded] = useState(false);
  const [amortExpanded, setAmortExpanded] = useState(false);

  // ── Fetch position deep-dive from all agents (1,2,4,5) ──
  const { data: deepDive, loading: positionLoading, error: positionError } = useApi<PositionDeepDiveData>(
    () => api.getIPVPositionDetail(positionIdNum),
    [positionIdNum]
  );

  // Merge API data with fallback
  const position = deepDive ?? fallbackPosition;
  const greeks: Greek[] = deepDive?.greeks?.greeks ?? fallbackGreeks;
  const activeDispute = useMemo(
    () => (deepDive?.disputes && deepDive.disputes.length > 0 ? deepDive.disputes[0] : fallbackDispute),
    [deepDive]
  );

  const loadReserves = useCallback(async () => {
    setReserveLoading(true);
    try {
      const classificationMap: Record<string, string> = { L1: 'Level1', L2: 'Level2', L3: 'Level3' };
      const fvl = (position as Record<string, unknown>).fair_value_level as string || 'L2';
      const result = await api.calculateAllReserves({
        position: {
          position_id: position.position_id,
          trade_id: position.trade_id,
          product_type: position.product_type,
          asset_class: position.asset_class,
          notional: position.notional ?? (position as Record<string, unknown>).notional_usd as number ?? 0,
          currency: position.currency,
          trade_date: position.trade_date,
          maturity_date: position.maturity_date,
          desk_mark: position.desk_mark,
          vc_fair_value: position.vc_fair_value,
          classification: classificationMap[fvl] ?? 'Level2',
          position_direction: 'LONG',
          transaction_price: (position as Record<string, unknown>).transaction_price as number ?? position.desk_mark,
        },
        model_results: [
          { model: 'Black-Scholes', value: 306000 },
          { model: 'Monte Carlo', value: 306213 },
          { model: 'PDE Finite Difference', value: 305800 },
          { model: 'Local Vol (Dupire)', value: 318000 },
        ],
      });
      setReserveData(result);
    } catch {
      // API unavailable — keep null (will show zeros)
    } finally {
      setReserveLoading(false);
    }
  }, [position]);

  useEffect(() => {
    loadReserves();
  }, [loadReserves]);

  // Derive reserve values from API result or fallback to zero
  const reserves = reserveData
    ? {
        fva: reserveData.fva.fva_amount,
        ava: reserveData.ava.total_ava,
        model_reserve: reserveData.model_reserve?.model_reserve ?? 0,
        day_1_pnl: reserveData.day1_pnl.deferred_amount,
      }
    : { fva: 0, ava: 0, model_reserve: 0, day_1_pnl: 0 };

  const avaComponents: AVAComponentsDetail | null = reserveData?.ava.components ?? null;
  const day1Status = reserveData?.day1_pnl.recognition_status ?? 'DEFERRED';
  const amortSchedule: AmortizationEntry[] = reserveData?.day1_pnl.amortization_schedule ?? [];

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'valuation', label: 'Valuation Methods' },
    { id: 'greeks', label: 'Greeks' },
    { id: 'sensitivity', label: 'Sensitivity' },
    { id: 'dispute', label: 'Dispute', icon: <MessageSquare size={14} /> },
    { id: 'history', label: 'History' },
    { id: 'documents', label: 'Documents' },
  ];

  return (
    <div className="space-y-6">
      {positionError && (
        <div className="px-4 py-2 rounded-lg bg-amber-50 text-amber-700 text-sm border border-amber-200">
          Using cached data — backend unavailable ({positionError})
        </div>
      )}

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
                {positionLoading ? 'Loading...' : `Position #${positionId} - ${position.product_type}`}
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
                {position.exception_status || 'GREEN'}
              </Badge>
            </div>
            <p className="text-sm text-enterprise-500 mt-1">
              Last valued: {formatDateTime((position as Record<string, unknown>).last_valued as string ?? (position as Record<string, unknown>).updated_at as string ?? position.valuation_date)}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <Button variant="secondary" icon={<Play size={16} />}>
            Run Valuation
          </Button>
          <Button variant="secondary" icon={<FileText size={16} />}>
            View Model Output
          </Button>
          <Button icon={<AlertTriangle size={16} />}>Create Exception</Button>
        </div>
      </div>

      {/* Tabs */}
      <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab} />

      {/* Tab Content */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Position Details */}
            <Card title="Position Details">
              <dl className="space-y-3">
                <div className="flex justify-between py-2 border-b border-enterprise-100">
                  <dt className="text-enterprise-500">Product</dt>
                  <dd className="font-medium text-enterprise-800">{position.product_type}</dd>
                </div>
                <div className="flex justify-between py-2 border-b border-enterprise-100">
                  <dt className="text-enterprise-500">Notional</dt>
                  <dd className="font-medium text-enterprise-800">{formatCurrency(position.notional)}</dd>
                </div>
                <div className="flex justify-between py-2 border-b border-enterprise-100">
                  <dt className="text-enterprise-500">Trade Date</dt>
                  <dd className="font-medium text-enterprise-800">{formatDate(position.trade_date)}</dd>
                </div>
                <div className="flex justify-between py-2 border-b border-enterprise-100">
                  <dt className="text-enterprise-500">Maturity</dt>
                  <dd className="font-medium text-enterprise-800">{formatDate(position.maturity_date)}</dd>
                </div>
                <div className="flex justify-between py-2">
                  <dt className="text-enterprise-500">Counterparty</dt>
                  <dd className="font-medium text-enterprise-800">{position.counterparty ?? ((position as Record<string, unknown>).trader as string ?? 'N/A')}</dd>
                </div>
              </dl>
            </Card>

            {/* Valuation */}
            <Card title="Valuation">
              <dl className="space-y-3">
                <div className="flex justify-between py-2 border-b border-enterprise-100">
                  <dt className="text-enterprise-500">Desk Mark</dt>
                  <dd className="font-medium text-enterprise-800">{formatCurrency(position.desk_mark)}</dd>
                </div>
                <div className="flex justify-between py-2 border-b border-enterprise-100">
                  <dt className="text-enterprise-500">VC Fair Value</dt>
                  <dd className="font-bold text-red-600">
                    {formatCurrency(position.vc_fair_value)}
                  </dd>
                </div>
                <div className="flex justify-between py-2 border-b border-enterprise-100">
                  <dt className="text-enterprise-500">Difference</dt>
                  <dd className="font-bold text-red-600">
                    {formatCurrency(position.difference)} ({formatPercent(position.difference_pct)})
                  </dd>
                </div>
                <div className="flex justify-between py-2">
                  <dt className="text-enterprise-500">Last Valued</dt>
                  <dd className="font-medium text-enterprise-800">{formatDateTime((position as Record<string, unknown>).last_valued as string ?? (position as Record<string, unknown>).updated_at as string ?? position.valuation_date)}</dd>
                </div>
              </dl>
            </Card>

            {/* Reserves — live from Agent 5 */}
            <Card title={reserveLoading ? 'Reserves (loading...)' : 'Reserves'}>
              <dl className="space-y-3">
                <div className="flex justify-between py-2 border-b border-enterprise-100">
                  <dt className="text-enterprise-500">FVA</dt>
                  <dd className="font-medium text-enterprise-800">{formatCurrency(reserves.fva)}</dd>
                </div>
                {reserveData?.fva.rationale && (
                  <p className="text-xs text-enterprise-400 -mt-2 pb-1">{reserveData.fva.rationale}</p>
                )}
                <div className="flex justify-between py-2 border-b border-enterprise-100">
                  <dt className="text-enterprise-500 flex items-center gap-1">
                    AVA (Total)
                    <button
                      className="ml-1 text-enterprise-400 hover:text-enterprise-600"
                      onClick={() => setAvaExpanded(!avaExpanded)}
                    >
                      {avaExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </button>
                  </dt>
                  <dd className="font-medium text-enterprise-800">{formatCurrency(reserves.ava)}</dd>
                </div>

                {/* 7-category AVA breakdown (CRD IV / Basel III Article 105) */}
                {avaExpanded && avaComponents && (
                  <div className="bg-enterprise-50 rounded-lg p-3 -mt-1 mb-1 space-y-2">
                    <p className="text-xs font-semibold text-enterprise-600 uppercase tracking-wide">
                      Basel III Article 105 — 7 AVA Categories
                    </p>
                    {(Object.keys(AVA_CATEGORY_LABELS) as Array<keyof AVAComponentsDetail>).map(
                      (key) => (
                        <div key={key} className="flex justify-between text-xs">
                          <span className="text-enterprise-500">{AVA_CATEGORY_LABELS[key]}</span>
                          <span className="font-mono text-enterprise-700">
                            {formatCurrency(avaComponents[key])}
                          </span>
                        </div>
                      )
                    )}
                  </div>
                )}

                <div className="flex justify-between py-2 border-b border-enterprise-100">
                  <dt className="text-enterprise-500">Model Reserve</dt>
                  <dd className="font-medium text-enterprise-800">{formatCurrency(reserves.model_reserve)}</dd>
                </div>
                {reserveData?.model_reserve && (
                  <p className="text-xs text-enterprise-400 -mt-2 pb-1">
                    Range: {formatCurrency(reserveData.model_reserve.model_range)} across{' '}
                    {reserveData.model_reserve.model_comparison.length} models
                  </p>
                )}

                <div className="flex justify-between py-2 border-b border-enterprise-100">
                  <dt className="text-enterprise-500 flex items-center gap-1">
                    Day 1 P&L
                    {amortSchedule.length > 0 && (
                      <button
                        className="ml-1 text-enterprise-400 hover:text-enterprise-600"
                        onClick={() => setAmortExpanded(!amortExpanded)}
                      >
                        {amortExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      </button>
                    )}
                  </dt>
                  <dd className="font-medium text-enterprise-500">
                    {formatCurrency(reserveData?.day1_pnl.day1_pnl ?? 0)}{' '}
                    <span className="text-xs">({day1Status.toLowerCase()})</span>
                  </dd>
                </div>

                {/* Amortization schedule for deferred Day 1 P&L */}
                {amortExpanded && amortSchedule.length > 0 && (
                  <div className="bg-enterprise-50 rounded-lg p-3 -mt-1 mb-1">
                    <p className="text-xs font-semibold text-enterprise-600 uppercase tracking-wide mb-2">
                      Amortization Schedule (IFRS 13 — Level 3 Deferred)
                    </p>
                    <div className="overflow-x-auto max-h-48 overflow-y-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="border-b border-enterprise-200">
                            <th className="py-1 text-left text-enterprise-500">Period</th>
                            <th className="py-1 text-right text-enterprise-500">Amount</th>
                            <th className="py-1 text-right text-enterprise-500">Cumulative</th>
                            <th className="py-1 text-right text-enterprise-500">Remaining</th>
                          </tr>
                        </thead>
                        <tbody>
                          {amortSchedule.map((entry) => (
                            <tr key={entry.period_date} className="border-b border-enterprise-100">
                              <td className="py-1 text-enterprise-600">{formatDate(entry.period_date)}</td>
                              <td className="py-1 text-right font-mono text-enterprise-700">
                                {formatCurrency(entry.amortization_amount)}
                              </td>
                              <td className="py-1 text-right font-mono text-enterprise-700">
                                {formatCurrency(entry.cumulative_recognized)}
                              </td>
                              <td className="py-1 text-right font-mono text-enterprise-700">
                                {formatCurrency(entry.remaining_deferred)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {reserveData && (
                  <div className="flex justify-between py-2 bg-enterprise-50 rounded-lg px-3 mt-2">
                    <dt className="font-semibold text-enterprise-700">Total Reserve</dt>
                    <dd className="font-bold text-enterprise-800">
                      {formatCurrency(reserveData.total_reserve)}
                    </dd>
                  </div>
                )}
              </dl>
            </Card>
          </div>

          {/* Market Data — shown when available (e.g. from fallback or enriched API response) */}
          {!!(position as Record<string, unknown>).market_data && (
            <Card title={`Market Data (as of ${formatDate(position.valuation_date)})`}>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-6">
                {(() => {
                  const md = (position as Record<string, unknown>).market_data as Record<string, unknown>;
                  const spot = md.spot as { value: number; source: string } | undefined;
                  const vol = md.volatility as { value: number; source: string } | undefined;
                  return (
                    <>
                      {spot && (
                        <div className="p-4 bg-enterprise-50 rounded-lg border border-enterprise-200">
                          <p className="text-sm text-enterprise-500 font-medium">{position.currency_pair ?? 'Spot'}</p>
                          <p className="text-xl font-bold mt-1 text-enterprise-800">{spot.value}</p>
                          <p className="text-xs text-enterprise-400">{spot.source}</p>
                        </div>
                      )}
                      {md.lower_barrier != null && (
                        <div className="p-4 bg-enterprise-50 rounded-lg border border-enterprise-200">
                          <p className="text-sm text-enterprise-500 font-medium">Lower Barrier</p>
                          <p className="text-xl font-bold mt-1 text-enterprise-800">{md.lower_barrier as number}</p>
                        </div>
                      )}
                      {md.upper_barrier != null && (
                        <div className="p-4 bg-enterprise-50 rounded-lg border border-enterprise-200">
                          <p className="text-sm text-enterprise-500 font-medium">Upper Barrier</p>
                          <p className="text-xl font-bold mt-1 text-enterprise-800">{md.upper_barrier as number}</p>
                        </div>
                      )}
                      {vol && (
                        <div className="p-4 bg-enterprise-50 rounded-lg border border-enterprise-200">
                          <p className="text-sm text-enterprise-500 font-medium">Volatility (1Y ATM)</p>
                          <p className="text-xl font-bold mt-1 text-enterprise-800">{vol.value}%</p>
                          <p className="text-xs text-enterprise-400">{vol.source}</p>
                        </div>
                      )}
                      {md.survival_probability != null && (
                        <div className="p-4 bg-enterprise-50 rounded-lg border border-enterprise-200">
                          <p className="text-sm text-enterprise-500 font-medium">Survival Probability</p>
                          <p className="text-xl font-bold mt-1 text-enterprise-800">
                            {((md.survival_probability as number) * 100).toFixed(0)}%
                          </p>
                          <p className="text-xs text-enterprise-400">Calculated</p>
                        </div>
                      )}
                    </>
                  );
                })()}
              </div>
            </Card>
          )}
        </div>
      )}

      {activeTab === 'valuation' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Valuation Methods Comparison */}
          <Card title="Valuation Method Comparison">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-enterprise-200 bg-enterprise-50">
                    <th className="px-4 py-3 text-left text-enterprise-700 font-semibold">Method</th>
                    <th className="px-4 py-3 text-right text-enterprise-700 font-semibold">Value</th>
                    <th className="px-4 py-3 text-right text-enterprise-700 font-semibold">Diff vs Primary</th>
                  </tr>
                </thead>
                <tbody>
                  {fallbackValuationMethods.map((method, idx) => (
                    <tr
                      key={method.method}
                      className={cn(
                        'border-b border-enterprise-100',
                        idx === 0 && 'bg-primary-50'
                      )}
                    >
                      <td className="px-4 py-3 text-enterprise-700">
                        {method.method}
                        {idx === 0 && (
                          <Badge variant="blue" size="sm" className="ml-2">
                            Primary
                          </Badge>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-enterprise-800">
                        {formatCurrency(method.value)}
                      </td>
                      <td
                        className={cn(
                          'px-4 py-3 text-right font-mono',
                          method.diff_pct && method.diff_pct > 0
                            ? 'text-green-600'
                            : method.diff_pct && method.diff_pct < 0
                            ? 'text-red-600'
                            : 'text-enterprise-500'
                        )}
                      >
                        {method.diff_pct !== undefined
                          ? formatPercent(method.diff_pct)
                          : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          {/* Monte Carlo Convergence */}
          <Card title="Model Convergence (Monte Carlo)">
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={fallbackMCConvergence}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis
                    dataKey="paths"
                    stroke="#64748b"
                    tick={{ fontSize: 12, fill: '#64748b' }}
                    tickFormatter={(val) => `${val / 1000}k`}
                    label={{
                      value: 'Number of Paths',
                      position: 'insideBottom',
                      offset: -5,
                      fill: '#64748b',
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
                  <Line
                    type="monotone"
                    dataKey="value"
                    stroke="#3b82f6"
                    strokeWidth={2}
                    dot={{ fill: '#3b82f6' }}
                    name="Fair Value"
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </div>
      )}

      {activeTab === 'greeks' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Greeks Table */}
          <Card title="Greeks">
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
                  {greeks.map((greek) => (
                    <tr key={greek.name} className="border-b border-enterprise-100">
                      <td className="px-4 py-3 font-medium text-enterprise-800">{greek.name}</td>
                      <td className="px-4 py-3 text-right font-mono text-enterprise-800">
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
          </Card>

          {/* P&L Attribution */}
          <Card title="P&L Attribution (Last 30 Days)">
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={fallbackPnLAttribution.slice(-14)}>
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
                  <Legend />
                  <Bar dataKey="delta" stackId="a" fill="#3b82f6" name="Delta" />
                  <Bar dataKey="vega" stackId="a" fill="#8b5cf6" name="Vega" />
                  <Bar dataKey="theta" stackId="a" fill="#10b981" name="Theta" />
                  <Bar dataKey="unexplained" stackId="a" fill="#94a3b8" name="Unexplained" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </div>
      )}

      {activeTab === 'sensitivity' && (
        <Card title="Sensitivity Analysis (P&L Impact)">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-enterprise-200 bg-enterprise-50">
                  <th className="px-4 py-3 text-left text-enterprise-700 font-semibold">Spot / Vol</th>
                  {[-2, -1, 0, 1, 2].map((vol) => (
                    <th key={vol} className="px-4 py-3 text-center text-enterprise-700 font-semibold">
                      {vol === 0 ? 'Base' : `${vol > 0 ? '+' : ''}${vol}% Vol`}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[-2, -1, 0, 1, 2].map((spot) => (
                  <tr key={spot} className="border-b border-enterprise-100">
                    <td className="px-4 py-3 font-medium text-enterprise-800">
                      {spot === 0 ? 'Base' : `${spot > 0 ? '+' : ''}${spot}% Spot`}
                    </td>
                    {[-2, -1, 0, 1, 2].map((vol) => {
                      const pnl = (spot * -15000 + vol * -21000);
                      return (
                        <td
                          key={`${spot}-${vol}`}
                          className={cn(
                            'px-4 py-3 text-center font-mono',
                            spot === 0 && vol === 0
                              ? 'bg-enterprise-100 font-bold text-enterprise-800'
                              : pnl > 0
                              ? 'text-green-600 bg-green-50'
                              : pnl < 0
                              ? 'text-red-600 bg-red-50'
                              : 'text-enterprise-700'
                          )}
                        >
                          {formatCurrency(pnl)}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {activeTab === 'dispute' && (
        <DisputePanel
          positionId={positionIdNum}
          exceptionId={activeDispute.exception_id ?? 0}
          dispute={activeDispute}
          deskMark={position.desk_mark}
          vcFairValue={position.vc_fair_value}
          currentUser={fallbackCurrentUser}
        />
      )}

      {activeTab === 'history' && (
        <Card title="Position History">
          <div className="space-y-4">
            {fallbackHistory.map((event, idx) => (
              <div key={event.id} className="relative">
                {idx < fallbackHistory.length - 1 && (
                  <div className="absolute left-[7px] top-8 w-0.5 h-full bg-enterprise-200" />
                )}
                <div className="flex items-start gap-4">
                  <div className="w-4 h-4 rounded-full bg-primary-500 mt-1 flex-shrink-0 ring-4 ring-primary-100" />
                  <div className="flex-1 min-w-0 pb-4">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-enterprise-800">{event.action}</span>
                      <span className="text-sm text-enterprise-500">
                        by {event.user}
                      </span>
                    </div>
                    <p className="text-sm text-enterprise-600 mt-1">{event.details}</p>
                    <p className="text-xs text-enterprise-400 mt-1">
                      {formatDateTime(event.date)}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {activeTab === 'documents' && (
        <Card title="Documents">
          <div className="space-y-2">
            {fallbackDocuments.map((doc) => (
              <div
                key={doc.name}
                className="flex items-center justify-between p-4 rounded-lg bg-enterprise-50 hover:bg-enterprise-100 cursor-pointer transition-colors border border-transparent hover:border-enterprise-200"
              >
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-white rounded-lg border border-enterprise-200">
                    <FileText size={20} className="text-enterprise-500" />
                  </div>
                  <div>
                    <p className="font-medium text-enterprise-800">{doc.name}</p>
                    <p className="text-sm text-enterprise-500">
                      Uploaded {formatDate(doc.uploaded)}
                    </p>
                  </div>
                </div>
                <Button variant="ghost" size="sm" icon={<Download size={16} />}>
                  Download
                </Button>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
