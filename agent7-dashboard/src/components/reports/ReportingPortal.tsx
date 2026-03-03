import { useState } from 'react';
import {
  FileSpreadsheet,
  FileText,
  Presentation,
  Code,
  Download,
  Clock,
  Plus,
  CheckCircle,
  AlertCircle,
  History,
} from 'lucide-react';
import { Card } from '../shared/Card';
import { Button, Badge } from '../shared/Button';
import { formatDateTime, cn } from '@/utils/format';
import type { Report, Pillar3Report, IFRS13Report, PRA110Report, FRY14QReport, AuditEvent } from '@/types';
import { api } from '@/services/api';

const mockReports: Report[] = [
  {
    id: 'daily_fx_valuation',
    title: 'Daily FX Valuation Report',
    description: 'All 7 FX positions with desk mark vs VC fair value, tolerance breaches',
    frequency: 'Daily',
    last_run: '2025-02-14T17:00:00Z',
    format: 'Excel',
  },
  {
    id: 'exception_summary',
    title: 'FX Exception Summary',
    description: 'USD/TRY RED, USD/BRL AMBER, EUR/USD Barrier RED — aging and escalation',
    frequency: 'Daily',
    last_run: '2025-02-14T17:00:00Z',
    format: 'PowerPoint',
  },
  {
    id: 'reserve_summary',
    title: 'FVA/AVA Reserve Summary',
    description: 'Funding valuation adjustments and additional valuation adjustments by position',
    frequency: 'Monthly',
    last_run: '2025-02-01T08:00:00Z',
    format: 'PDF',
  },
  {
    id: 'pillar3',
    title: 'Pillar 3 / CRD IV Disclosure',
    description: 'Basel III prudent valuation (AVA) regulatory disclosure — Table 3.2',
    frequency: 'Quarterly',
    last_run: '2025-01-15T07:00:00Z',
    format: 'PDF',
  },
  {
    id: 'ifrs13',
    title: 'IFRS 13 Fair Value Hierarchy',
    description: 'Fair value levels (L1/L2/L3), Level 3 reconciliation, valuation techniques',
    frequency: 'Quarterly',
    last_run: '2025-01-15T07:00:00Z',
    format: 'PDF',
  },
  {
    id: 'pra110',
    title: 'PRA110 Return (UK)',
    description: 'UK Prudential Regulation Authority return — Section D (Prudent Valuation)',
    frequency: 'Quarterly',
    last_run: '2025-01-15T07:00:00Z',
    format: 'XML',
  },
  {
    id: 'fry14q',
    title: 'FR Y-14Q (US Fed)',
    description: 'Federal Reserve Schedule H.1 — Trading Risk, VaR, fair value hierarchy',
    frequency: 'Quarterly',
    last_run: '2025-01-15T07:00:00Z',
    format: 'CSV',
  },
];

const formatIcons: Record<string, React.ReactNode> = {
  Excel: <FileSpreadsheet size={20} className="text-green-600" />,
  PDF: <FileText size={20} className="text-red-600" />,
  PowerPoint: <Presentation size={20} className="text-orange-600" />,
  XML: <Code size={20} className="text-blue-600" />,
  CSV: <FileSpreadsheet size={20} className="text-enterprise-500" />,
};

const assetClasses = ['FX G10 Spot', 'FX EM Spot', 'FX Forward', 'FX Option'];
const reportTypes = ['Position List', 'Exception Analysis', 'P&L Attribution', 'Tolerance Breach Report'];
const formats = ['Excel', 'PDF', 'CSV'];
const columns = [
  'Position ID',
  'Trade ID',
  'Currency Pair',
  'Product Type',
  'Notional (USD)',
  'Desk Mark',
  'VC Fair Value',
  'Difference',
  'Diff %',
  'Exception Status',
  'Fair Value Level',
  'Pricing Source',
  'FVA (USD)',
  'Counterparty',
  'Valuation Date',
];

