import { useState, useEffect, useCallback } from 'react';
import {
  Play,
  Upload,
  Calculator,
  FileDown,
  CheckCircle2,
  Loader2,
  Circle,
  RefreshCw,
  MessageSquare,
  AlertTriangle,
} from 'lucide-react';
import { Card } from '../shared/Card';
import { DataGrid } from '../shared/DataGrid';
import { Button, Badge } from '../shared/Button';
import { ExceptionDetailModal } from '../exceptions/ExceptionDetailModal';
import { api } from '@/services/api';
import {
  formatCurrency,
  formatPercent,
  cn,
} from '@/utils/format';
import type { Exception, ValuationRun, BatchComparisonResult } from '@/types';

// Fallback mock data used when backend is unavailable
const fallbackExceptions: (Exception & { product: string; trader: string })[] = [
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
    trader: 'EM Trading Desk',
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
    trader: 'EM Macro Fund D',
  },
  {
    exception_id: 3,
    position_id: 7,
    product: 'EUR/USD Barrier (DNT)',
    difference: 119000,
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
    trader: 'Structured Products Client F',
  },
];

const fallbackValuationRuns: ValuationRun[] = [
  {
    id: '1',
    name: 'FX market data refresh (WM/Reuters 4pm Fix)',
    status: 'completed',
    scheduled_time: '2025-02-14T16:00:00Z',
  },
  {
    id: '2',
    name: 'FX independent pricing (7 positions)',
    status: 'completed',
    scheduled_time: '2025-02-14T16:05:00Z',
    progress: 7,
    total: 7,
  },
  {
    id: '3',
    name: 'IPV tolerance check & breach analysis',
    status: 'completed',
    scheduled_time: '2025-02-14T16:10:00Z',
  },
  {
    id: '4',
    name: 'FVA / AVA reserve calculations',
    status: 'pending',
    scheduled_time: '2025-02-14T17:00:00Z',
  },
];

