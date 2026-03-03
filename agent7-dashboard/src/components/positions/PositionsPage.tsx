import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Activity,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Download,
  TrendingUp,
} from 'lucide-react';
import { Card, KPICard } from '../shared/Card';
import { DataGrid } from '../shared/DataGrid';
import { Button, Badge } from '../shared/Button';
import { useApi } from '@/hooks/useApi';
import { api } from '@/services/api';
import { formatCurrency, formatNumber } from '@/utils/format';
import type { Position } from '@/types';

const fallbackPositions: Position[] = [
  { position_id: 1, trade_id: 'FX-20250101-001', product_type: 'FX Forward', asset_class: 'FX', currency_pair: 'EUR/USD', notional: 10000000, notional_usd: 10000000, currency: 'USD', trade_date: '2025-01-15', maturity_date: '2025-07-15', settlement_date: null, counterparty: 'Deutsche Bank', desk_mark: 1.0842, vc_fair_value: 1.0838, book_value_usd: 10842000, difference: -400, difference_pct: -0.04, exception_status: 'GREEN', fair_value_level: 'L1', pricing_source: 'Bloomberg', fva_usd: 1200, valuation_date: '2025-02-14', created_at: '2025-01-15T10:00:00Z', updated_at: '2025-02-14T06:13:00Z' },
  { position_id: 2, trade_id: 'IR-20250102-001', product_type: 'IRS', asset_class: 'Rates', currency_pair: 'USD/USD', notional: 50000000, notional_usd: 50000000, currency: 'USD', trade_date: '2025-01-10', maturity_date: '2030-01-10', settlement_date: null, counterparty: 'JP Morgan', desk_mark: 2150000, vc_fair_value: 2148000, book_value_usd: 2150000, difference: -2000, difference_pct: -0.09, exception_status: 'GREEN', fair_value_level: 'L2', pricing_source: 'MarkIT', fva_usd: 45000, valuation_date: '2025-02-14', created_at: '2025-01-10T09:00:00Z', updated_at: '2025-02-14T06:13:00Z' },
  { position_id: 3, trade_id: 'EQ-20250103-001', product_type: 'Equity Option', asset_class: 'Equity', currency_pair: 'AAPL', notional: 5000000, notional_usd: 5000000, currency: 'USD', trade_date: '2025-01-20', maturity_date: '2025-06-20', settlement_date: null, counterparty: 'Goldman Sachs', desk_mark: 325000, vc_fair_value: 318000, book_value_usd: 325000, difference: -7000, difference_pct: -2.15, exception_status: 'AMBER', fair_value_level: 'L2', pricing_source: 'Internal Model', fva_usd: 2800, valuation_date: '2025-02-14', created_at: '2025-01-20T14:00:00Z', updated_at: '2025-02-14T06:13:00Z' },
  { position_id: 4, trade_id: 'CR-20250104-001', product_type: 'CDS', asset_class: 'Credit', currency_pair: 'USD/USD', notional: 25000000, notional_usd: 25000000, currency: 'USD', trade_date: '2025-01-12', maturity_date: '2030-03-20', settlement_date: null, counterparty: 'Barclays', desk_mark: 185000, vc_fair_value: 172000, book_value_usd: 185000, difference: -13000, difference_pct: -7.03, exception_status: 'RED', fair_value_level: 'L3', pricing_source: 'Internal Model', fva_usd: 8500, valuation_date: '2025-02-14', created_at: '2025-01-12T11:00:00Z', updated_at: '2025-02-14T06:13:00Z' },
];

const statusBadge = (status: Position['exception_status']) => {
  switch (status) {
    case 'GREEN':
      return <Badge variant="green">GREEN</Badge>;
    case 'AMBER':
      return <Badge variant="amber">AMBER</Badge>;
    case 'RED':
      return <Badge variant="red">RED</Badge>;
    default:
      return <Badge>N/A</Badge>;
  }
};

