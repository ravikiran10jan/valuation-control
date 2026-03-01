export interface Position {
  position_id: number;
  trade_id: string;
  product_type: string;
  asset_class: string;
  currency_pair: string;
  notional: number;
  notional_usd: number;
  currency: string;
  trade_date: string;
  maturity_date: string;
  settlement_date: string | null;
  counterparty: string;
  desk_mark: number;
  vc_fair_value: number;
  book_value_usd: number;
  difference: number;
  difference_pct: number;
  exception_status: 'GREEN' | 'AMBER' | 'RED' | null;
  fair_value_level: 'L1' | 'L2' | 'L3' | null;
  pricing_source: string | null;
  fva_usd: number | null;
  valuation_date: string;
  created_at: string;
  updated_at: string;
}

export interface Exception {
  exception_id: number;
  position_id: number;
  difference: number;
  difference_pct: number;
  severity: 'AMBER' | 'RED';
  status: 'OPEN' | 'INVESTIGATING' | 'RESOLVED' | 'ESCALATED';
  created_date: string;
  assigned_to: string | null;
  days_open: number;
  escalation_level: number;
  resolution_notes: string | null;
  resolved_date: string | null;
  created_at: string;
  updated_at: string;
  position?: Position;
  comments?: ExceptionComment[];
}

export interface ExceptionComment {
  comment_id: number;
  exception_id: number;
  user_name: string;
  comment_text: string;
  attachments?: { files: string[] };
  timestamp: string;
}

export interface ExceptionSummary {
  total_exceptions: number;
  red_count: number;
  amber_count: number;
  avg_days_to_resolve: number;
}

export interface ExceptionFilters {
  severity?: 'AMBER' | 'RED' | '';
  status?: 'OPEN' | 'INVESTIGATING' | 'RESOLVED' | 'ESCALATED' | '';
  asset_class?: string;
  assigned_to?: string;
  start_date?: string;
  end_date?: string;
}

export interface ValuationComparison {
  comparison_id: number;
  position_id: number;
  desk_mark: number;
  vc_fair_value: number;
  difference: number;
  difference_pct: number;
  status: 'GREEN' | 'AMBER' | 'RED';
  comparison_date: string;
  created_at: string;
}

export interface ComparisonResult {
  position_id: number;
  desk_mark: number;
  vc_fair_value: number;
  difference: number;
  difference_pct: number;
  status: 'GREEN' | 'AMBER' | 'RED';
  comparison_date: string;
  comparison_id: number;
  exception_id: number | null;
}

export interface BatchComparisonResult {
  total_compared: number;
  green: number;
  amber: number;
  red: number;
  errors: { position_id: number; error: string }[];
}

export interface EscalationResult {
  checked: number;
  escalated_to_manager: number;
  escalated_to_committee: number;
}

export interface CommitteeAgendaItem {
  agenda_id: number;
  exception_id: number;
  position_id: number;
  difference: number;
  status: string;
  meeting_date: string;
  resolution: string | null;
  created_at: string;
}

export interface KPIData {
  total_positions: number;
  total_fair_value: number;
  open_exceptions: number;
  red_exceptions: number;
  amber_exceptions: number;
  total_fva_reserve: number;
  total_ava: number;
  trends: {
    positions_trend: number;
    fair_value_trend: number;
    exceptions_trend: number;
    red_trend: number;
    fva_trend: number;
    ava_trend: number;
  };
}

export interface ExceptionTrend {
  date: string;
  total: number;
  red: number;
  amber: number;
  green: number;
}

export interface AssetClassBreakdown {
  asset_class: string;
  fair_value: number;
  fva_reserve: number;
  position_count: number;
}

export interface Alert {
  id: string;
  severity: 'high' | 'medium' | 'low';
  title: string;
  message: string;
  timestamp: string;
  read: boolean;
}

export interface ValuationRun {
  id: string;
  name: string;
  status: 'completed' | 'in_progress' | 'pending' | 'failed';
  scheduled_time: string;
  progress?: number;
  total?: number;
}

export interface ValuationMethod {
  method: string;
  value: number;
  diff_pct?: number;
}

export interface Greek {
  name: string;
  value: number;
  unit: string;
}

export interface PnLAttribution {
  date: string;
  delta: number;
  vega: number;
  theta: number;
  unexplained: number;
}

export interface PositionHistory {
  id: string;
  date: string;
  user: string;
  action: string;
  details: string;
}

export interface Reserve {
  fva: number;
  ava: number;
  model_reserve: number;
  day_1_pnl: number;
}

// ── Agent 5 Reserve Calculation Types ────────────────────────────
export interface AVAComponentsDetail {
  mpu: number;
  close_out: number;
  model_risk: number;
  credit_spreads: number;
  funding: number;
  concentration: number;
  admin: number;
}

export interface FVACalcResult {
  position_id: number;
  fva_amount: number;
  desk_mark: number | null;
  vc_fair_value: number | null;
  rationale: string;
  calculation_date: string;
}

