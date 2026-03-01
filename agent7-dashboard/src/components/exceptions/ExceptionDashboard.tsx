import { useState, useEffect, useCallback } from 'react';
import {
  AlertTriangle,
  FileWarning,
  Clock,
  CheckCircle2,
  Filter,
  RefreshCw,
  Users,
  X,
} from 'lucide-react';
import { Card, KPICard } from '../shared/Card';
import { DataGrid } from '../shared/DataGrid';
import { Button, Badge } from '../shared/Button';
import { ExceptionDetailModal } from './ExceptionDetailModal';
import { api } from '@/services/api';
import {
  formatCurrency,
  formatPercent,
  formatDate,
  cn,
} from '@/utils/format';
import type { Exception, ExceptionFilters, ExceptionSummary, BatchComparisonResult } from '@/types';

// Mock exception data for when backend is unavailable
const mockExceptions: (Exception & { product: string })[] = [
  {
    exception_id: 1,
    position_id: 4,
    product: 'USD/TRY Spot (EM)',
    difference: -2.67,
    difference_pct: -8.22,
    severity: 'RED',
    status: 'OPEN',
    created_date: '2025-02-14',
    assigned_to: 'Sarah Chen',
    days_open: 0,
    escalation_level: 1,
    resolution_notes: null,
    resolved_date: null,
    created_at: '2025-02-14T16:00:00Z',
    updated_at: '2025-02-14T16:00:00Z',
  },
  {
    exception_id: 2,
    position_id: 5,
    product: 'USD/BRL Spot (EM)',
    difference: -0.06,
    difference_pct: -1.17,
    severity: 'AMBER',
    status: 'OPEN',
    created_date: '2025-02-14',
    assigned_to: 'Michael Park',
    days_open: 0,
    escalation_level: 1,
    resolution_notes: null,
    resolved_date: null,
    created_at: '2025-02-14T16:00:00Z',
    updated_at: '2025-02-14T16:00:00Z',
  },
  {
    exception_id: 3,
    position_id: 7,
    product: 'EUR/USD Barrier (DNT)',
    difference: -119000,
    difference_pct: -28.0,
    severity: 'RED',
    status: 'INVESTIGATING',
    created_date: '2025-02-10',
    assigned_to: 'David Liu',
    days_open: 4,
    escalation_level: 2,
    resolution_notes: null,
    resolved_date: null,
    created_at: '2025-02-10T09:00:00Z',
    updated_at: '2025-02-14T17:00:00Z',
  },
  {
    exception_id: 4,
    position_id: 8,
    product: 'GBP/USD 1Y Forward',
    difference: 4500,
    difference_pct: 6.2,
    severity: 'AMBER',
    status: 'ESCALATED',
    created_date: '2025-02-08',
    assigned_to: 'Sarah Chen',
    days_open: 6,
    escalation_level: 2,
    resolution_notes: null,
    resolved_date: null,
    created_at: '2025-02-08T10:00:00Z',
    updated_at: '2025-02-14T17:00:00Z',
  },
  {
    exception_id: 5,
    position_id: 9,
    product: 'USD/JPY Spot',
    difference: -0.45,
    difference_pct: -3.1,
    severity: 'AMBER',
    status: 'RESOLVED',
    created_date: '2025-02-11',
    assigned_to: 'Michael Park',
    days_open: 2,
    escalation_level: 1,
    resolution_notes: 'Desk mark updated after market close correction.',
    resolved_date: '2025-02-13',
    created_at: '2025-02-11T09:00:00Z',
    updated_at: '2025-02-13T15:00:00Z',
  },
];

const mockSummary: ExceptionSummary = {
  total_exceptions: 4,
  red_count: 2,
  amber_count: 2,
  avg_days_to_resolve: 2.0,
};

const ANALYSTS = ['Sarah Chen', 'Michael Park', 'David Liu', 'James Wong', 'Lisa Martinez'];