export function PositionsPage() {
  const navigate = useNavigate();
  const [assetFilter, setAssetFilter] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('');

  const params: Record<string, string> = {};
  if (assetFilter) params.asset_class = assetFilter;
  if (statusFilter) params.exception_status = statusFilter;

  const { data: positions, error } = useApi(
    () => api.getPositions(Object.keys(params).length > 0 ? params : undefined),
    [assetFilter, statusFilter],
    fallbackPositions
  );

  const data = positions ?? fallbackPositions;

  const greenCount = data.filter((p) => p.exception_status === 'GREEN' || !p.exception_status).length;
  const amberCount = data.filter((p) => p.exception_status === 'AMBER').length;
  const redCount = data.filter((p) => p.exception_status === 'RED').length;
  const totalNotional = data.reduce((sum, p) => sum + (p.notional_usd || 0), 0);

  const assetClasses = [...new Set(data.map((p) => p.asset_class).filter(Boolean))].sort();

  const columns = [
    { key: 'position_id' as const, header: 'ID', sortable: true, className: 'font-mono text-xs w-16' },
    { key: 'trade_id' as const, header: 'Trade ID', sortable: true, className: 'font-mono text-xs' },
    { key: 'currency_pair' as const, header: 'Ccy Pair', sortable: true },
    { key: 'product_type' as const, header: 'Product', sortable: true },
    { key: 'asset_class' as const, header: 'Asset Class', sortable: true },
    {
      key: 'notional_usd' as const,
      header: 'Notional',
      sortable: true,
      className: 'text-right',
      render: (row: Position) => (
        <span className="font-mono">{formatCurrency(row.notional_usd, true)}</span>
      ),
    },
    {
      key: 'desk_mark' as const,
      header: 'Desk Mark',
      sortable: true,
      className: 'text-right',
      render: (row: Position) => (
        <span className="font-mono">{formatCurrency(row.desk_mark)}</span>
      ),
    },
    {
      key: 'vc_fair_value' as const,
      header: 'VC Fair Value',
      sortable: true,
      className: 'text-right',
      render: (row: Position) => (
        <span className="font-mono">{formatCurrency(row.vc_fair_value)}</span>
      ),
    },
    {
      key: 'difference' as const,
      header: 'Diff',
      sortable: true,
      className: 'text-right',
      render: (row: Position) => (
        <span className={`font-mono ${row.difference < 0 ? 'text-red-600' : 'text-green-600'}`}>
          {formatCurrency(row.difference)}
        </span>
      ),
    },
    {
      key: 'difference_pct' as const,
      header: 'Diff %',
      sortable: true,
      className: 'text-right',
      render: (row: Position) => (
        <span className={`font-mono ${Math.abs(row.difference_pct) > 2 ? 'text-red-600' : row.difference_pct < 0 ? 'text-amber-600' : 'text-green-600'}`}>
          {row.difference_pct.toFixed(2)}%
        </span>
      ),
    },
    {
      key: 'exception_status' as const,
      header: 'Status',
      sortable: true,
      render: (row: Position) => statusBadge(row.exception_status),
    },
    {
      key: 'fair_value_level' as const,
      header: 'FV Level',
      sortable: true,
      render: (row: Position) => (
        <Badge variant={row.fair_value_level === 'L3' ? 'red' : row.fair_value_level === 'L1' ? 'green' : 'blue'}>
          {row.fair_value_level ?? '—'}
        </Badge>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      {error && (
        <div className="px-4 py-2 rounded-lg bg-amber-50 text-amber-700 text-sm border border-amber-200">
          Using cached data — backend unavailable ({error})
        </div>
      )}

      {/* KPI Row */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <KPICard
          title="Total Positions"
          value={formatNumber(data.length)}
          icon={<Activity size={20} className="text-primary-500" />}
        />
        <KPICard
          title="Total Notional"
          value={formatCurrency(totalNotional, true)}
          icon={<TrendingUp size={20} className="text-blue-500" />}
        />
        <KPICard
          title="GREEN"
          value={formatNumber(greenCount)}
          color="green"
          icon={<CheckCircle2 size={20} className="text-green-500" />}
        />
        <KPICard
          title="AMBER"
          value={formatNumber(amberCount)}
          color="amber"
          icon={<AlertTriangle size={20} className="text-amber-500" />}
        />
        <KPICard
          title="RED"
          value={formatNumber(redCount)}
          color="red"
          icon={<XCircle size={20} className="text-red-500" />}
        />
        <KPICard
          title="Asset Classes"
          value={formatNumber(assetClasses.length)}
          icon={<Activity size={20} className="text-indigo-500" />}
        />
      </div>

      {/* Filters + Actions */}
      <Card>
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2">
            <label className="text-sm text-enterprise-600">Asset Class:</label>
            <select
              value={assetFilter}
              onChange={(e) => setAssetFilter(e.target.value)}
              className="px-3 py-2 bg-white border border-enterprise-300 rounded-lg text-sm text-enterprise-800 focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              <option value="">All</option>
              {assetClasses.map((ac) => (
                <option key={ac} value={ac}>{ac}</option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-sm text-enterprise-600">Status:</label>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="px-3 py-2 bg-white border border-enterprise-300 rounded-lg text-sm text-enterprise-800 focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              <option value="">All</option>
              <option value="GREEN">GREEN</option>
              <option value="AMBER">AMBER</option>
              <option value="RED">RED</option>
            </select>
          </div>
          <div className="flex-1" />
          <Button
            variant="secondary"
            icon={<Download size={16} />}
            onClick={() => api.exportToExcel('positions')}
          >
            Export
          </Button>
        </div>
      </Card>

      {/* Positions Grid */}
      <DataGrid<Position>
        data={data}
        columns={columns}
        keyField="position_id"
        searchable
        searchPlaceholder="Search by trade ID, currency pair, product, counterparty..."
        onRowClick={(row) => navigate(`/positions/${row.position_id}`)}
      />
    </div>
  );
}