export function AnalystWorkbench() {
  const [exceptions, setExceptions] = useState<(Exception & { product?: string; trader?: string })[]>(fallbackExceptions);
  const [valuationRuns, setValuationRuns] = useState<ValuationRun[]>(fallbackValuationRuns);
  const [loading, setLoading] = useState(false);
  const [detailModalId, setDetailModalId] = useState<number | null>(null);
  const [runningComparison, setRunningComparison] = useState(false);
  const [comparisonResult, setComparisonResult] = useState<BatchComparisonResult | null>(null);

  const fetchExceptions = useCallback(async () => {
    setLoading(true);
    try {
      const excs = await api.getExceptions({ status: 'OPEN' });
      setExceptions(excs);
    } catch {
      // Backend unavailable, keep fallback data
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchExceptions();
    // Also try to fetch valuation runs
    api.getValuationRuns().then(setValuationRuns).catch(() => {});
  }, [fetchExceptions]);

  const handleRunValuation = async () => {
    setRunningComparison(true);
    setComparisonResult(null);

    // Update runs to show in_progress
    setValuationRuns((prev) =>
      prev.map((run) =>
        run.id === '3' ? { ...run, status: 'in_progress' as const } : run
      )
    );

    try {
      const result = await api.runBatchComparison();
      setComparisonResult(result);
      await fetchExceptions();
    } catch {
      // Simulate result
      setComparisonResult({
        total_compared: 7,
        green: 4,
        amber: 1,
        red: 2,
        errors: [],
      });
    } finally {
      setRunningComparison(false);
      setValuationRuns((prev) =>
        prev.map((run) =>
          run.id === '3' ? { ...run, status: 'completed' as const } : run
        )
      );
    }
  };

  const columns = [
    {
      key: 'position_id' as const,
      header: 'Position ID',
      sortable: true,
    },
    {
      key: 'product' as const,
      header: 'Product',
      sortable: true,
      render: (row: (typeof exceptions)[0]) => (
        <span>{row.product || `Position #${row.position_id}`}</span>
      ),
    },
    {
      key: 'difference' as const,
      header: 'Desk Mark',
      render: (row: (typeof exceptions)[0]) => {
        const deskMark = row.difference_pct !== 0
          ? row.difference / (row.difference_pct / 100)
          : 0;
        return formatCurrency(deskMark);
      },
      sortable: true,
    },
    {
      key: 'vc_fv' as const,
      header: 'VC FV',
      render: (row: (typeof exceptions)[0]) => {
        const deskMark = row.difference_pct !== 0
          ? row.difference / (row.difference_pct / 100)
          : 0;
        return formatCurrency(deskMark + row.difference);
      },
    },
    {
      key: 'difference_pct' as const,
      header: 'Diff %',
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
      sortable: true,
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
            row.days_open > 5 ? 'text-red-600' : row.days_open > 3 ? 'text-amber-600' : 'text-enterprise-700'
          )}
        >
          {row.days_open}
        </span>
      ),
    },
    {
      key: 'severity' as const,
      header: 'Priority',
      render: (row: (typeof exceptions)[0]) => (
        <Badge variant={row.severity === 'RED' ? 'red' : 'amber'} size="sm">
          {row.severity}
        </Badge>
      ),
    },
    {
      key: 'dispute_status' as const,
      header: 'Dispute',
      render: (row: (typeof exceptions)[0]) => {
        // Mock dispute status based on exception status
        const hasDispute = row.status === 'INVESTIGATING' || row.escalation_level > 1;
        if (hasDispute) {
          return (
            <Badge variant="blue" size="sm" className="flex items-center gap-1">
              <MessageSquare size={12} />
              Active
            </Badge>
          );
        }
        return <span className="text-enterprise-400 text-sm">-</span>;
      },
    },
    {
      key: 'actions' as const,
      header: 'Actions',
      render: (row: (typeof exceptions)[0]) => {
        const hasDispute = row.status === 'INVESTIGATING' || row.escalation_level > 1;
        return (
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                setDetailModalId(row.exception_id);
              }}
            >
              View
            </Button>
            {!hasDispute && row.severity === 'RED' && (
              <Button
                variant="ghost"
                size="sm"
                className="text-purple-600 hover:text-purple-700 hover:bg-purple-50"
                onClick={(e) => {
                  e.stopPropagation();
                  setDetailModalId(row.exception_id);
                  // In real app, this would open the dispute tab or modal
                }}
              >
                <AlertTriangle size={14} />
              </Button>
            )}
          </div>
        );
      },
    },
  ];

  const statusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="text-green-600" size={18} />;
      case 'in_progress':
        return <Loader2 className="text-primary-600 animate-spin" size={18} />;
      case 'pending':
        return <Circle className="text-enterprise-400" size={18} />;
      case 'failed':
        return <Circle className="text-red-600" size={18} />;
      default:
        return <Circle className="text-enterprise-400" size={18} />;
    }
  };

  return (
    <div className="space-y-6">
      {/* Quick Actions */}
      <Card title="Quick Actions">
        <div className="flex flex-wrap gap-3">
          <Button
            icon={<Play size={16} />}
            onClick={handleRunValuation}
            disabled={runningComparison}
          >
            {runningComparison ? 'Running...' : 'Run Valuation Now'}
          </Button>
          <Button variant="secondary" icon={<Upload size={16} />}>
            Upload Desk Marks
          </Button>
          <Button variant="secondary" icon={<Calculator size={16} />}>
            Recalculate Reserves
          </Button>
          <Button variant="secondary" icon={<FileDown size={16} />}>
            Export to Excel
          </Button>
          <Button variant="secondary" icon={<MessageSquare size={16} />}>
            View My Disputes
          </Button>
          <Button
            variant="secondary"
            icon={<RefreshCw size={14} className={loading ? 'animate-spin' : ''} />}
            onClick={fetchExceptions}
            disabled={loading}
          >
            Refresh
          </Button>
        </div>

        {/* Comparison Result Banner */}
        {comparisonResult && (
          <div className="mt-4 pt-4 border-t border-enterprise-200">
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <div className="text-center p-2 bg-enterprise-50 rounded-lg">
                <p className="text-xl font-bold text-enterprise-800">{comparisonResult.total_compared}</p>
                <p className="text-xs text-enterprise-500">Compared</p>
              </div>
              <div className="text-center p-2 bg-green-50 rounded-lg border border-green-200">
                <p className="text-xl font-bold text-green-700">{comparisonResult.green}</p>
                <p className="text-xs text-green-600">GREEN</p>
              </div>
              <div className="text-center p-2 bg-amber-50 rounded-lg border border-amber-200">
                <p className="text-xl font-bold text-amber-700">{comparisonResult.amber}</p>
                <p className="text-xs text-amber-600">AMBER</p>
              </div>
              <div className="text-center p-2 bg-red-50 rounded-lg border border-red-200">
                <p className="text-xl font-bold text-red-700">{comparisonResult.red}</p>
                <p className="text-xs text-red-600">RED</p>
              </div>
              <div className="text-center p-2 bg-enterprise-50 rounded-lg">
                <p className="text-xl font-bold text-enterprise-800">{comparisonResult.errors.length}</p>
                <p className="text-xs text-enterprise-500">Errors</p>
              </div>
            </div>
          </div>
        )}
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Today's Valuation Runs */}
        <Card title="Today's Valuation Runs" className="lg:col-span-1">
          <div className="space-y-4">
            {valuationRuns.map((run, index) => (
              <div key={run.id} className="relative">
                {/* Timeline connector */}
                {index < valuationRuns.length - 1 && (
                  <div
                    className={cn(
                      'absolute left-[9px] top-7 w-0.5 h-full',
                      run.status === 'completed' ? 'bg-green-400' : 'bg-enterprise-200'
                    )}
                  />
                )}

                <div className="flex items-start gap-3">
                  {statusIcon(run.status)}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-enterprise-500">
                        {new Date(run.scheduled_time).toLocaleTimeString('en-US', {
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </span>
                      <Badge
                        variant={
                          run.status === 'completed'
                            ? 'green'
                            : run.status === 'in_progress'
                            ? 'blue'
                            : 'default'
                        }
                        size="sm"
                      >
                        {run.status.replace('_', ' ')}
                      </Badge>
                    </div>
                    <p className="text-sm mt-1 text-enterprise-700">{run.name}</p>
                    {run.status === 'in_progress' && run.progress !== undefined && (
                      <div className="mt-2">
                        <div className="flex justify-between text-xs text-enterprise-500 mb-1">
                          <span>Progress</span>
                          <span>
                            {run.progress} / {run.total} ({Math.round((run.progress / run.total!) * 100)}%)
                          </span>
                        </div>
                        <div className="h-2 bg-enterprise-100 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-primary-600 transition-all duration-300 rounded-full"
                            style={{
                              width: `${(run.progress / run.total!) * 100}%`,
                            }}
                          />
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* My Exceptions */}
        <Card title="My Exceptions (Assigned to Me)" className="lg:col-span-2">
          <DataGrid
            data={exceptions}
            columns={columns}
            keyField="exception_id"
            onRowClick={(row) => setDetailModalId(row.exception_id)}
            searchable
            searchPlaceholder="Search exceptions..."
          />
        </Card>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <div className="bg-white rounded-xl p-5 border border-enterprise-200 shadow-enterprise-card">
          <p className="text-sm text-enterprise-500 font-medium">Total Assigned</p>
          <p className="text-2xl font-bold mt-1 text-enterprise-800">{exceptions.length}</p>
        </div>
        <div className="bg-red-50 rounded-xl p-5 border border-red-200 shadow-enterprise-card">
          <p className="text-sm text-red-600 font-medium">RED Priority</p>
          <p className="text-2xl font-bold mt-1 text-red-700">
            {exceptions.filter((e) => e.severity === 'RED').length}
          </p>
        </div>
        <div className="bg-amber-50 rounded-xl p-5 border border-amber-200 shadow-enterprise-card">
          <p className="text-sm text-amber-600 font-medium">AMBER Priority</p>
          <p className="text-2xl font-bold mt-1 text-amber-700">
            {exceptions.filter((e) => e.severity === 'AMBER').length}
          </p>
        </div>
        <div className="bg-purple-50 rounded-xl p-5 border border-purple-200 shadow-enterprise-card">
          <p className="text-sm text-purple-600 font-medium">Active Disputes</p>
          <p className="text-2xl font-bold mt-1 text-purple-700">
            {exceptions.filter((e) => e.status === 'INVESTIGATING' || e.escalation_level > 1).length}
          </p>
        </div>
        <div className="bg-white rounded-xl p-5 border border-enterprise-200 shadow-enterprise-card">
          <p className="text-sm text-enterprise-500 font-medium">Avg Days Open</p>
          <p className="text-2xl font-bold mt-1 text-enterprise-800">
            {exceptions.length > 0
              ? (exceptions.reduce((sum, e) => sum + Number(e.days_open), 0) / exceptions.length).toFixed(1)
              : '0'}
          </p>
        </div>
      </div>

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
