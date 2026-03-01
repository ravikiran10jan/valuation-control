import { useState } from 'react';
import {
  MessageSquare,
  Clock,
  AlertTriangle,
  CheckCircle,
  Users,
  FileText,
  Send,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { Card } from '../shared/Card';
import { Button, Badge } from '../shared/Button';
import { DisputeThread } from './DisputeThread';
import { formatCurrency, formatPercent, formatDateTime, cn } from '@/utils/format';
import type {
  Dispute,
  DisputeState,
  DisputeResolutionType,
} from '@/types';

interface DisputePanelProps {
  positionId: number;
  exceptionId: number;
  dispute: Dispute | null;
  deskMark: number;
  vcFairValue: number;
  onDisputeCreated?: (dispute: Dispute) => void;
  onDisputeUpdated?: (dispute: Dispute) => void;
  currentUser: { email: string; role: 'VC' | 'DESK' | 'MANAGER'; name: string };
}

const STATE_CONFIG: Record<DisputeState, { label: string; color: string; bgColor: string }> = {
  INITIATED: { label: 'Initiated', color: 'text-blue-700', bgColor: 'bg-blue-50 border-blue-200' },
  DESK_REVIEWING: { label: 'Desk Reviewing', color: 'text-amber-700', bgColor: 'bg-amber-50 border-amber-200' },
  DESK_RESPONDED: { label: 'Desk Responded', color: 'text-purple-700', bgColor: 'bg-purple-50 border-purple-200' },
  VC_REVIEWING: { label: 'VC Reviewing', color: 'text-indigo-700', bgColor: 'bg-indigo-50 border-indigo-200' },
  NEGOTIATING: { label: 'Negotiating', color: 'text-orange-700', bgColor: 'bg-orange-50 border-orange-200' },
  ESCALATED: { label: 'Escalated', color: 'text-red-700', bgColor: 'bg-red-50 border-red-200' },
  RESOLVED_VC_WIN: { label: 'Resolved (VC)', color: 'text-green-700', bgColor: 'bg-green-50 border-green-200' },
  RESOLVED_DESK_WIN: { label: 'Resolved (Desk)', color: 'text-green-700', bgColor: 'bg-green-50 border-green-200' },
  RESOLVED_COMPROMISE: { label: 'Resolved (Compromise)', color: 'text-green-700', bgColor: 'bg-green-50 border-green-200' },
};

const WORKFLOW_STEPS: DisputeState[] = [
  'INITIATED',
  'DESK_REVIEWING',
  'DESK_RESPONDED',
  'VC_REVIEWING',
  'NEGOTIATING',
];

const SLA_DAYS = {
  desk_response: 2,
  vc_review: 2,
  escalation_warning: 5,
  auto_escalate: 7,
};

function calculateSLA(dispute: Dispute): { daysOpen: number; slaStatus: 'ok' | 'warning' | 'breach'; message: string } {
  const createdDate = new Date(dispute.created_date);
  const now = new Date();
  const daysOpen = Math.floor((now.getTime() - createdDate.getTime()) / (1000 * 60 * 60 * 24));

  if (dispute.state.startsWith('RESOLVED')) {
    return { daysOpen, slaStatus: 'ok', message: 'Resolved' };
  }

  if (daysOpen >= SLA_DAYS.auto_escalate) {
    return { daysOpen, slaStatus: 'breach', message: `${daysOpen} days - Auto-escalation triggered` };
  }
  if (daysOpen >= SLA_DAYS.escalation_warning) {
    return { daysOpen, slaStatus: 'warning', message: `${daysOpen} days - Escalation imminent` };
  }
  if (dispute.state === 'DESK_REVIEWING' && daysOpen >= SLA_DAYS.desk_response) {
    return { daysOpen, slaStatus: 'warning', message: `Desk response overdue (${daysOpen} days)` };
  }

  return { daysOpen, slaStatus: 'ok', message: `${daysOpen} day${daysOpen !== 1 ? 's' : ''} open` };
}

export function DisputePanel({
  positionId,
  exceptionId,
  dispute,
  deskMark,
  vcFairValue,
  onDisputeCreated,
  onDisputeUpdated,
  currentUser,
}: DisputePanelProps) {
  const [isCreating, setIsCreating] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [vcPosition, setVcPosition] = useState('');
  const [deskPosition, setDeskPosition] = useState('');
  const [proposedMark, setProposedMark] = useState('');
  const [resolutionType, setResolutionType] = useState<DisputeResolutionType>('COMPROMISE');
  const [finalMark, setFinalMark] = useState('');
  const [resolutionNotes, setResolutionNotes] = useState('');
  const [showThread, setShowThread] = useState(true);
  const [showAuditTrail, setShowAuditTrail] = useState(false);

  const difference = deskMark - vcFairValue;
  const differencePct = vcFairValue !== 0 ? (difference / Math.abs(vcFairValue)) * 100 : 0;

  const sla = dispute ? calculateSLA(dispute) : null;
  const isResolved = dispute?.state.startsWith('RESOLVED');

  const handleCreateDispute = async () => {
    if (!vcPosition.trim()) return;
    setIsSubmitting(true);
    try {
      // In real app: await api.createDispute({ exception_id: exceptionId, ... });
      // For now, simulate:
      const mockDispute: Dispute = {
        dispute_id: Date.now(),
        exception_id: exceptionId,
        position_id: positionId,
        state: 'INITIATED',
        vc_position: vcPosition,
        desk_position: null,
        vc_analyst: currentUser.email,
        desk_trader: null,
        desk_mark: deskMark,
        vc_fair_value: vcFairValue,
        difference,
        difference_pct: differencePct,
        resolution_type: null,
        final_mark: null,
        audit_trail: [{
          action: 'CREATED',
          actor: currentUser.email,
          detail: 'Dispute initiated by VC analyst',
          timestamp: new Date().toISOString(),
          from_state: null,
        }],
        created_date: new Date().toISOString(),
        resolved_date: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        messages: [],
        approvals: [],
        attachments: [],
      };
      onDisputeCreated?.(mockDispute);
      setIsCreating(false);
      setVcPosition('');
    } catch (err) {
      console.error('Failed to create dispute:', err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeskRespond = async () => {
    if (!dispute || !deskPosition.trim()) return;
    setIsSubmitting(true);
    try {
      // In real app: await api.deskRespond(dispute.dispute_id, { desk_position: deskPosition, desk_trader: currentUser.email, proposed_mark: proposedMark ? parseFloat(proposedMark) : undefined });
      const updated: Dispute = {
        ...dispute,
        state: 'DESK_RESPONDED',
        desk_position: deskPosition,
        desk_trader: currentUser.email,
        audit_trail: [
          ...dispute.audit_trail,
          {
            action: 'DESK_RESPONDED',
            actor: currentUser.email,
            detail: deskPosition.slice(0, 200),
            timestamp: new Date().toISOString(),
            from_state: dispute.state,
          },
        ],
        updated_at: new Date().toISOString(),
      };
      onDisputeUpdated?.(updated);
      setDeskPosition('');
      setProposedMark('');
    } catch (err) {
      console.error('Failed to submit desk response:', err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleTransition = async (newState: DisputeState, reason?: string) => {
    if (!dispute) return;
    setIsSubmitting(true);
    try {
      // In real app: const updated = await api.transitionDispute(dispute.dispute_id, newState, currentUser.email, reason);
      const updated: Dispute = {
        ...dispute,
        state: newState,
        audit_trail: [
          ...dispute.audit_trail,
          {
            action: `STATE_CHANGE:${dispute.state}->${newState}`,
            actor: currentUser.email,
            detail: reason || '',
            timestamp: new Date().toISOString(),
            from_state: dispute.state,
          },
        ],
        updated_at: new Date().toISOString(),
      };
      onDisputeUpdated?.(updated);
    } catch (err) {
      console.error('Failed to transition dispute:', err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleResolve = async () => {
    if (!dispute || !finalMark) return;
    setIsSubmitting(true);
    try {
      // In real app: await api.resolveDispute(dispute.dispute_id, { resolution_type: resolutionType, final_mark: parseFloat(finalMark), actor: currentUser.email, notes: resolutionNotes || undefined });
      const targetState: DisputeState = `RESOLVED_${resolutionType}` as DisputeState;
      const updated: Dispute = {
        ...dispute,
        state: targetState,
        resolution_type: resolutionType,
        final_mark: parseFloat(finalMark),
        resolved_date: new Date().toISOString(),
        audit_trail: [
          ...dispute.audit_trail,
          {
            action: `RESOLVED:${resolutionType}`,
            actor: currentUser.email,
            detail: resolutionNotes || `Final mark: ${finalMark}`,
            timestamp: new Date().toISOString(),
            from_state: dispute.state,
          },
        ],
        updated_at: new Date().toISOString(),
      };
      onDisputeUpdated?.(updated);
      setFinalMark('');
      setResolutionNotes('');
    } catch (err) {
      console.error('Failed to resolve dispute:', err);
    } finally {
      setIsSubmitting(false);
    }
  };

  // No dispute yet - show create form
  if (!dispute) {
    if (!isCreating) {
      return (
        <Card title="Dispute Status">
          <div className="text-center py-8">
            <MessageSquare className="mx-auto h-12 w-12 text-enterprise-300" />
            <h3 className="mt-4 text-lg font-medium text-enterprise-800">No Active Dispute</h3>
            <p className="mt-2 text-sm text-enterprise-500">
              Initiate a dispute to challenge the desk mark and begin the resolution workflow.
            </p>
            <Button onClick={() => setIsCreating(true)} className="mt-4" icon={<AlertTriangle size={16} />}>
              Initiate Dispute
            </Button>
          </div>
        </Card>
      );
    }

    return (
      <Card title="Initiate Dispute">
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4 p-4 bg-enterprise-50 rounded-lg">
            <div>
              <p className="text-sm text-enterprise-500">Desk Mark</p>
              <p className="text-lg font-semibold text-enterprise-800">{formatCurrency(deskMark)}</p>
            </div>
            <div>
              <p className="text-sm text-enterprise-500">VC Fair Value</p>
              <p className="text-lg font-semibold text-red-600">{formatCurrency(vcFairValue)}</p>
            </div>
            <div className="col-span-2">
              <p className="text-sm text-enterprise-500">Difference</p>
              <p className="text-lg font-bold text-red-600">
                {formatCurrency(difference)} ({formatPercent(differencePct)})
              </p>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-enterprise-700 mb-2">
              VC Position / Justification *
            </label>
            <textarea
              value={vcPosition}
              onChange={(e) => setVcPosition(e.target.value)}
              rows={4}
              className="w-full px-3 py-2 border border-enterprise-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm"
              placeholder="Explain why the VC fair value differs from the desk mark. Include model methodology, market data sources, and key assumptions..."
            />
          </div>

          <div className="flex gap-3 justify-end">
            <Button variant="secondary" onClick={() => setIsCreating(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleCreateDispute}
              disabled={!vcPosition.trim() || isSubmitting}
              icon={<Send size={16} />}
            >
              {isSubmitting ? 'Submitting...' : 'Submit Dispute'}
            </Button>
          </div>
        </div>
      </Card>
    );
  }

  // Active dispute - show workflow
  const stateConfig = STATE_CONFIG[dispute.state];
  const currentStepIndex = WORKFLOW_STEPS.indexOf(dispute.state as DisputeState);

  return (
    <div className="space-y-6">
      {/* Header with SLA */}
      <Card title={`Dispute #${dispute.dispute_id}`}>
        <div className="space-y-4">
          {/* Status and SLA Row */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className={cn('px-3 py-1.5 rounded-full text-sm font-medium border', stateConfig.bgColor, stateConfig.color)}>
                {stateConfig.label}
              </span>
              {dispute.state === 'ESCALATED' && (
                <Badge variant="red">
                  <AlertTriangle size={12} className="mr-1" />
                  Escalated to Committee
                </Badge>
              )}
            </div>
            {sla && (
              <div className={cn(
                'flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm',
                sla.slaStatus === 'breach' ? 'bg-red-50 text-red-700' :
                sla.slaStatus === 'warning' ? 'bg-amber-50 text-amber-700' :
                'bg-green-50 text-green-700'
              )}>
                <Clock size={14} />
                {sla.message}
              </div>
            )}
          </div>

          {/* Workflow Progress */}
          {!isResolved && (
            <div className="pt-4">
              <div className="flex items-center justify-between">
                {WORKFLOW_STEPS.map((step, idx) => {
                  const stepConfig = STATE_CONFIG[step];
                  const isActive = step === dispute.state;
                  const isPast = idx < currentStepIndex;
                  const isEscalated = dispute.state === 'ESCALATED';

                  return (
                    <div key={step} className="flex items-center">
                      <div className="flex flex-col items-center">
                        <div
                          className={cn(
                            'w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium border-2',
                            isActive ? 'bg-primary-600 text-white border-primary-600' :
                            isPast ? 'bg-green-100 text-green-700 border-green-300' :
                            isEscalated ? 'bg-red-100 text-red-400 border-red-200' :
                            'bg-enterprise-100 text-enterprise-400 border-enterprise-200'
                          )}
                        >
                          {isPast ? <CheckCircle size={16} /> : idx + 1}
                        </div>
                        <span className={cn(
                          'mt-2 text-xs text-center max-w-[80px]',
                          isActive ? 'text-primary-700 font-medium' : 'text-enterprise-500'
                        )}>
                          {stepConfig.label}
                        </span>
                      </div>
                      {idx < WORKFLOW_STEPS.length - 1 && (
                        <div className={cn(
                          'w-12 h-0.5 mx-2',
                          isPast ? 'bg-green-300' : 'bg-enterprise-200'
                        )} />
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Valuation Summary */}
          <div className="grid grid-cols-3 gap-4 p-4 bg-enterprise-50 rounded-lg mt-4">
            <div>
              <p className="text-sm text-enterprise-500">Desk Mark</p>
              <p className="text-lg font-semibold text-enterprise-800">{formatCurrency(dispute.desk_mark || 0)}</p>
            </div>
            <div>
              <p className="text-sm text-enterprise-500">VC Fair Value</p>
              <p className="text-lg font-semibold text-red-600">{formatCurrency(dispute.vc_fair_value || 0)}</p>
            </div>
            <div>
              <p className="text-sm text-enterprise-500">Difference</p>
              <p className="text-lg font-bold text-red-600">
                {formatCurrency(dispute.difference || 0)} ({formatPercent(dispute.difference_pct || 0)})
              </p>
            </div>
            {isResolved && dispute.final_mark && (
              <div className="col-span-3 pt-3 border-t border-enterprise-200">
                <p className="text-sm text-enterprise-500">Final Agreed Mark</p>
                <p className="text-xl font-bold text-green-600">{formatCurrency(dispute.final_mark)}</p>
              </div>
            )}
          </div>

          {/* Positions */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
              <div className="flex items-center gap-2 mb-2">
                <Users size={16} className="text-blue-600" />
                <span className="font-medium text-blue-800">VC Position</span>
              </div>
              <p className="text-sm text-blue-700">{dispute.vc_position || 'Not provided'}</p>
              <p className="text-xs text-blue-500 mt-2">— {dispute.vc_analyst}</p>
            </div>
            <div className="p-4 bg-purple-50 rounded-lg border border-purple-200">
              <div className="flex items-center gap-2 mb-2">
                <Users size={16} className="text-purple-600" />
                <span className="font-medium text-purple-800">Desk Position</span>
              </div>
              <p className="text-sm text-purple-700">{dispute.desk_position || 'Awaiting response...'}</p>
              {dispute.desk_trader && (
                <p className="text-xs text-purple-500 mt-2">— {dispute.desk_trader}</p>
              )}
            </div>
          </div>
        </div>
      </Card>

      {/* Action Panel based on state and user role */}
      {!isResolved && (
        <Card title="Actions">
          {/* Desk Response Form */}
          {dispute.state === 'DESK_REVIEWING' && currentUser.role === 'DESK' && (
            <div className="space-y-4">
              <p className="text-sm text-enterprise-600">
                Please review the VC position and provide your response.
              </p>
              <div>
                <label className="block text-sm font-medium text-enterprise-700 mb-2">
                  Desk Position / Counter-Argument *
                </label>
                <textarea
                  value={deskPosition}
                  onChange={(e) => setDeskPosition(e.target.value)}
                  rows={4}
                  className="w-full px-3 py-2 border border-enterprise-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm"
                  placeholder="Provide your justification for the desk mark. Reference client quotes, term sheet provisions, or market data..."
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-enterprise-700 mb-2">
                  Proposed Mark (Optional)
                </label>
                <input
                  type="number"
                  value={proposedMark}
                  onChange={(e) => setProposedMark(e.target.value)}
                  className="w-full px-3 py-2 border border-enterprise-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm"
                  placeholder="Enter adjusted mark if proposing a change..."
                />
              </div>
              <Button
                onClick={handleDeskRespond}
                disabled={!deskPosition.trim() || isSubmitting}
                icon={<Send size={16} />}
              >
                {isSubmitting ? 'Submitting...' : 'Submit Response'}
              </Button>
            </div>
          )}

          {/* VC Review Actions */}
          {dispute.state === 'DESK_RESPONDED' && currentUser.role === 'VC' && (
            <div className="space-y-4">
              <p className="text-sm text-enterprise-600">
                Review the desk response and decide on next steps.
              </p>
              <div className="flex gap-3">
                <Button
                  variant="secondary"
                  onClick={() => handleTransition('VC_REVIEWING', 'VC is reviewing desk response')}
                  disabled={isSubmitting}
                >
                  Continue Review
                </Button>
                <Button
                  variant="danger"
                  onClick={() => handleTransition('ESCALATED', 'Unable to reach agreement')}
                  disabled={isSubmitting}
                  icon={<AlertTriangle size={16} />}
                >
                  Escalate to Committee
                </Button>
              </div>
            </div>
          )}

          {/* Negotiation / Resolution */}
          {(dispute.state === 'VC_REVIEWING' || dispute.state === 'NEGOTIATING') && (
            <div className="space-y-4">
              <p className="text-sm text-enterprise-600">
                Select resolution outcome and final agreed mark.
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-enterprise-700 mb-2">
                    Resolution Type *
                  </label>
                  <select
                    value={resolutionType}
                    onChange={(e) => setResolutionType(e.target.value as DisputeResolutionType)}
                    className="w-full px-3 py-2 border border-enterprise-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm"
                  >
                    <option value="VC_WIN">VC Win - Use VC Fair Value</option>
                    <option value="DESK_WIN">Desk Win - Use Desk Mark</option>
                    <option value="COMPROMISE">Compromise - Agreed Mark</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-enterprise-700 mb-2">
                    Final Mark *
                  </label>
                  <input
                    type="number"
                    value={finalMark}
                    onChange={(e) => setFinalMark(e.target.value)}
                    className="w-full px-3 py-2 border border-enterprise-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm"
                    placeholder={
                      resolutionType === 'VC_WIN' ? String(dispute.vc_fair_value) :
                      resolutionType === 'DESK_WIN' ? String(dispute.desk_mark) :
                      'Enter agreed mark...'
                    }
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-enterprise-700 mb-2">
                  Resolution Notes
                </label>
                <textarea
                  value={resolutionNotes}
                  onChange={(e) => setResolutionNotes(e.target.value)}
                  rows={2}
                  className="w-full px-3 py-2 border border-enterprise-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm"
                  placeholder="Document the resolution rationale..."
                />
              </div>
              <div className="flex gap-3">
                {dispute.state === 'VC_REVIEWING' && (
                  <Button
                    variant="secondary"
                    onClick={() => handleTransition('NEGOTIATING', 'Entering negotiation phase')}
                    disabled={isSubmitting}
                  >
                    Continue Negotiating
                  </Button>
                )}
                <Button
                  onClick={handleResolve}
                  disabled={!finalMark || isSubmitting}
                  icon={<CheckCircle size={16} />}
                >
                  {isSubmitting ? 'Resolving...' : 'Resolve Dispute'}
                </Button>
                <Button
                  variant="danger"
                  onClick={() => handleTransition('ESCALATED', 'Unable to reach agreement')}
                  disabled={isSubmitting}
                  icon={<AlertTriangle size={16} />}
                >
                  Escalate
                </Button>
              </div>
            </div>
          )}

          {/* Escalated - Manager/Committee actions */}
          {dispute.state === 'ESCALATED' && currentUser.role === 'MANAGER' && (
            <div className="space-y-4">
              <div className="p-4 bg-red-50 rounded-lg border border-red-200">
                <div className="flex items-center gap-2 mb-2">
                  <AlertTriangle className="text-red-600" size={18} />
                  <span className="font-medium text-red-800">Escalated to Committee</span>
                </div>
                <p className="text-sm text-red-700">
                  This dispute requires committee review and decision.
                </p>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-enterprise-700 mb-2">
                    Committee Decision *
                  </label>
                  <select
                    value={resolutionType}
                    onChange={(e) => setResolutionType(e.target.value as DisputeResolutionType)}
                    className="w-full px-3 py-2 border border-enterprise-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm"
                  >
                    <option value="VC_WIN">Support VC Position</option>
                    <option value="DESK_WIN">Support Desk Position</option>
                    <option value="COMPROMISE">Committee Directed Mark</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-enterprise-700 mb-2">
                    Final Mark *
                  </label>
                  <input
                    type="number"
                    value={finalMark}
                    onChange={(e) => setFinalMark(e.target.value)}
                    className="w-full px-3 py-2 border border-enterprise-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm"
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-enterprise-700 mb-2">
                  Committee Resolution Notes *
                </label>
                <textarea
                  value={resolutionNotes}
                  onChange={(e) => setResolutionNotes(e.target.value)}
                  rows={3}
                  className="w-full px-3 py-2 border border-enterprise-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm"
                  placeholder="Document committee rationale and decision..."
                />
              </div>
              <Button
                onClick={handleResolve}
                disabled={!finalMark || !resolutionNotes || isSubmitting}
                icon={<CheckCircle size={16} />}
              >
                {isSubmitting ? 'Resolving...' : 'Record Committee Decision'}
              </Button>
            </div>
          )}
        </Card>
      )}

      {/* Discussion Thread */}
      <Card
        title={
          <button
            onClick={() => setShowThread(!showThread)}
            className="flex items-center gap-2 w-full text-left"
          >
            <MessageSquare size={18} />
            <span>Discussion Thread</span>
            <span className="text-enterprise-400 text-sm ml-2">
              ({dispute.messages?.length || 0} messages)
            </span>
            {showThread ? <ChevronUp size={16} className="ml-auto" /> : <ChevronDown size={16} className="ml-auto" />}
          </button>
        }
      >
        {showThread && (
          <DisputeThread
            disputeId={dispute.dispute_id}
            messages={dispute.messages || []}
            currentUser={currentUser}
            onMessageAdded={(msg) => {
              if (dispute.messages) {
                onDisputeUpdated?.({
                  ...dispute,
                  messages: [...dispute.messages, msg],
                });
              }
            }}
            disabled={isResolved}
          />
        )}
      </Card>

      {/* Audit Trail */}
      <Card
        title={
          <button
            onClick={() => setShowAuditTrail(!showAuditTrail)}
            className="flex items-center gap-2 w-full text-left"
          >
            <FileText size={18} />
            <span>Audit Trail</span>
            <span className="text-enterprise-400 text-sm ml-2">
              ({dispute.audit_trail?.length || 0} events)
            </span>
            {showAuditTrail ? <ChevronUp size={16} className="ml-auto" /> : <ChevronDown size={16} className="ml-auto" />}
          </button>
        }
      >
        {showAuditTrail && (
          <div className="space-y-3 max-h-64 overflow-y-auto">
            {[...(dispute.audit_trail || [])].reverse().map((event, idx) => (
              <div key={idx} className="flex items-start gap-3 p-3 bg-enterprise-50 rounded-lg">
                <div className="w-2 h-2 rounded-full bg-primary-500 mt-2" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-enterprise-800 text-sm">{event.action}</span>
                    <span className="text-xs text-enterprise-500">by {event.actor}</span>
                  </div>
                  {event.detail && (
                    <p className="text-sm text-enterprise-600 mt-1 truncate">{event.detail}</p>
                  )}
                  <p className="text-xs text-enterprise-400 mt-1">
                    {formatDateTime(event.timestamp)}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
