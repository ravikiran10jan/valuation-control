import type {
  KPIData,
  Exception,
  ExceptionComment,
  ExceptionSummary,
  ExceptionFilters,
  Position,
  ExceptionTrend,
  AssetClassBreakdown,
  Alert,
  ValuationRun,
  ValuationComparison,
  ComparisonResult,
  BatchComparisonResult,
  EscalationResult,
  CommitteeAgendaItem,
  Report,
  Pillar3Report,
  IFRS13Report,
  PRA110Report,
  FRY14QReport,
  AuditEvent,
  AuditReport,
  AuditEventType,
  Dispute,
  DisputeSummary,
  DisputeCreate,
  DeskResponse,
  DisputeResolve,
  DisputeMessage,
  DisputeMessageCreate,
  DisputeApproval,
  DisputeApprovalCreate,
  DisputeApprovalDecision,
  DisputeAttachment,
  PositionReserveResult,
  PositionReserveRequest,
  ReserveSummaryResult,
  FVAByAssetClass,
  IPVRun,
  IPVLatestResult,
  ReserveWaterfallData,
  CapitalAdequacy,
  FVHierarchySummary,
  ValidationReport,
  PositionDeepDiveData,
} from '@/types';

const API_BASE = '/api';

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }

  return response.json();
}

