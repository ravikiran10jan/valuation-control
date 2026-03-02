import { Routes, Route } from 'react-router-dom';
import { Layout } from './components/shared/Layout';
import { ExecutiveDashboard } from './components/dashboard/ExecutiveDashboard';
import { AnalystWorkbench } from './components/workbench/AnalystWorkbench';
import { ExceptionDashboard } from './components/exceptions/ExceptionDashboard';
import { PositionDetail } from './components/positions/PositionDetail';
import { ReportingPortal } from './components/reports/ReportingPortal';
import { IPVRunDashboard } from './components/ipv/IPVRunDashboard';
import { PositionDeepDive } from './components/ipv/PositionDeepDive';
import { ReserveWaterfall } from './components/reserves/ReserveWaterfall';
import { CapitalAdequacyView } from './components/capital/CapitalAdequacyView';
import { FVHierarchyView } from './components/hierarchy/FVHierarchyView';
import { ValidationDashboard } from './components/validation/ValidationDashboard';
import { SimulatorPage } from './components/simulator/SimulatorPage';
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
          <Route path="ipv" element={<IPVRunDashboard />} />
          <Route path="positions/:id/deep-dive" element={<PositionDeepDive />} />
          <Route path="reserves" element={<ReserveWaterfall />} />
          <Route path="capital" element={<CapitalAdequacyView />} />
          <Route path="hierarchy" element={<FVHierarchyView />} />
          <Route path="validation" element={<ValidationDashboard />} />
          <Route path="simulator" element={<SimulatorPage />} />
        </Route>
      </Routes>
    </AlertsProvider>
  );
}
