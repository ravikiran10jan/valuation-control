import { useState } from 'react';
import { Send, Paperclip, User } from 'lucide-react';
import { Button } from '../shared/Button';
import { formatRelativeTime, cn } from '@/utils/format';
import type { DisputeMessage } from '@/types';

interface DisputeThreadProps {
  disputeId: number;
  messages: DisputeMessage[];
  currentUser: { email: string; role: 'VC' | 'DESK' | 'MANAGER'; name: string };
  onMessageAdded: (message: DisputeMessage) => void;
  disabled?: boolean;
}

const ROLE_CONFIG = {
  VC: { label: 'VC Analyst', bgColor: 'bg-blue-50', borderColor: 'border-blue-200', textColor: 'text-blue-700' },
  DESK: { label: 'Desk Trader', bgColor: 'bg-purple-50', borderColor: 'border-purple-200', textColor: 'text-purple-700' },
  MANAGER: { label: 'Manager', bgColor: 'bg-amber-50', borderColor: 'border-amber-200', textColor: 'text-amber-700' },
};

export function DisputeThread({
  disputeId,
  messages,
  currentUser,
  onMessageAdded,
  disabled = false,
}: DisputeThreadProps) {
  const [newMessage, setNewMessage] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!newMessage.trim() || isSubmitting) return;
    setIsSubmitting(true);
    try {
      // In real app: const created = await api.addDisputeMessage(disputeId, { sender, sender_role, message_text });
      const mockMessage: DisputeMessage = {
        message_id: Date.now(),
        dispute_id: disputeId,
        sender: currentUser.email,
        sender_role: currentUser.role,
        message_text: newMessage.trim(),
        source: 'platform',
        timestamp: new Date().toISOString(),
      };
      onMessageAdded(mockMessage);
      setNewMessage('');
    } catch (err) {
      console.error('Failed to send message:', err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="space-y-4">
      {/* Messages */}
      <div className="space-y-3 max-h-96 overflow-y-auto">
        {messages.length === 0 ? (
          <div className="text-center py-8 text-enterprise-500 text-sm">
            No messages yet. Start the discussion...
          </div>
        ) : (
          messages.map((msg) => {
            const roleConfig = ROLE_CONFIG[msg.sender_role];
            const isOwnMessage = msg.sender === currentUser.email;

            return (
              <div
                key={msg.message_id}
                className={cn(
                  'flex gap-3',
                  isOwnMessage ? 'flex-row-reverse' : ''
                )}
              >
                <div className={cn(
                  'w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0',
                  roleConfig.bgColor,
                  'border',
                  roleConfig.borderColor
                )}>
                  <User size={14} className={roleConfig.textColor} />
                </div>
                <div
                  className={cn(
                    'flex-1 max-w-[80%] p-3 rounded-lg border',
                    isOwnMessage ? 'bg-primary-50 border-primary-200' : `${roleConfig.bgColor} ${roleConfig.borderColor}`
                  )}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className={cn('text-sm font-medium', isOwnMessage ? 'text-primary-700' : roleConfig.textColor)}>
                      {msg.sender.split('@')[0]}
                    </span>
                    <span className={cn('text-xs px-1.5 py-0.5 rounded', roleConfig.bgColor, roleConfig.textColor)}>
                      {roleConfig.label}
                    </span>
                    {msg.source === 'email' && (
                      <span className="text-xs px-1.5 py-0.5 rounded bg-enterprise-100 text-enterprise-600">
                        via Email
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-enterprise-700 whitespace-pre-wrap">{msg.message_text}</p>
                  {msg.attachments?.files && msg.attachments.files.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {msg.attachments.files.map((file, idx) => (
                        <span
                          key={idx}
                          className="inline-flex items-center gap-1 px-2 py-1 bg-white rounded border border-enterprise-200 text-xs text-enterprise-600"
                        >
                          <Paperclip size={10} />
                          {file}
                        </span>
                      ))}
                    </div>
                  )}
                  <p className="text-xs text-enterprise-400 mt-2">
                    {formatRelativeTime(msg.timestamp)}
                  </p>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* New Message Input */}
      {!disabled && (
        <div className="flex gap-3 pt-3 border-t border-enterprise-200">
          <div className={cn(
            'w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0',
            ROLE_CONFIG[currentUser.role].bgColor,
            'border',
            ROLE_CONFIG[currentUser.role].borderColor
          )}>
            <User size={14} className={ROLE_CONFIG[currentUser.role].textColor} />
          </div>
          <div className="flex-1">
            <textarea
              value={newMessage}
              onChange={(e) => setNewMessage(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={2}
              placeholder="Type your message... (Enter to send, Shift+Enter for new line)"
              className="w-full px-3 py-2 border border-enterprise-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm resize-none"
              disabled={isSubmitting}
            />
            <div className="flex justify-between items-center mt-2">
              <button className="text-enterprise-500 hover:text-enterprise-700 text-sm flex items-center gap-1">
                <Paperclip size={14} />
                Attach file
              </button>
              <Button
                size="sm"
                onClick={handleSubmit}
                disabled={!newMessage.trim() || isSubmitting}
                icon={<Send size={14} />}
              >
                {isSubmitting ? 'Sending...' : 'Send'}
              </Button>
            </div>
          </div>
        </div>
      )}

      {disabled && (
        <div className="text-center py-4 text-enterprise-500 text-sm bg-enterprise-50 rounded-lg">
          This dispute has been resolved. Discussion thread is now read-only.
        </div>
      )}
    </div>
  );
}
