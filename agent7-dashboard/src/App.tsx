import { Routes, Route } from 'react-router-dom';
import { Layout } from './components/shared/Layout';
import { ExecutiveDashboard } from './components/dashboard/ExecutiveDashboard';
import { AnalystWorkbench } from './components/workbench/AnalystWorkbench';
import { ExceptionDashboard } from './components/exceptions/ExceptionDashboard';
import { PositionDetail } from './components/positions/PositionDetail';
import { ReportingPortal } from './components/reports/ReportingPortal';
import { AlertsProvider } from './hooks/useAlerts';

export default function App() {
  return (
    <AlertsProvider>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<ExecutiveDashboard />} />
          <Route path="workbench" element={<AnalystWorkbench />} />
          <Route path="exceptions" element={<ExceptionDashboard />} />
          <Route path="positions/:positionId" element={<PositionDetail />} />
          <Route path="reports" element={<ReportingPortal />} />
        </Route>
      </Routes>
    </AlertsProvider>
  );
}