export const api = {
  // KPIs
  getKPIs: () => fetchJson<KPIData>('/dashboard/kpis'),

  // ── Exceptions ────────────────────────────────────────────────
  getExceptions: (params?: ExceptionFilters) => {
    const filtered = Object.fromEntries(
      Object.entries(params ?? {}).filter(([, v]) => v !== '' && v != null)
    );
    const query = new URLSearchParams(filtered as Record<string, string>).toString();
    return fetchJson<Exception[]>(`/exceptions${query ? `?${query}` : ''}`);
  },

  getException: (id: number) =>
    fetchJson<Exception & { comments: ExceptionComment[] }>(`/exceptions/${id}`),

  updateException: (id: number, data: Partial<Exception>) =>
    fetchJson<Exception>(`/exceptions/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  assignException: (id: number, assignedTo: string) =>
    fetchJson<Exception>(`/exceptions/${id}/assign?assigned_to=${encodeURIComponent(assignedTo)}`, {
      method: 'POST',
    }),

  resolveException: (id: number, notes: string, resolvedBy: string) =>
    fetchJson<Exception>(`/exceptions/${id}/resolve`, {
      method: 'PUT',
      body: JSON.stringify({ resolution_notes: notes, resolved_by: resolvedBy }),
    }),

  addComment: (exceptionId: number, userName: string, commentText: string, attachments?: { files: string[] }) =>
    fetchJson<ExceptionComment>(`/exceptions/${exceptionId}/comment`, {
      method: 'POST',
      body: JSON.stringify({ user_name: userName, comment_text: commentText, attachments }),
    }),

  getExceptionSummary: () =>
    fetchJson<ExceptionSummary>('/exceptions/summary'),

  getExceptionStatistics: () =>
    fetchJson<Record<string, unknown>>('/exceptions/statistics'),

  // ── Comparisons ───────────────────────────────────────────────
  runComparison: (positionId: number) =>
    fetchJson<ComparisonResult>(`/comparisons/run/${positionId}`, { method: 'POST' }),

  runBatchComparison: (assetClass?: string) => {
    const query = assetClass ? `?asset_class=${encodeURIComponent(assetClass)}` : '';
    return fetchJson<BatchComparisonResult>(`/comparisons/run-batch${query}`, { method: 'POST' });
  },

  getComparisonHistory: (positionId: number, limit = 30) =>
    fetchJson<ValuationComparison[]>(`/comparisons/history/${positionId}?limit=${limit}`),

  // ── Escalation ────────────────────────────────────────────────
  checkEscalations: () =>
    fetchJson<EscalationResult>('/escalation/check', { method: 'POST' }),

  updateAging: () =>
    fetchJson<{ updated: number }>('/escalation/update-aging', { method: 'POST' }),

  // ── Committee ─────────────────────────────────────────────────
  getCommitteeAgenda: (meetingDate?: string) => {
    const query = meetingDate ? `?meeting_date=${meetingDate}` : '';
    return fetchJson<CommitteeAgendaItem[]>(`/committee/agenda${query}`);
  },

  getNextMeeting: () =>
    fetchJson<{ meeting_date: string; pending_items: number }>('/committee/next-meeting'),

  // ── Positions ─────────────────────────────────────────────────
  getPositions: (params?: { asset_class?: string; exception_status?: string }) => {
    const query = new URLSearchParams(params as Record<string, string>).toString();
    return fetchJson<Position[]>(`/positions${query ? `?${query}` : ''}`);
  },

  getPosition: (id: number) => fetchJson<Position>(`/positions/${id}`),

  // ── Trends & Analytics ────────────────────────────────────────
  getExceptionTrends: (days: number = 90) =>
    fetchJson<ExceptionTrend[]>(`/dashboard/exception-trends?days=${days}`),

  getAssetClassBreakdown: () =>
    fetchJson<AssetClassBreakdown[]>('/dashboard/asset-breakdown'),

  getExceptionAging: () =>
    fetchJson<Array<{ desk: string; asset_class: string; avg_days: number; count: number }>>('/dashboard/exception-aging'),

  // ── Alerts ────────────────────────────────────────────────────
  getAlerts: () => fetchJson<Alert[]>('/alerts'),
  markAlertRead: (id: string) =>
    fetchJson<void>(`/alerts/${id}/read`, { method: 'POST' }),

  // ── Valuation runs ────────────────────────────────────────────
  getValuationRuns: () => fetchJson<ValuationRun[]>('/valuations/runs'),
  triggerValuation: () =>
    fetchJson<{ run_id: string }>('/valuations/trigger', { method: 'POST' }),

  // ── Reports ───────────────────────────────────────────────────
  getReports: () => fetchJson<Report[]>('/reports'),
  generateReport: (reportId: string, params?: Record<string, unknown>) =>
    fetchJson<{ download_url: string }>(`/reports/${reportId}/generate`, {
      method: 'POST',
      body: JSON.stringify(params),
    }),

  // ── Data export ───────────────────────────────────────────────
  exportToExcel: (type: string, params?: Record<string, unknown>) =>
    fetchJson<{ download_url: string }>(`/export/${type}`, {
      method: 'POST',
      body: JSON.stringify(params),
    }),

  // ── Regulatory Reports ─────────────────────────────────────────
  // Pillar 3 (Basel III)
  generatePillar3: (reportingDate: string) =>
    fetchJson<Pillar3Report>(`/reports/pillar3?reporting_date=${reportingDate}`, {
      method: 'POST',
    }),

  approvePillar3: (reportId: number, approvedBy: string) =>
    fetchJson<{ status: string; report_id: number }>(`/reports/pillar3/${reportId}/approve?approved_by=${encodeURIComponent(approvedBy)}`, {
      method: 'POST',
    }),

  submitPillar3: (reportId: number, regulator: string = 'ECB') =>
    fetchJson<{ report_id: number; submitted_at: string; confirmation_id: string }>(`/reports/pillar3/${reportId}/submit?regulator=${regulator}`, {
      method: 'POST',
    }),

  // IFRS 13 Fair Value Hierarchy
  generateIFRS13: (reportingDate: string) =>
    fetchJson<IFRS13Report>(`/reports/ifrs13?reporting_date=${reportingDate}`, {
      method: 'POST',
    }),

  // PRA110 (UK)
  generatePRA110: (reportingDate: string) =>
    fetchJson<PRA110Report>(`/reports/pra110?reporting_date=${reportingDate}`, {
      method: 'POST',
    }),

  submitPRA110: (reportId: number) =>
    fetchJson<{ report_id: number; submitted_at: string; confirmation_id: string }>(`/reports/pra110/${reportId}/submit`, {
      method: 'POST',
    }),

  downloadPRA110XML: (reportId: number) =>
    `/api/reports/pra110/${reportId}/xml`,

  // FR Y-14Q (US Fed)
  generateFRY14Q: (reportingDate: string) =>
    fetchJson<FRY14QReport>(`/reports/fry14q?reporting_date=${reportingDate}`, {
      method: 'POST',
    }),

  submitFRY14Q: (reportId: number) =>
    fetchJson<{ report_id: number; submitted_at: string; confirmation_id: string }>(`/reports/fry14q/${reportId}/submit`, {
      method: 'POST',
    }),

  downloadFRY14QCSV: (reportId: number) =>
    `/api/reports/fry14q/${reportId}/csv`,

  // ── Audit Trail ────────────────────────────────────────────────
  getAuditTrail: (params: {
    start_date: string;
    end_date: string;
    event_type?: AuditEventType;
    user?: string;
    limit?: number;
    offset?: number;
  }) => {
    const query = new URLSearchParams(
      Object.fromEntries(
        Object.entries(params).filter(([, v]) => v !== undefined && v !== '')
      ) as Record<string, string>
    ).toString();
    return fetchJson<AuditEvent[]>(`/audit/trail?${query}`);
  },

  getAuditEvent: (eventId: string) =>
    fetchJson<AuditEvent>(`/audit/trail/${eventId}`),

  getAuditReport: (startDate: string, endDate: string) =>
    fetchJson<AuditReport>(`/audit/report?start_date=${startDate}&end_date=${endDate}`),

  downloadAuditReportExcel: (startDate: string, endDate: string) =>
    `/api/audit/report/excel?start_date=${startDate}&end_date=${endDate}`,

  getAuditStatistics: (startDate: string, endDate: string) =>
    fetchJson<Record<string, unknown>>(`/audit/statistics?start_date=${startDate}&end_date=${endDate}`),

  // ── Disputes (Agent 4) ──────────────────────────────────────────
  getDisputes: (params?: { state?: string; exception_id?: number; vc_analyst?: string; desk_trader?: string }) => {
    const query = new URLSearchParams(
      Object.fromEntries(
        Object.entries(params ?? {}).filter(([, v]) => v !== undefined && v !== '')
      ) as Record<string, string>
    ).toString();
    return fetchJson<Dispute[]>(`/disputes${query ? `?${query}` : ''}`);
  },

  getDispute: (id: number) => fetchJson<Dispute>(`/disputes/${id}`),

  getDisputeSummary: () => fetchJson<DisputeSummary>('/disputes/summary'),

  createDispute: (data: DisputeCreate) =>
    fetchJson<Dispute>('/disputes/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  transitionDispute: (disputeId: number, newState: string, actor: string, reason?: string) =>
    fetchJson<Dispute>(`/disputes/${disputeId}/transition`, {
      method: 'POST',
      body: JSON.stringify({ new_state: newState, actor, reason }),
    }),

  deskRespond: (disputeId: number, data: DeskResponse) =>
    fetchJson<Dispute>(`/disputes/${disputeId}/desk-respond`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  resolveDispute: (disputeId: number, data: DisputeResolve) =>
    fetchJson<Dispute>(`/disputes/${disputeId}/resolve`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Dispute Messages
  getDisputeMessages: (disputeId: number) =>
    fetchJson<DisputeMessage[]>(`/disputes/${disputeId}/messages/`),

  addDisputeMessage: (disputeId: number, data: DisputeMessageCreate) =>
    fetchJson<DisputeMessage>(`/disputes/${disputeId}/messages/`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Dispute Approvals
  getDisputeApprovals: (disputeId: number) =>
    fetchJson<DisputeApproval[]>(`/disputes/${disputeId}/approvals/`),

  requestMarkAdjustment: (disputeId: number, data: DisputeApprovalCreate) =>
    fetchJson<DisputeApproval>(`/disputes/${disputeId}/approvals/`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  decideApproval: (disputeId: number, approvalId: number, data: DisputeApprovalDecision) =>
    fetchJson<DisputeApproval>(`/disputes/${disputeId}/approvals/${approvalId}/decide`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Dispute Documents
  getDisputeDocuments: (disputeId: number) =>
    fetchJson<DisputeAttachment[]>(`/disputes/${disputeId}/documents/`),

  uploadDisputeDocument: async (
    disputeId: number,
    file: File,
    documentType: string,
    uploadedBy: string
  ): Promise<DisputeAttachment & { presigned_url: string }> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await fetch(
      `${API_BASE}/disputes/${disputeId}/documents/?document_type=${encodeURIComponent(documentType)}&uploaded_by=${encodeURIComponent(uploadedBy)}`,
      { method: 'POST', body: formData }
    );
    if (!response.ok) {
      throw new Error(`API error: ${response.status} ${response.statusText}`);
    }
    return response.json();
  },

  deleteDisputeDocument: (disputeId: number, attachmentId: number) =>
    fetch(`${API_BASE}/disputes/${disputeId}/documents/${attachmentId}`, { method: 'DELETE' }),

  // ── Reserve Calculations (Agent 5) ───────────────────────────────
  calculateAllReserves: (req: PositionReserveRequest) =>
    fetchJson<PositionReserveResult>('/reserves/calculate-all', {
      method: 'POST',
      body: JSON.stringify(req),
    }),

  calculateBatchReserves: (requests: PositionReserveRequest[]) =>
    fetchJson<PositionReserveResult[]>('/reserves/calculate-batch', {
      method: 'POST',
      body: JSON.stringify(requests),
    }),

  getReserveSummary: (calculationDate?: string) => {
    const query = calculationDate ? `?calculation_date=${calculationDate}` : '';
    return fetchJson<ReserveSummaryResult>(`/reserves/summary${query}`);
  },

  getFVAByAssetClass: (calculationDate?: string) => {
    const query = calculationDate ? `?calculation_date=${calculationDate}` : '';
    return fetchJson<FVAByAssetClass[]>(`/reserves/fva-by-asset-class${query}`);
  },

  getReservesByPosition: (positionId: number, reserveType?: string) => {
    const query = reserveType ? `?reserve_type=${reserveType}` : '';
    return fetchJson<Array<{ reserve_id: number; position_id: number; reserve_type: string; amount: number; calculation_date: string; rationale: string | null; components: Record<string, unknown> | null; created_at: string }>>(`/reserves/by-position/${positionId}${query}`);
  },

  // ── IPV Lifecycle ────────────────────────────────────────────────
  getIPVRuns: (params?: { limit?: number; status?: string }) => {
    const query = new URLSearchParams(
      Object.fromEntries(
        Object.entries(params ?? {}).filter(([, v]) => v !== undefined && v !== '')
      ) as Record<string, string>
    ).toString();
    return fetchJson<IPVRun[]>(`/ipv/runs${query ? `?${query}` : ''}`);
  },

  getIPVLatest: () => fetchJson<IPVLatestResult>('/ipv/latest'),

  triggerIPVRun: (assetClass?: string, runDate?: string) => {
    const params = new URLSearchParams();
    if (assetClass) params.set('asset_class', assetClass);
    if (runDate) params.set('run_date', runDate);
    const query = params.toString();
    return fetchJson<{ run_id: string }>(`/ipv/trigger${query ? `?${query}` : ''}`, {
      method: 'POST',
    });
  },

  getIPVPositionDetail: (positionId: number) =>
    fetchJson<PositionDeepDiveData>(`/ipv/positions/${positionId}/detail`),

  // ── Reserves Detail ──────────────────────────────────────────────
  getReservesDetail: () => fetchJson<ReserveWaterfallData>('/reserves/detail'),

  // ── Capital Adequacy ─────────────────────────────────────────────
  getCapitalAdequacy: () => fetchJson<CapitalAdequacy>('/capital-adequacy'),

  // ── Greeks ───────────────────────────────────────────────────────
  getGreeks: (positionId: number) =>
    fetchJson<{ position_id: number; greeks: Array<{ name: string; value: number; unit: string }>; error?: string }>(`/greeks/${positionId}`),

  // ── Validation ───────────────────────────────────────────────────
  getValidationReport: () => fetchJson<ValidationReport>('/validation/report'),

  // ── FV Hierarchy ─────────────────────────────────────────────────
  getFVHierarchy: () => fetchJson<FVHierarchySummary[]>('/fv-hierarchy'),

  getFVLevelTransfers: () =>
    fetchJson<Array<{ from: string; to: string; count: number; reason: string }>>('/fv-hierarchy/transfers'),
};
