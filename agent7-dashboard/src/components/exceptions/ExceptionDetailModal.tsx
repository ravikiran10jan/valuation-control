import { useState, useEffect } from 'react';
import {
  X,
  Send,
  UserCheck,
  CheckCircle2,
  Paperclip,
  AlertTriangle,
  FileWarning,
} from 'lucide-react';
import { Button, Badge } from '../shared/Button';
import { api } from '@/services/api';
import {
  formatCurrency,
  formatPercent,
  formatDate,
  formatDateTime,
  formatRelativeTime,
  cn,
} from '@/utils/format';
import type { Exception, ExceptionComment, ValuationComparison } from '@/types';

const ANALYSTS = ['Sarah Chen', 'Michael Park', 'David Liu', 'James Wong', 'Lisa Martinez'];

interface ExceptionDetailModalProps {
  exceptionId: number;
  exceptions: Exception[];
  onClose: () => void;
  onUpdate: () => void;
}

export function ExceptionDetailModal({
  exceptionId,
  exceptions,
  onClose,
  onUpdate,
}: ExceptionDetailModalProps) {
  const localExc = exceptions.find((e) => e.exception_id === exceptionId);

  const [exception, setException] = useState<(Exception & { comments?: ExceptionComment[] }) | null>(
    localExc ?? null
  );
  const [comments, setComments] = useState<ExceptionComment[]>([]);
  const [comparisonHistory, setComparisonHistory] = useState<ValuationComparison[]>([]);
  const [activeTab, setActiveTab] = useState<'details' | 'comments' | 'history'>('details');
  const [newComment, setNewComment] = useState('');
  const [commentUser, setCommentUser] = useState('Sarah Chen');
  const [submittingComment, setSubmittingComment] = useState(false);
  const [assignee, setAssignee] = useState(localExc?.assigned_to || '');
  const [resolveNotes, setResolveNotes] = useState('');
  const [showResolve, setShowResolve] = useState(false);

  useEffect(() => {
    async function fetchDetail() {
      try {
        const detail = await api.getException(exceptionId);
        setException(detail);
        setComments(detail.comments || []);
        setAssignee(detail.assigned_to || '');
      } catch {
        // Fallback to local data + mock comments
        if (localExc) {
          setException(localExc);
          setComments([
            {
              comment_id: 1,
              exception_id: exceptionId,
              user_name: 'Sarah Chen',
              comment_text: 'Investigating desk mark. Requested updated quote from trader.',
              timestamp: '2025-02-14T10:30:00Z',
            },
            {
              comment_id: 2,
              exception_id: exceptionId,
              user_name: 'David Liu',
              comment_text: 'Trader confirmed stale mark due to illiquid market. Will update EOD.',
              timestamp: '2025-02-14T14:15:00Z',
            },
          ]);
        }
      }

      try {
        if (localExc) {
          const history = await api.getComparisonHistory(localExc.position_id);
          setComparisonHistory(history);
        }
      } catch {
        // Mock comparison history
        setComparisonHistory([
          {
            comparison_id: 1,
            position_id: localExc?.position_id || 0,
            desk_mark: 32.45,
            vc_fair_value: 35.12,
            difference: -2.67,
            difference_pct: -8.22,
            status: 'RED',
            comparison_date: '2025-02-14',
            created_at: '2025-02-14T16:10:00Z',
          },
          {
            comparison_id: 2,
            position_id: localExc?.position_id || 0,
            desk_mark: 32.10,
            vc_fair_value: 34.89,
            difference: -2.79,
            difference_pct: -8.69,
            status: 'RED',
            comparison_date: '2025-02-13',
            created_at: '2025-02-13T16:10:00Z',
          },
          {
            comparison_id: 3,
            position_id: localExc?.position_id || 0,
            desk_mark: 33.50,
            vc_fair_value: 34.20,
            difference: -0.70,
            difference_pct: -2.09,
            status: 'GREEN',
            comparison_date: '2025-02-12',
            created_at: '2025-02-12T16:10:00Z',
          },
        ]);
      }
    }
    fetchDetail();
  }, [exceptionId]);

  const handleAddComment = async () => {
    if (!newComment.trim()) return;
    setSubmittingComment(true);
    try {
      const comment = await api.addComment(exceptionId, commentUser, newComment);
      setComments((prev) => [...prev, comment]);
    } catch {
      // Fallback: add locally
      setComments((prev) => [
        ...prev,
        {
          comment_id: Date.now(),
          exception_id: exceptionId,
          user_name: commentUser,
          comment_text: newComment,
          timestamp: new Date().toISOString(),
        },
      ]);
    }
    setNewComment('');
    setSubmittingComment(false);
  };

  const handleAssign = async () => {
    if (!assignee) return;
    try {
      const updated = await api.assignException(exceptionId, assignee);
      setException(updated);
      onUpdate();
    } catch {
      if (exception) {
        setException({
          ...exception,
          assigned_to: assignee,
          status: exception.status === 'OPEN' ? 'INVESTIGATING' : exception.status,
        });
      }
    }
  };

  const handleResolve = async () => {
    if (!resolveNotes.trim()) return;
    try {
      const updated = await api.resolveException(exceptionId, resolveNotes, commentUser);
      setException(updated);
      onUpdate();
      setShowResolve(false);
    } catch {
      if (exception) {
        setException({
          ...exception,
          status: 'RESOLVED',
          resolution_notes: resolveNotes,
          resolved_date: new Date().toISOString().split('T')[0],
        });
        onUpdate();
        setShowResolve(false);
      }
    }
  };

  if (!exception) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
        <div className="bg-white rounded-xl p-8 text-enterprise-500">Loading...</div>
      </div>
    );
  }

  const escalationLabels = ['', 'Analyst', 'Manager', 'Committee'];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="bg-white rounded-xl shadow-2xl w-full max-w-3xl max-h-[90vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-enterprise-200 bg-enterprise-50">
          <div className="flex items-center gap-3">
            {exception.severity === 'RED' ? (
              <FileWarning size={24} className="text-red-600" />
            ) : (
              <AlertTriangle size={24} className="text-amber-600" />
            )}
            <div>
              <h2 className="text-lg font-semibold text-enterprise-800">
                Exception #{exception.exception_id}
              </h2>
              <p className="text-sm text-enterprise-500">
                Position #{exception.position_id}
                {(exception as Exception & { product?: string }).product &&
                  ` - ${(exception as Exception & { product?: string }).product}`}
              </p>
            </div>
            <Badge variant={exception.severity === 'RED' ? 'red' : 'amber'} size="sm">
              {exception.severity}
            </Badge>
            <Badge
              variant={
                exception.status === 'RESOLVED'
                  ? 'green'
                  : exception.status === 'ESCALATED'
                  ? 'red'
                  : exception.status === 'INVESTIGATING'
                  ? 'blue'
                  : 'amber'
              }
              size="sm"
            >
              {exception.status}
            </Badge>
          </div>
          <button onClick={onClose} className="text-enterprise-400 hover:text-enterprise-600">
            <X size={24} />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-enterprise-200 bg-white">
          {(['details', 'comments', 'history'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={cn(
                'px-5 py-3 text-sm font-medium transition-colors relative',
                activeTab === tab
                  ? 'text-primary-600'
                  : 'text-enterprise-500 hover:text-enterprise-700'
              )}
            >
              {tab === 'details' && 'Details'}
              {tab === 'comments' && `Comments (${comments.length})`}
              {tab === 'history' && 'Comparison History'}
              {activeTab === tab && (
                <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary-600 rounded-full" />
              )}
            </button>
          ))}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-6">
          {/* Details Tab */}
          {activeTab === 'details' && (
            <div className="space-y-6">
              {/* Key Metrics */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="p-3 bg-enterprise-50 rounded-lg">
                  <p className="text-xs text-enterprise-500">Difference</p>
                  <p className={cn('text-lg font-bold', exception.difference < 0 ? 'text-red-600' : 'text-enterprise-800')}>
                    {formatCurrency(exception.difference)}
                  </p>
                </div>
                <div className="p-3 bg-enterprise-50 rounded-lg">
                  <p className="text-xs text-enterprise-500">Difference %</p>
                  <p className={cn('text-lg font-bold', exception.severity === 'RED' ? 'text-red-600' : 'text-amber-600')}>
                    {formatPercent(exception.difference_pct)}
                  </p>
                </div>
                <div className="p-3 bg-enterprise-50 rounded-lg">
                  <p className="text-xs text-enterprise-500">Days Open</p>
                  <p className={cn('text-lg font-bold', exception.days_open > 5 ? 'text-red-600' : 'text-enterprise-800')}>
                    {exception.days_open}
                  </p>
                </div>
                <div className="p-3 bg-enterprise-50 rounded-lg">
                  <p className="text-xs text-enterprise-500">Escalation Level</p>
                  <p className="text-lg font-bold text-enterprise-800">
                    {escalationLabels[exception.escalation_level]}
                  </p>
                </div>
              </div>

              {/* Info Grid */}
              <div className="grid grid-cols-2 gap-x-8 gap-y-3 text-sm">
                <div>
                  <span className="text-enterprise-500">Created:</span>{' '}
                  <span className="text-enterprise-700 font-medium">{formatDate(exception.created_date)}</span>
                </div>
                <div>
                  <span className="text-enterprise-500">Updated:</span>{' '}
                  <span className="text-enterprise-700 font-medium">{formatDateTime(exception.updated_at)}</span>
                </div>
                <div>
                  <span className="text-enterprise-500">Assigned To:</span>{' '}
                  <span className="text-enterprise-700 font-medium">{exception.assigned_to || 'Unassigned'}</span>
                </div>
                {exception.resolved_date && (
                  <div>
                    <span className="text-enterprise-500">Resolved:</span>{' '}
                    <span className="text-enterprise-700 font-medium">{formatDate(exception.resolved_date)}</span>
                  </div>
                )}
              </div>

              {exception.resolution_notes && (
                <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
                  <p className="text-xs font-medium text-green-700 mb-1">Resolution Notes</p>
                  <p className="text-sm text-green-800">{exception.resolution_notes}</p>
                </div>
              )}

              {/* Assignment Workflow */}
              {exception.status !== 'RESOLVED' && (
                <div className="border border-enterprise-200 rounded-lg p-4 space-y-3">
                  <h4 className="text-sm font-semibold text-enterprise-700">Assignment</h4>
                  <div className="flex items-center gap-2">
                    <select
                      value={assignee}
                      onChange={(e) => setAssignee(e.target.value)}
                      className="flex-1 rounded-lg border border-enterprise-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                    >
                      <option value="">Select analyst...</option>
                      {ANALYSTS.map((a) => (
                        <option key={a} value={a}>{a}</option>
                      ))}
                    </select>
                    <Button
                      size="sm"
                      icon={<UserCheck size={14} />}
                      onClick={handleAssign}
                      disabled={!assignee || assignee === exception.assigned_to}
                    >
                      Assign
                    </Button>
                  </div>
                </div>
              )}

              {/* Resolve */}
              {exception.status !== 'RESOLVED' && (
                <div className="border border-enterprise-200 rounded-lg p-4 space-y-3">
                  {!showResolve ? (
                    <Button
                      variant="primary"
                      size="sm"
                      icon={<CheckCircle2 size={14} />}
                      onClick={() => setShowResolve(true)}
                    >
                      Resolve Exception
                    </Button>
                  ) : (
                    <>
                      <h4 className="text-sm font-semibold text-enterprise-700">Resolve Exception</h4>
                      <textarea
                        value={resolveNotes}
                        onChange={(e) => setResolveNotes(e.target.value)}
                        placeholder="Enter resolution notes (required)..."
                        rows={3}
                        className="w-full rounded-lg border border-enterprise-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                      />
                      <div className="flex gap-2">
                        <Button size="sm" onClick={handleResolve} disabled={!resolveNotes.trim()}>
                          Confirm Resolve
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => setShowResolve(false)}>
                          Cancel
                        </Button>
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Comments Tab */}
          {activeTab === 'comments' && (
            <div className="space-y-4">
              {comments.length === 0 && (
                <p className="text-sm text-enterprise-400 text-center py-8">
                  No comments yet. Add the first comment below.
                </p>
              )}
              {comments.map((comment) => (
                <div
                  key={comment.comment_id}
                  className={cn(
                    'p-4 rounded-lg border',
                    comment.user_name === 'SYSTEM'
                      ? 'bg-enterprise-50 border-enterprise-200'
                      : 'bg-white border-enterprise-200'
                  )}
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-enterprise-700">
                        {comment.user_name}
                      </span>
                      {comment.user_name === 'SYSTEM' && (
                        <Badge variant="default" size="sm">System</Badge>
                      )}
                    </div>
                    <span className="text-xs text-enterprise-400">
                      {formatRelativeTime(comment.timestamp)}
                    </span>
                  </div>
                  <p className="text-sm text-enterprise-600">{comment.comment_text}</p>
                  {comment.attachments?.files && comment.attachments.files.length > 0 && (
                    <div className="mt-2 flex items-center gap-2">
                      <Paperclip size={14} className="text-enterprise-400" />
                      {comment.attachments.files.map((file) => (
                        <span key={file} className="text-xs text-primary-600 underline cursor-pointer">
                          {file}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}

              {/* Add Comment */}
              <div className="border border-enterprise-200 rounded-lg p-4 space-y-3">
                <div className="flex items-center gap-2">
                  <label className="text-xs font-medium text-enterprise-600">As:</label>
                  <select
                    value={commentUser}
                    onChange={(e) => setCommentUser(e.target.value)}
                    className="rounded-lg border border-enterprise-300 bg-white px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-primary-500"
                  >
                    {ANALYSTS.map((a) => (
                      <option key={a} value={a}>{a}</option>
                    ))}
                    <option value="Desk Trader">Desk Trader</option>
                  </select>
                </div>
                <textarea
                  value={newComment}
                  onChange={(e) => setNewComment(e.target.value)}
                  placeholder="Add a comment or dispute..."
                  rows={3}
                  className="w-full rounded-lg border border-enterprise-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
                <div className="flex items-center justify-between">
                  <Button variant="ghost" size="sm" icon={<Paperclip size={14} />}>
                    Attach File
                  </Button>
                  <Button
                    size="sm"
                    icon={<Send size={14} />}
                    onClick={handleAddComment}
                    disabled={!newComment.trim() || submittingComment}
                  >
                    {submittingComment ? 'Sending...' : 'Send'}
                  </Button>
                </div>
              </div>
            </div>
          )}

          {/* History Tab */}
          {activeTab === 'history' && (
            <div className="space-y-3">
              {comparisonHistory.length === 0 && (
                <p className="text-sm text-enterprise-400 text-center py-8">
                  No comparison history available.
                </p>
              )}
              {comparisonHistory.map((comp) => (
                <div
                  key={comp.comparison_id}
                  className={cn(
                    'p-4 rounded-lg border',
                    comp.status === 'RED'
                      ? 'bg-red-50 border-red-200'
                      : comp.status === 'AMBER'
                      ? 'bg-amber-50 border-amber-200'
                      : 'bg-green-50 border-green-200'
                  )}
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Badge
                        variant={comp.status === 'RED' ? 'red' : comp.status === 'AMBER' ? 'amber' : 'green'}
                        size="sm"
                      >
                        {comp.status}
                      </Badge>
                      <span className="text-sm font-medium text-enterprise-700">
                        {formatDate(comp.comparison_date)}
                      </span>
                    </div>
                    <span className={cn(
                      'text-sm font-bold',
                      comp.status === 'RED' ? 'text-red-600' : comp.status === 'AMBER' ? 'text-amber-600' : 'text-green-600'
                    )}>
                      {formatPercent(comp.difference_pct)}
                    </span>
                  </div>
                  <div className="grid grid-cols-3 gap-4 text-xs text-enterprise-600">
                    <div>
                      <span className="text-enterprise-400">Desk Mark:</span>{' '}
                      {formatCurrency(comp.desk_mark)}
                    </div>
                    <div>
                      <span className="text-enterprise-400">VC FV:</span>{' '}
                      {formatCurrency(comp.vc_fair_value)}
                    </div>
                    <div>
                      <span className="text-enterprise-400">Diff:</span>{' '}
                      {formatCurrency(comp.difference)}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