export interface AVACalcResult {
  position_id: number;
  total_ava: number;
  components: AVAComponentsDetail;
  calculation_date: string;
}

export interface ModelComparisonEntry {
  model: string;
  value: number;
}

export interface ModelReserveCalcResult {
  position_id: number;
  model_reserve: number;
  model_range: number;
  model_comparison: ModelComparisonEntry[];
  calculation_date: string;
}

export interface AmortizationEntry {
  period_date: string;
  amortization_amount: number;
  cumulative_recognized: number;
  remaining_deferred: number;
}

export interface Day1PnLCalcResult {
  position_id: number;
  transaction_price: number;
  fair_value: number;
  day1_pnl: number;
  recognition_status: 'RECOGNIZED' | 'DEFERRED';
  recognized_amount: number;
  deferred_amount: number;
  trade_date: string | null;
  amortization_schedule: AmortizationEntry[];
}

export interface PositionReserveResult {
  position_id: number;
  fva: FVACalcResult;
  ava: AVACalcResult;
  model_reserve: ModelReserveCalcResult | null;
  day1_pnl: Day1PnLCalcResult;
  total_reserve: number;
  calculation_date: string;
}

export interface ReserveSummaryResult {
  total_fva: number;
  total_ava: number;
  total_model_reserve: number;
  total_day1_deferred: number;
  grand_total: number;
  position_count: number;
  calculation_date: string;
}

export interface FVAByAssetClass {
  asset_class: string;
  total_fva: number;
  position_count: number;
}

export interface PositionReserveRequest {
  position: {
    position_id: number;
    trade_id: string;
    product_type?: string;
    asset_class?: string;
    notional?: number;
    currency?: string;
    trade_date?: string;
    maturity_date?: string;
    desk_mark?: number;
    vc_fair_value?: number;
    classification?: string;
    position_direction?: string;
    transaction_price?: number;
  };
  dealer_quotes?: { dealer_name: string; value: number }[];
  model_results?: ModelComparisonEntry[];
  total_book_value?: number;
}

export interface MarketDataPoint {
  label: string;
  value: string | number;
  source?: string;
}

export interface Report {
  id: string;
  title: string;
  description: string;
  frequency: string;
  last_run: string;
  format: 'Excel' | 'PDF' | 'PowerPoint' | 'XML' | 'CSV';
}

// Regulatory Reporting Types
export type ReportType = 'PILLAR3' | 'IFRS13' | 'PRA110' | 'FRY14Q' | 'ECB';
export type ReportStatus = 'DRAFT' | 'PENDING_REVIEW' | 'APPROVED' | 'SUBMITTED' | 'REJECTED';
export type FairValueLevel = 'Level 1' | 'Level 2' | 'Level 3';
export type AuditEventType = 
  | 'VALUATION_RUN' 
  | 'MARK_ADJUSTMENT' 
  | 'EXCEPTION_CREATED' 
  | 'EXCEPTION_RESOLVED'
  | 'REPORT_GENERATED'
  | 'REPORT_SUBMITTED'
  | 'AVA_CALCULATED'
  | 'LEVEL_TRANSFER';

export interface AVABreakdown {
  market_price_uncertainty: number;
  close_out_costs: number;
  model_risk: number;
  unearned_credit_spreads: number;
  investment_funding: number;
  concentrated_positions: number;
  future_admin_costs: number;
  total: number;
}

export interface Pillar3Table32 {
  total_ava: string;
  breakdown: Record<string, number>;
  as_pct_of_cet1: string;
}

export interface Pillar3Report {
  report_id: number;
  reporting_date: string;
  status: ReportStatus;
  tables: { '3.2'?: Pillar3Table32 };
  generated_at: string;
  submitted_at?: string;
  submitted_to?: string;
}

export interface FairValueLevelSummary {
  level: FairValueLevel;
  count: number;
  total_fair_value: number;
  percentage_of_total: number;
}

export interface Level3Movement {
  opening_balance: number;
  purchases: number;
  issuances: number;
  transfers_in: number;
  transfers_out: number;
  settlements: number;
  pnl: number;
  oci: number;
  closing_balance: number;
  check_passed: boolean;
}

export interface ValuationTechnique {
  product_type: string;
  technique: string;
  inputs: string[];
  observable_inputs: boolean;
}

export interface IFRS13Report {
  report_id: number;
  reporting_date: string;
  status: ReportStatus;
  fair_value_hierarchy: FairValueLevelSummary[];
  level3_reconciliation: Level3Movement;
  valuation_techniques: ValuationTechnique[];
  generated_at: string;
}

export interface PRA110SectionD {
  d010_mpu: number;
  d020_close_out: number;
  d030_model_risk: number;
  d040_credit_spreads: number;
  d050_funding: number;
  d060_concentration: number;
  d070_admin: number;
  d080_total_ava: number;
}