export function ExceptionDashboard() {
  const [exceptions, setExceptions] = useState<(Exception & { product?: string })[]>(mockExceptions);
  const [summary, setSummary] = useState<ExceptionSummary>(mockSummary);
  const [loading, setLoading] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [filters, setFilters] = useState<ExceptionFilters>({});
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [detailModalId, setDetailModalId] = useState<number | null>(null);
  const [batchRunning, setBatchRunning] = useState(false);
  const [batchResult, setBatchResult] = useState<BatchComparisonResult | null>(null);
  const [bulkAssignOpen, setBulkAssignOpen] = useState(false);
  const [bulkAssignee, setBulkAssignee] = useState('');

  const fetchExceptions = useCallback(async () => {
    setLoading(true);
    try {
      const [excs, sum] = await Promise.all([
        api.getExceptions(filters),
        api.getExceptionSummary(),
      ]);
      setExceptions(excs);
      setSummary(sum);
    } catch {
      // Backend unavailable, keep mock data
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    fetchExceptions();
  }, [fetchExceptions]);

  const handleRunBatchComparison = async () => {
    setBatchRunning(true);
    setBatchResult(null);
    try {
      const result = await api.runBatchComparison(filters.asset_class || undefined);
      setBatchResult(result);
      // Refresh exceptions after comparison
      await fetchExceptions();
    } catch {
      // Backend unavailable
      setBatchResult({
        total_compared: 7,
        green: 4,
        amber: 1,
        red: 2,
        errors: [],
      });
    } finally {
      setBatchRunning(false);
    }
  };

  const handleCheckEscalations = async () => {
    try {
      await api.checkEscalations();
      await fetchExceptions();
    } catch {
      // Backend unavailable
    }
  };

  const handleBulkAssign = async () => {
    if (!bulkAssignee || selectedIds.size === 0) return;
    try {
      await Promise.all(
        Array.from(selectedIds).map((id) => api.assignException(id, bulkAssignee))
      );
      setSelectedIds(new Set());
      setBulkAssignOpen(false);
      setBulkAssignee('');
      await fetchExceptions();
    } catch {
      // Fallback: update local state
      setExceptions((prev) =>
        prev.map((e) =>
          selectedIds.has(e.exception_id)
            ? { ...e, assigned_to: bulkAssignee, status: e.status === 'OPEN' ? 'INVESTIGATING' : e.status }
            : e
        )
      );
      setSelectedIds(new Set());
      setBulkAssignOpen(false);
      setBulkAssignee('');
    }
  };

  const handleBulkResolve = async () => {
    if (selectedIds.size === 0) return;
    try {
      await Promise.all(
        Array.from(selectedIds).map((id) =>
          api.resolveException(id, 'Bulk resolved', 'System')
        )
      );
      setSelectedIds(new Set());
      await fetchExceptions();
    } catch {
      setExceptions((prev) =>
        prev.map((e) =>
          selectedIds.has(e.exception_id)
            ? { ...e, status: 'RESOLVED' as const, resolved_date: new Date().toISOString().split('T')[0] }
            : e
        )
      );
      setSelectedIds(new Set());
    }
  };

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === exceptions.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(exceptions.map((e) => e.exception_id)));
    }
  };

  const clearFilters = () => {
    setFilters({});
  };

  const activeFilterCount = Object.values(filters).filter((v) => v !== '' && v != null).length;

  const columns = [
    {
      key: 'select' as const,
      header: '',
      render: (row: (typeof exceptions)[0]) => (
        <input
          type="checkbox"
          checked={selectedIds.has(row.exception_id)}
          onChange={(e) => {
            e.stopPropagation();
            toggleSelect(row.exception_id);
          }}
          className="rounded border-enterprise-300 text-primary-600 focus:ring-primary-500"
        />
      ),
      className: 'w-10',
    },
    {
      key: 'exception_id' as const,
      header: 'ID',
      sortable: true,
      className: 'w-16',
    },
    {
      key: 'position_id' as const,
      header: 'Position',
      sortable: true,
      render: (row: (typeof exceptions)[0]) => (
        <span className="font-medium text-primary-600">
          #{row.position_id}
          {row.product && (
            <span className="ml-1 text-enterprise-500 font-normal">
              {row.product}
            </span>
          )}
        </span>
      ),
    },
    {
      key: 'difference' as const,
      header: 'Difference',
      sortable: true,
      render: (row: (typeof exceptions)[0]) => (
        <span className={cn('font-medium', row.difference < 0 ? 'text-red-600' : 'text-enterprise-700')}>
          {formatCurrency(row.difference)}
        </span>
      ),
    },
    {
      key: 'difference_pct' as const,
      header: 'Diff %',
      sortable: true,
      render: (row: (typeof exceptions)[0]) => (
        <span
          className={cn(
            'font-medium',
            row.severity === 'RED' ? 'text-red-600' : 'text-amber-600'
          )}
        >
          {formatPercent(row.difference_pct)}
        </span>
      ),
    },
    {
      key: 'severity' as const,
      header: 'Severity',
      render: (row: (typeof exceptions)[0]) => (
        <Badge variant={row.severity === 'RED' ? 'red' : 'amber'} size="sm">
          {row.severity}
        </Badge>
      ),
    },
    {
      key: 'status' as const,
      header: 'Status',
      render: (row: (typeof exceptions)[0]) => (
        <Badge
          variant={
            row.status === 'RESOLVED'
              ? 'green'
              : row.status === 'ESCALATED'
              ? 'red'
              : row.status === 'INVESTIGATING'
              ? 'blue'
              : 'amber'
          }
          size="sm"
        >
          {row.status}
        </Badge>
      ),
    },
    {
      key: 'days_open' as const,
      header: 'Days Open',
      sortable: true,
      render: (row: (typeof exceptions)[0]) => (
        <span
          className={cn(
            'font-medium',
            row.days_open > 5
              ? 'text-red-600'
              : row.days_open > 3
              ? 'text-amber-600'
              : 'text-enterprise-700'
          )}
        >
          {row.days_open}
        </span>
      ),
    },
    {
      key: 'escalation_level' as const,
      header: 'Level',
      render: (row: (typeof exceptions)[0]) => {
        const labels = ['', 'Analyst', 'Manager', 'Committee'];
        return (
          <span className="text-sm text-enterprise-600">
            {labels[row.escalation_level] || row.escalation_level}
          </span>
        );
      },
    },
    {
      key: 'assigned_to' as const,
      header: 'Assigned To',
      sortable: true,
      render: (row: (typeof exceptions)[0]) => (
        <span className="text-sm text-enterprise-600">
          {row.assigned_to || '—'}
        </span>
      ),
    },
    {
      key: 'created_date' as const,
      header: 'Created',
      sortable: true,
      render: (row: (typeof exceptions)[0]) => (
        <span className="text-sm text-enterprise-500">{formatDate(row.created_date)}</span>
      ),
    },
    {
      key: 'actions' as const,
      header: '',
      render: (row: (typeof exceptions)[0]) => (
        <Button
          variant="ghost"
          size="sm"
          onClick={(e) => {
            e.stopPropagation();
            setDetailModalId(row.exception_id);
          }}
        >
          Detail
        </Button>
      ),
      className: 'w-20',
    },
  ];

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPICard
          title="Total Open Exceptions"
          value={summary.total_exceptions}
          icon={<AlertTriangle size={20} className="text-amber-600" />}
          color="amber"
        />
        <KPICard
          title="RED Exceptions"
          value={summary.red_count}
          icon={<FileWarning size={20} className="text-red-600" />}
          color="red"
        />
        <KPICard
          title="AMBER Exceptions"
          value={summary.amber_count}
          icon={<AlertTriangle size={20} className="text-amber-600" />}
        />
        <KPICard
          title="Avg Days to Resolve"
          value={summary.avg_days_to_resolve.toFixed(1)}
          icon={<Clock size={20} className="text-primary-600" />}
        />
      </div>

      {/* Tolerance Breach Detection */}
      <Card title="Tolerance Breach Detection" headerAction={
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            icon={<RefreshCw size={14} className={batchRunning ? 'animate-spin' : ''} />}
            onClick={handleRunBatchComparison}
            disabled={batchRunning}
          >
            {batchRunning ? 'Running...' : 'Run VC vs Desk Comparison'}
          </Button>
          <Button
            variant="secondary"
            size="sm"
            icon={<Clock size={14} />}
            onClick={handleCheckEscalations}
          >
            Check Escalations
          </Button>
        </div>
      }>
        {batchResult && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <div className="text-center p-3 bg-enterprise-50 rounded-lg">
              <p className="text-2xl font-bold text-enterprise-800">{batchResult.total_compared}</p>
              <p className="text-xs text-enterprise-500">Total Compared</p>
            </div>
            <div className="text-center p-3 bg-green-50 rounded-lg border border-green-200">
              <p className="text-2xl font-bold text-green-700">{batchResult.green}</p>
              <p className="text-xs text-green-600">GREEN (Pass)</p>
            </div>
            <div className="text-center p-3 bg-amber-50 rounded-lg border border-amber-200">
              <p className="text-2xl font-bold text-amber-700">{batchResult.amber}</p>
              <p className="text-xs text-amber-600">AMBER (Warning)</p>
            </div>
            <div className="text-center p-3 bg-red-50 rounded-lg border border-red-200">
              <p className="text-2xl font-bold text-red-700">{batchResult.red}</p>
              <p className="text-xs text-red-600">RED (Breach)</p>
            </div>
            <div className="text-center p-3 bg-enterprise-50 rounded-lg">
              <p className="text-2xl font-bold text-enterprise-800">{batchResult.errors.length}</p>
              <p className="text-xs text-enterprise-500">Errors</p>
            </div>
          </div>
        )}
        {!batchResult && (
          <p className="text-sm text-enterprise-500">
            Run the comparison engine to detect tolerance breaches across all positions.
            This compares VC independent valuations against desk marks using Basel III / IFRS 13 thresholds
            (GREEN &lt;5%, AMBER 5-10%, RED &gt;10%).
          </p>
        )}
      </Card>

      {/* Filters & Bulk Actions */}
      <Card>
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-2">
            <Button
              variant={filtersOpen ? 'primary' : 'secondary'}
              size="sm"
              icon={<Filter size={14} />}
              onClick={() => setFiltersOpen(!filtersOpen)}
            >
              Filters{activeFilterCount > 0 && ` (${activeFilterCount})`}
            </Button>
            {activeFilterCount > 0 && (
              <Button variant="ghost" size="sm" onClick={clearFilters}>
                Clear
              </Button>
            )}
          </div>

          {selectedIds.size > 0 && (
            <div className="flex items-center gap-2">
              <span className="text-sm text-enterprise-500">
                {selectedIds.size} selected
              </span>
              <Button
                variant="secondary"
                size="sm"
                icon={<Users size={14} />}
                onClick={() => setBulkAssignOpen(true)}
              >
                Bulk Assign
              </Button>
              <Button
                variant="secondary"
                size="sm"
                icon={<CheckCircle2 size={14} />}
                onClick={handleBulkResolve}
              >
                Bulk Resolve
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setSelectedIds(new Set())}
              >
                Clear Selection
              </Button>
            </div>
          )}

          <Button
            variant="secondary"
            size="sm"
            icon={<RefreshCw size={14} className={loading ? 'animate-spin' : ''} />}
            onClick={fetchExceptions}
            disabled={loading}
          >
            Refresh
          </Button>
        </div>

        {/* Filter Panel */}
        {filtersOpen && (
          <div className="mt-4 pt-4 border-t border-enterprise-200 grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
            <div>
              <label className="block text-xs font-medium text-enterprise-600 mb-1">Severity</label>
              <select
                value={filters.severity || ''}
                onChange={(e) => setFilters((f) => ({ ...f, severity: e.target.value as ExceptionFilters['severity'] }))}
                className="w-full rounded-lg border border-enterprise-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
              >
                <option value="">All</option>
                <option value="RED">RED</option>
                <option value="AMBER">AMBER</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-enterprise-600 mb-1">Status</label>
              <select
                value={filters.status || ''}
                onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value as ExceptionFilters['status'] }))}
                className="w-full rounded-lg border border-enterprise-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
              >
                <option value="">All</option>
                <option value="OPEN">OPEN</option>
                <option value="INVESTIGATING">INVESTIGATING</option>
                <option value="ESCALATED">ESCALATED</option>
                <option value="RESOLVED">RESOLVED</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-enterprise-600 mb-1">Asset Class</label>
              <select
                value={filters.asset_class || ''}
                onChange={(e) => setFilters((f) => ({ ...f, asset_class: e.target.value }))}
                className="w-full rounded-lg border border-enterprise-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
              >
                <option value="">All</option>
                <option value="FX">FX</option>
                <option value="Rates">Rates</option>
                <option value="Credit">Credit</option>
                <option value="Equity">Equity</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-enterprise-600 mb-1">Assigned To</label>
              <select
                value={filters.assigned_to || ''}
                onChange={(e) => setFilters((f) => ({ ...f, assigned_to: e.target.value }))}
                className="w-full rounded-lg border border-enterprise-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
              >
                <option value="">All</option>
                {ANALYSTS.map((a) => (
                  <option key={a} value={a}>{a}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-enterprise-600 mb-1">From</label>
              <input
                type="date"
                value={filters.start_date || ''}
                onChange={(e) => setFilters((f) => ({ ...f, start_date: e.target.value }))}
                className="w-full rounded-lg border border-enterprise-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-enterprise-600 mb-1">To</label>
              <input
                type="date"
                value={filters.end_date || ''}
                onChange={(e) => setFilters((f) => ({ ...f, end_date: e.target.value }))}
                className="w-full rounded-lg border border-enterprise-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
          </div>
        )}
      </Card>

      {/* Exception DataGrid */}
      <Card
        title={`Exceptions (${exceptions.length})`}
        headerAction={
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={selectedIds.size === exceptions.length && exceptions.length > 0}
              onChange={toggleSelectAll}
              className="rounded border-enterprise-300 text-primary-600 focus:ring-primary-500"
            />
            <span className="text-xs text-enterprise-500">Select All</span>
          </div>
        }
      >
        <DataGrid
          data={exceptions}
          columns={columns}
          keyField="exception_id"
          onRowClick={(row) => setDetailModalId(row.exception_id)}
          searchable
          searchPlaceholder="Search exceptions by ID, product, status..."
        />
      </Card>

      {/* Bulk Assign Modal */}
      {bulkAssignOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-md">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-enterprise-800">
                Bulk Assign ({selectedIds.size} exceptions)
              </h3>
              <button onClick={() => setBulkAssignOpen(false)}>
                <X size={20} className="text-enterprise-400" />
              </button>
            </div>
            <div className="mb-4">
              <label className="block text-sm font-medium text-enterprise-600 mb-1">
                Assign to Analyst
              </label>
              <select
                value={bulkAssignee}
                onChange={(e) => setBulkAssignee(e.target.value)}
                className="w-full rounded-lg border border-enterprise-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
              >
                <option value="">Select analyst...</option>
                {ANALYSTS.map((a) => (
                  <option key={a} value={a}>{a}</option>
                ))}
              </select>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" size="sm" onClick={() => setBulkAssignOpen(false)}>
                Cancel
              </Button>
              <Button size="sm" onClick={handleBulkAssign} disabled={!bulkAssignee}>
                Assign
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Exception Detail Modal */}
      {detailModalId !== null && (
        <ExceptionDetailModal
          exceptionId={detailModalId}
          exceptions={exceptions}
          onClose={() => setDetailModalId(null)}
          onUpdate={fetchExceptions}
        />
      )}
    </div>
  );
}