export function ReportingPortal() {
  const [selectedReportType, setSelectedReportType] = useState(reportTypes[0]);
  const [selectedFormat, setSelectedFormat] = useState(formats[0]);
  const [selectedAssetClasses, setSelectedAssetClasses] = useState<string[]>([]);
  const [selectedColumns, setSelectedColumns] = useState<string[]>(columns.slice(0, 5));
  const [dateRange, setDateRange] = useState({ start: '', end: '' });
  const [generating, setGenerating] = useState<string | null>(null);
  const [generatedReports, setGeneratedReports] = useState<{
    pillar3?: Pillar3Report;
    ifrs13?: IFRS13Report;
    pra110?: PRA110Report;
    fry14q?: FRY14QReport;
  }>({});
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'catalog' | 'audit'>('catalog');
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [auditLoading, setAuditLoading] = useState(false);

  const getReportingDate = () => {
    // Default to end of last quarter
    const today = new Date();
    const quarter = Math.floor(today.getMonth() / 3);
    const quarterEnd = new Date(today.getFullYear(), quarter * 3, 0);
    return quarterEnd.toISOString().split('T')[0];
  };

  const handleGenerateReport = async (reportId: string) => {
    setGenerating(reportId);
    setError(null);
    const reportingDate = getReportingDate();

    const reportMeta = mockReports.find((r) => r.id === reportId);
    const trackDownload = (name: string) => {
      setRecentDownloads((prev) => [
        { name, generated: new Date().toISOString(), size: 'Generated' },
        ...prev.slice(0, 19),
      ]);
    };

    try {
      switch (reportId) {
        case 'pillar3': {
          const report = await api.generatePillar3(reportingDate);
          setGeneratedReports((prev) => ({ ...prev, pillar3: report }));
          trackDownload(`Pillar3_${reportingDate}.pdf`);
          break;
        }
        case 'ifrs13': {
          const report = await api.generateIFRS13(reportingDate);
          setGeneratedReports((prev) => ({ ...prev, ifrs13: report }));
          trackDownload(`IFRS13_${reportingDate}.pdf`);
          break;
        }
        case 'pra110': {
          const report = await api.generatePRA110(reportingDate);
          setGeneratedReports((prev) => ({ ...prev, pra110: report }));
          trackDownload(`PRA110_${reportingDate}.xml`);
          break;
        }
        case 'fry14q': {
          const report = await api.generateFRY14Q(reportingDate);
          setGeneratedReports((prev) => ({ ...prev, fry14q: report }));
          trackDownload(`FRY14Q_${reportingDate}.csv`);
          break;
        }
        default: {
          // For non-regulatory reports, use the generic report generation
          await api.generateReport(reportId, { reporting_date: reportingDate });
          const ext = reportMeta?.format?.toLowerCase() ?? 'pdf';
          trackDownload(`${reportId}_${reportingDate}.${ext}`);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate report');
    } finally {
      setGenerating(null);
    }
  };

  const handleDownloadXML = (reportId: number) => {
    window.open(api.downloadPRA110XML(reportId), '_blank');
  };

  const handleDownloadCSV = (reportId: number) => {
    window.open(api.downloadFRY14QCSV(reportId), '_blank');
  };

  const loadAuditTrail = async () => {
    setAuditLoading(true);
    try {
      const endDate = new Date().toISOString().split('T')[0];
      const startDate = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
      const events = await api.getAuditTrail({
        start_date: startDate,
        end_date: endDate,
        limit: 50,
      });
      setAuditEvents(events);
    } catch (err) {
      console.error('Failed to load audit trail:', err);
    } finally {
      setAuditLoading(false);
    }
  };

  const toggleAssetClass = (ac: string) => {
    setSelectedAssetClasses((prev) =>
      prev.includes(ac) ? prev.filter((x) => x !== ac) : [...prev, ac]
    );
  };

  const toggleColumn = (col: string) => {
    setSelectedColumns((prev) =>
      prev.includes(col) ? prev.filter((x) => x !== col) : [...prev, col]
    );
  };

  const [customGenerating, setCustomGenerating] = useState(false);
  const [recentDownloads, setRecentDownloads] = useState<
    Array<{ name: string; generated: string; size: string }>
  >([]);

  const handleGenerateCustomReport = async () => {
    setCustomGenerating(true);
    setError(null);
    try {
      const exportType = selectedReportType.toLowerCase().replace(/\s+/g, '_');
      const result = await api.exportToExcel(exportType, {
        format: selectedFormat,
        asset_classes: selectedAssetClasses.length > 0 ? selectedAssetClasses : undefined,
        columns: selectedColumns,
        date_range: dateRange.start && dateRange.end ? dateRange : undefined,
      });
      const ext = selectedFormat.toLowerCase() === 'csv' ? 'csv' : selectedFormat.toLowerCase();
      const fileName = `${selectedReportType.replace(/\s+/g, '_')}_${new Date().toISOString().split('T')[0]}.${ext}`;
      setRecentDownloads((prev) => [
        { name: fileName, generated: new Date().toISOString(), size: 'Ready' },
        ...prev.slice(0, 19),
      ]);
      if (result.download_url) {
        // Trigger actual file download
        const link = document.createElement('a');
        link.href = result.download_url;
        link.download = fileName;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate custom report');
    } finally {
      setCustomGenerating(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Tabs */}
      <div className="flex gap-2 border-b border-enterprise-200 pb-2">
        <button
          onClick={() => setActiveTab('catalog')}
          className={cn(
            'px-4 py-2 text-sm font-medium rounded-t-lg transition-colors',
            activeTab === 'catalog'
              ? 'bg-primary-50 text-primary-700 border-b-2 border-primary-600'
              : 'text-enterprise-500 hover:text-enterprise-700'
          )}
        >
          Report Catalog
        </button>
        <button
          onClick={() => {
            setActiveTab('audit');
            loadAuditTrail();
          }}
          className={cn(
            'px-4 py-2 text-sm font-medium rounded-t-lg transition-colors flex items-center gap-2',
            activeTab === 'audit'
              ? 'bg-primary-50 text-primary-700 border-b-2 border-primary-600'
              : 'text-enterprise-500 hover:text-enterprise-700'
          )}
        >
          <History size={16} />
          Audit Trail (SOX)
        </button>
      </div>

      {/* Error Display */}
      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg flex items-center gap-3">
          <AlertCircle className="text-red-500" size={20} />
          <span className="text-red-700">{error}</span>
          <button onClick={() => setError(null)} className="ml-auto text-red-500 hover:text-red-700">
            &times;
          </button>
        </div>
      )}

      {activeTab === 'catalog' ? (
        <>
          {/* Report Catalog */}
          <Card title="Regulatory Report Catalog">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {mockReports.map((report) => {
                const isRegulatoryReport = ['pillar3', 'ifrs13', 'pra110', 'fry14q'].includes(report.id);
                const generatedReport = generatedReports[report.id as keyof typeof generatedReports];

                return (
                  <div
                    key={report.id}
                    className="p-5 rounded-xl border border-enterprise-200 bg-white hover:border-primary-300 hover:shadow-enterprise-md transition-all duration-200"
                  >
                    <div className="flex items-start justify-between mb-3">
                      <div className="p-2 bg-enterprise-50 rounded-lg">
                        {formatIcons[report.format]}
                      </div>
                      <div className="flex flex-col items-end gap-1">
                        <Badge variant="default" size="sm">
                          {report.frequency}
                        </Badge>
                        {isRegulatoryReport && (
                          <Badge variant="blue" size="sm">
                            Regulatory
                          </Badge>
                        )}
                      </div>
                    </div>

                    <h3 className="font-semibold text-enterprise-800 mb-1">{report.title}</h3>
                    <p className="text-sm text-enterprise-500 mb-4">{report.description}</p>

                    <div className="flex items-center gap-2 text-xs text-enterprise-400 mb-4">
                      <Clock size={14} />
                      <span>Last run: {formatDateTime(report.last_run)}</span>
                    </div>

                    {/* Generated Report Status */}
                    {generatedReport && (
                      <div className="mb-3 p-2 bg-green-50 border border-green-200 rounded-lg">
                        <div className="flex items-center gap-2 text-green-700 text-xs">
                          <CheckCircle size={14} />
                          <span>Generated: Report #{generatedReport.report_id}</span>
                        </div>
                        <div className="text-xs text-green-600 mt-1">
                          Status: {generatedReport.status}
                        </div>
                        {/* Download buttons for PRA110 and FRY14Q */}
                        {report.id === 'pra110' && (generatedReport as PRA110Report).xml_content && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="mt-2 w-full"
                            icon={<Download size={14} />}
                            onClick={() => handleDownloadXML(generatedReport.report_id)}
                          >
                            Download XML
                          </Button>
                        )}
                        {report.id === 'fry14q' && (generatedReport as FRY14QReport).csv_content && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="mt-2 w-full"
                            icon={<Download size={14} />}
                            onClick={() => handleDownloadCSV(generatedReport.report_id)}
                          >
                            Download CSV
                          </Button>
                        )}
                      </div>
                    )}

                    <Button
                      variant="secondary"
                      size="sm"
                      className="w-full"
                      icon={
                        generating === report.id ? (
                          <div className="w-4 h-4 border-2 border-enterprise-400 border-t-transparent rounded-full animate-spin" />
                        ) : (
                          <Download size={14} />
                        )
                      }
                      onClick={() => handleGenerateReport(report.id)}
                      disabled={generating === report.id}
                    >
                      {generating === report.id ? 'Generating...' : 'Generate Report'}
                    </Button>
                  </div>
                );
              })}
            </div>
          </Card>

      {/* Custom Report Builder */}
      <Card title="Build Custom Report">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <div className="space-y-6">
            {/* Report Type */}
            <div>
              <label className="block text-sm font-semibold text-enterprise-700 mb-2">
                Report Type
              </label>
              <select
                value={selectedReportType}
                onChange={(e) => setSelectedReportType(e.target.value)}
                className="w-full px-3 py-2.5 bg-white border border-enterprise-300 rounded-lg text-sm text-enterprise-800 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors"
              >
                {reportTypes.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
            </div>

            {/* Date Range */}
            <div>
              <label className="block text-sm font-semibold text-enterprise-700 mb-2">
                Period
              </label>
              <div className="flex gap-3 items-center">
                <input
                  type="date"
                  value={dateRange.start}
                  onChange={(e) =>
                    setDateRange((prev) => ({ ...prev, start: e.target.value }))
                  }
                  className="flex-1 px-3 py-2.5 bg-white border border-enterprise-300 rounded-lg text-sm text-enterprise-800 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors"
                />
                <span className="text-enterprise-400 font-medium">to</span>
                <input
                  type="date"
                  value={dateRange.end}
                  onChange={(e) =>
                    setDateRange((prev) => ({ ...prev, end: e.target.value }))
                  }
                  className="flex-1 px-3 py-2.5 bg-white border border-enterprise-300 rounded-lg text-sm text-enterprise-800 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors"
                />
              </div>
            </div>

            {/* Asset Classes */}
            <div>
              <label className="block text-sm font-semibold text-enterprise-700 mb-2">
                Asset Classes
              </label>
              <div className="flex flex-wrap gap-2">
                {assetClasses.map((ac) => (
                  <button
                    key={ac}
                    onClick={() => toggleAssetClass(ac)}
                    className={cn(
                      'px-4 py-2 rounded-lg text-sm font-medium border transition-all duration-150',
                      selectedAssetClasses.includes(ac)
                        ? 'bg-primary-600 border-primary-600 text-white shadow-sm'
                        : 'bg-white border-enterprise-300 text-enterprise-600 hover:border-primary-400 hover:text-primary-600'
                    )}
                  >
                    {ac}
                  </button>
                ))}
              </div>
              <p className="text-xs text-enterprise-400 mt-2">
                {selectedAssetClasses.length === 0
                  ? 'All asset classes will be included'
                  : `Selected: ${selectedAssetClasses.join(', ')}`}
              </p>
            </div>

            {/* Format */}
            <div>
              <label className="block text-sm font-semibold text-enterprise-700 mb-2">
                Format
              </label>
              <div className="flex gap-3">
                {formats.map((format) => (
                  <button
                    key={format}
                    onClick={() => setSelectedFormat(format)}
                    className={cn(
                      'flex items-center gap-2 px-4 py-2.5 rounded-lg border transition-all duration-150',
                      selectedFormat === format
                        ? 'bg-primary-600 border-primary-600 text-white shadow-sm'
                        : 'bg-white border-enterprise-300 text-enterprise-600 hover:border-primary-400'
                    )}
                  >
                    {selectedFormat === format ? (
                      <FileSpreadsheet size={18} className="text-white" />
                    ) : (
                      formatIcons[format]
                    )}
                    <span className="font-medium">{format}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="space-y-6">
            {/* Columns */}
            <div>
              <label className="block text-sm font-semibold text-enterprise-700 mb-2">
                Columns
              </label>
              <div className="grid grid-cols-2 gap-2 max-h-64 overflow-y-auto p-3 bg-enterprise-50 rounded-lg border border-enterprise-200">
                {columns.map((col) => (
                  <label
                    key={col}
                    className="flex items-center gap-2 cursor-pointer p-2 rounded-lg hover:bg-white transition-colors"
                  >
                    <input
                      type="checkbox"
                      checked={selectedColumns.includes(col)}
                      onChange={() => toggleColumn(col)}
                      className="rounded border-enterprise-300 text-primary-600 focus:ring-primary-500 focus:ring-offset-0"
                    />
                    <span className="text-sm text-enterprise-700">{col}</span>
                  </label>
                ))}
              </div>
              <p className="text-xs text-enterprise-400 mt-2">
                {selectedColumns.length} columns selected
              </p>
            </div>

            {/* Generate Button */}
            <div className="pt-4">
              <Button
                className="w-full"
                icon={customGenerating
                  ? <div className="w-4 h-4 border-2 border-enterprise-400 border-t-transparent rounded-full animate-spin" />
                  : <Plus size={16} />
                }
                onClick={handleGenerateCustomReport}
                disabled={selectedColumns.length === 0 || customGenerating}
              >
                {customGenerating ? 'Generating...' : 'Generate Custom Report'}
              </Button>
            </div>
          </div>
        </div>
      </Card>

      {/* Recent Reports — dynamically tracked from generated reports */}
      {recentDownloads.length > 0 && (
        <Card title="Recent Downloads">
          <div className="space-y-2">
            {recentDownloads.map((file, idx) => {
              const ext = file.name.split('.').pop()?.toLowerCase();
              const formatKey = ext === 'xlsx' ? 'Excel' : ext === 'pptx' ? 'PowerPoint' : ext === 'csv' ? 'CSV' : ext === 'xml' ? 'XML' : 'PDF';
              return (
                <div
                  key={`${file.name}-${idx}`}
                  className="flex items-center justify-between p-4 rounded-lg bg-enterprise-50 hover:bg-enterprise-100 cursor-pointer transition-colors border border-transparent hover:border-enterprise-200"
                >
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-white rounded-lg border border-enterprise-200">
                      {formatIcons[formatKey]}
                    </div>
                    <div>
                      <p className="font-medium text-sm text-enterprise-800">{file.name}</p>
                      <p className="text-xs text-enterprise-500">
                        {formatDateTime(file.generated)} - {file.size}
                      </p>
                    </div>
                  </div>
                  <Button variant="ghost" size="sm" icon={<Download size={16} />}>
                    Download
                  </Button>
                </div>
              );
            })}
          </div>
        </Card>
      )}
        </>
      ) : (
        /* Audit Trail Tab */
        <Card title="SOX-Compliant Audit Trail">
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <p className="text-sm text-enterprise-500">
                Immutable audit log of all valuation-related events for regulatory compliance
              </p>
              <Button
                variant="secondary"
                size="sm"
                icon={<Download size={14} />}
                onClick={() => {
                  const endDate = new Date().toISOString().split('T')[0];
                  const startDate = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
                  window.open(api.downloadAuditReportExcel(startDate, endDate), '_blank');
                }}
              >
                Export to Excel
              </Button>
            </div>

            {auditLoading ? (
              <div className="flex items-center justify-center py-8">
                <div className="w-8 h-8 border-4 border-primary-200 border-t-primary-600 rounded-full animate-spin" />
              </div>
            ) : auditEvents.length === 0 ? (
              <div className="text-center py-8 text-enterprise-400">
                No audit events found for the last 30 days
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-enterprise-200">
                      <th className="text-left py-3 px-4 font-semibold text-enterprise-600">Timestamp</th>
                      <th className="text-left py-3 px-4 font-semibold text-enterprise-600">Event Type</th>
                      <th className="text-left py-3 px-4 font-semibold text-enterprise-600">User</th>
                      <th className="text-left py-3 px-4 font-semibold text-enterprise-600">Details</th>
                      <th className="text-left py-3 px-4 font-semibold text-enterprise-600">IP Address</th>
                    </tr>
                  </thead>
                  <tbody>
                    {auditEvents.map((event) => (
                      <tr key={event.event_id} className="border-b border-enterprise-100 hover:bg-enterprise-50">
                        <td className="py-3 px-4 text-enterprise-700">
                          {formatDateTime(event.timestamp)}
                        </td>
                        <td className="py-3 px-4">
                          <Badge
                            variant={
                              event.event_type.includes('REPORT') ? 'blue' :
                              event.event_type.includes('EXCEPTION') ? 'amber' :
                              'default'
                            }
                            size="sm"
                          >
                            {event.event_type}
                          </Badge>
                        </td>
                        <td className="py-3 px-4 text-enterprise-700">{event.user}</td>
                        <td className="py-3 px-4 text-enterprise-500 max-w-xs truncate">
                          {JSON.stringify(event.details).slice(0, 50)}...
                        </td>
                        <td className="py-3 px-4 text-enterprise-400 font-mono text-xs">
                          {event.ip_address || '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </Card>
      )}
    </div>
  );
}
