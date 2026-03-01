import { X, AlertTriangle, AlertCircle, Info, CheckCheck } from 'lucide-react';
import { useAlerts } from '@/hooks/useAlerts';
import { formatRelativeTime, cn } from '@/utils/format';

interface AlertPanelProps {
  onClose: () => void;
}

export function AlertPanel({ onClose }: AlertPanelProps) {
  const { alerts, markAsRead, markAllAsRead, clearAlerts } = useAlerts();

  const severityIcon = {
    high: <AlertTriangle className="text-red-500" size={16} />,
    medium: <AlertCircle className="text-amber-500" size={16} />,
    low: <Info className="text-blue-500" size={16} />,
  };

  const unreadAlerts = alerts.filter((a) => !a.read);

  return (
    <div className="absolute right-0 top-full mt-2 w-96 bg-white rounded-xl border border-enterprise-200 shadow-enterprise-lg z-50">
      <div className="flex items-center justify-between px-4 py-3 border-b border-enterprise-200">
        <h3 className="font-semibold text-enterprise-800">
          Alerts
          {unreadAlerts.length > 0 && (
            <span className="ml-2 text-xs font-medium text-primary-600 bg-primary-50 px-1.5 py-0.5 rounded-full">
              {unreadAlerts.length} new
            </span>
          )}
        </h3>
        <div className="flex items-center gap-2">
          {unreadAlerts.length > 0 && (
            <button
              onClick={markAllAsRead}
              className="text-sm text-enterprise-500 hover:text-primary-600 transition-colors flex items-center gap-1"
              title="Mark all as read"
            >
              <CheckCheck size={14} />
              Mark read
            </button>
          )}
          {alerts.length > 0 && (
            <button
              onClick={clearAlerts}
              className="text-sm text-enterprise-500 hover:text-red-600 transition-colors"
            >
              Clear all
            </button>
          )}
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-enterprise-100 text-enterprise-500 transition-colors"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      <div className="max-h-96 overflow-y-auto scrollbar-thin">
        {alerts.length === 0 ? (
          <div className="px-4 py-8 text-center text-enterprise-400">
            No alerts
          </div>
        ) : (
          alerts.map((alert) => (
            <div
              key={alert.id}
              onClick={() => markAsRead(alert.id)}
              className={cn(
                'px-4 py-3 border-b border-enterprise-100 cursor-pointer transition-colors',
                'hover:bg-enterprise-50',
                !alert.read && 'bg-primary-50/50'
              )}
            >
              <div className="flex items-start gap-3">
                <div className={cn(
                  'p-1.5 rounded-lg',
                  alert.severity === 'high' ? 'bg-red-100' :
                  alert.severity === 'medium' ? 'bg-amber-100' : 'bg-blue-100'
                )}>
                  {severityIcon[alert.severity]}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-sm text-enterprise-800 truncate">
                    {alert.title}
                  </p>
                  <p className="text-sm text-enterprise-500 mt-0.5">
                    {alert.message}
                  </p>
                  <p className="text-xs text-enterprise-400 mt-1">
                    {formatRelativeTime(alert.timestamp)}
                  </p>
                </div>
                {!alert.read && (
                  <div className="w-2 h-2 rounded-full bg-primary-500 mt-1.5" />
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {alerts.length > 0 && (
        <div className="px-4 py-3 border-t border-enterprise-200 bg-enterprise-50 rounded-b-xl">
          <p className="text-center text-xs text-enterprise-500">
            {alerts.length} alert{alerts.length !== 1 ? 's' : ''} total
          </p>
        </div>
      )}
    </div>
  );
}