export interface PRA110Report {
  report_id: number;
  reporting_date: string;
  firm_reference: string;
  status: ReportStatus;
  section_d: PRA110SectionD;
  xml_content?: string;
  generated_at: string;
  submitted_at?: string;
}

export interface VaRMetrics {
  var_1day_99: number;
  var_10day_99: number;
  stressed_var?: number;
}

export interface FRY14QScheduleH1 {
  fair_value_hierarchy: FairValueLevelSummary[];
  prudent_valuation: AVABreakdown;
  var_metrics: VaRMetrics;
}

export interface FRY14QReport {
  report_id: number;
  reporting_date: string;
  firm_reference: string;
  status: ReportStatus;
  schedule_h1: FRY14QScheduleH1;
  csv_content?: string;
  generated_at: string;
  submitted_at?: string;
}

export interface AuditEvent {
  event_id: string;
  event_type: AuditEventType;
  user: string;
  timestamp: string;
  details: Record<string, unknown>;
  ip_address?: string;
}

export interface AuditReport {
  period_start: string;
  period_end: string;
  total_events: number;
  events_by_type: Record<string, number>;
  users: string[];
  events: AuditEvent[];
}

export interface RegulatoryReport {
  report_id: number;
  report_type: ReportType;
  reporting_date: string;
  firm_reference: string;
  status: ReportStatus;
  content: Record<string, unknown>;
  file_format?: string;
  generated_at: string;
  approved_at?: string;
  approved_by?: string;
  submitted_at?: string;
  submission_ref?: string;
}

export interface User {
  id: string;
  name: string;
  email: string;
  role: 'analyst' | 'manager' | 'executive';
}

// ── Dispute Workflow Types ───────────────────────────────────────
export type DisputeState =
  | 'INITIATED'
  | 'DESK_REVIEWING'
  | 'DESK_RESPONDED'
  | 'VC_REVIEWING'
  | 'NEGOTIATING'
  | 'ESCALATED'
  | 'RESOLVED_VC_WIN'
  | 'RESOLVED_DESK_WIN'
  | 'RESOLVED_COMPROMISE';

export type DisputeResolutionType = 'VC_WIN' | 'DESK_WIN' | 'COMPROMISE';

export interface Dispute {
  dispute_id: number;
  exception_id: number;
  position_id: number;
  state: DisputeState;
  vc_position: string | null;
  desk_position: string | null;
  vc_analyst: string;
  desk_trader: string | null;
  desk_mark: number | null;
  vc_fair_value: number | null;
  difference: number | null;
  difference_pct: number | null;
  resolution_type: DisputeResolutionType | null;
  final_mark: number | null;
  audit_trail: DisputeAuditEntry[];
  created_date: string;
  resolved_date: string | null;
  created_at: string;
  updated_at: string;
  messages?: DisputeMessage[];
  approvals?: DisputeApproval[];
  attachments?: DisputeAttachment[];
}

export interface DisputeAuditEntry {
  action: string;
  actor: string;
  detail: string;
  timestamp: string;
  from_state: string | null;
}

export interface DisputeMessage {
  message_id: number;
  dispute_id: number;
  sender: string;
  sender_role: 'VC' | 'DESK' | 'MANAGER';
  message_text: string;
  attachments?: { files: string[] };
  source: 'platform' | 'email';
  timestamp: string;
}

export interface DisputeApproval {
  approval_id: number;
  dispute_id: number;
  requested_by: string;
  approved_by: string | null;
  old_mark: number;
  new_mark: number;
  justification: string;
  status: 'PENDING' | 'APPROVED' | 'REJECTED';
  requested_date: string;
  approved_date: string | null;
}

export interface DisputeAttachment {
  attachment_id: number;
  dispute_id: number;
  filename: string;
  content_type: string | null;
  file_size_bytes: number | null;
  document_type: string | null;
  version: number;
  uploaded_by: string;
  uploaded_at: string;
  presigned_url?: string;
}

export interface DisputeSummary {
  total_disputes: number;
  initiated: number;
  in_progress: number;
  escalated: number;
  resolved: number;
  avg_days_to_resolve: number;
}

export interface DisputeCreate {
  exception_id: number;
  position_id: number;
  vc_position: string;
  vc_analyst: string;
  desk_trader?: string;
  desk_mark?: number;
  vc_fair_value?: number;
}

export interface DeskResponse {
  desk_position: string;
  desk_trader: string;
  proposed_mark?: number;
}

export interface DisputeResolve {
  resolution_type: DisputeResolutionType;
  final_mark: number;
  actor: string;
  notes?: string;
}

export interface DisputeMessageCreate {
  sender: string;
  sender_role: 'VC' | 'DESK' | 'MANAGER';
  message_text: string;
  attachments?: { files: string[] };
}

export interface DisputeApprovalCreate {
  requested_by: string;
  old_mark: number;
  new_mark: number;
  justification: string;
}

export interface DisputeApprovalDecision {
  approver: string;
  decision: 'APPROVED' | 'REJECTED';
}
