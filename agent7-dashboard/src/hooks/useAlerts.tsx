import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from 'react';
import type { Alert } from '@/types';
import { wsService } from '@/services/websocket';

interface AlertsContextType {
  alerts: Alert[];
  unreadCount: number;
  addAlert: (alert: Alert) => void;
  markAsRead: (id: string) => void;
  markAllAsRead: () => void;
  clearAlerts: () => void;
}

const AlertsContext = createContext<AlertsContextType | null>(null);

const initialAlerts: Alert[] = [
  {
    id: 'seed-1',
    severity: 'high',
    title: 'New RED exception: EUR/USD Barrier',
    message: 'Difference: -28%',
    timestamp: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
    read: false,
  },
  {
    id: 'seed-2',
    severity: 'medium',
    title: 'Desk adjusted mark on Bermudan Swaption',
    message: 'Mark changed from $95M to $91M',
    timestamp: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
    read: false,
  },
  {
    id: 'seed-3',
    severity: 'medium',
    title: 'FVA reserve recalculation complete',
    message: 'Total FVA increased by $2M across Rates book',
    timestamp: new Date(Date.now() - 4 * 60 * 60 * 1000).toISOString(),
    read: false,
  },
  {
    id: 'seed-4',
    severity: 'low',
    title: 'Pillar 3 report generated successfully',
    message: 'Report ready for download',
    timestamp: new Date(Date.now() - 5 * 60 * 60 * 1000).toISOString(),
    read: true,
  },
];

export function AlertsProvider({ children }: { children: ReactNode }) {
  const [alerts, setAlerts] = useState<Alert[]>(initialAlerts);

  const addAlert = useCallback((alert: Alert) => {
    setAlerts((prev) => {
      if (prev.some((a) => a.id === alert.id)) return prev;
      return [alert, ...prev].slice(0, 100);
    });
  }, []);

  const markAsRead = useCallback((id: string) => {
    setAlerts((prev) =>
      prev.map((alert) =>
        alert.id === id ? { ...alert, read: true } : alert
      )
    );
  }, []);

  const markAllAsRead = useCallback(() => {
    setAlerts((prev) => prev.map((alert) => ({ ...alert, read: true })));
  }, []);

  const clearAlerts = useCallback(() => {
    setAlerts([]);
  }, []);

  useEffect(() => {
    wsService.connect();
    const unsubscribe = wsService.subscribe(addAlert);

    return () => {
      unsubscribe();
      wsService.disconnect();
    };
  }, [addAlert]);

  const unreadCount = alerts.filter((a) => !a.read).length;

  return (
    <AlertsContext.Provider
      value={{ alerts, unreadCount, addAlert, markAsRead, markAllAsRead, clearAlerts }}
    >
      {children}
    </AlertsContext.Provider>
  );
}

export function useAlerts() {
  const context = useContext(AlertsContext);
  if (!context) {
    throw new Error('useAlerts must be used within AlertsProvider');
  }
  return context;
}
