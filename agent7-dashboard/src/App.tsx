import { Routes, Route } from 'react-router-dom';
import { Layout } from './components/shared/Layout';
import { ExecutiveDashboard } from './components/dashboard/ExecutiveDashboard';
import { AnalystWorkbench } from './components/workbench/AnalystWorkbench';
import { ExceptionDashboard } from './components/exceptions/ExceptionDashboard';
import { PositionDetail } from './components/positions/PositionDetail';
import { PositionsPage } from './components/positions/PositionsPage';
import { ReportingPortal } from './components/reports/ReportingPortal';
import { IPVRunDashboard } from './components/ipv/IPVRunDashboard';
import { PositionDeepDive } from './components/ipv/PositionDeepDive';
import { ReserveWaterfall } from './components/reserves/ReserveWaterfall';
import { CapitalAdequacyView } from './components/capital/CapitalAdequacyView';
import { FVHierarchyView } from './components/hierarchy/FVHierarchyView';
import { ValidationDashboard } from './components/validation/ValidationDashboard';
import { SimulatorPage } from './components/simulator/SimulatorPage';
import { ApplicabilityPage } from './components/simulator/ApplicabilityPage';
import { Day1PnLDashboard } from './components/day1pnl/Day1PnLDashboard';
import { SettingsPage } from './components/settings/SettingsPage';
import { AlertsProvider } from './hooks/useAlerts';

export default function App() {
  return (
    <AlertsProvider>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<ExecutiveDashboard />} />
          <Route path="workbench" element={<AnalystWorkbench />} />
          <Route path="exceptions" element={<ExceptionDashboard />} />
          <Route path="positions" element={<PositionsPage />} />
          <Route path="positions/:positionId" element={<PositionDetail />} />
          <Route path="reports" element={<ReportingPortal />} />
          <Route path="ipv" element={<IPVRunDashboard />} />
          <Route path="positions/:id/deep-dive" element={<PositionDeepDive />} />
          <Route path="reserves" element={<ReserveWaterfall />} />
          <Route path="capital" element={<CapitalAdequacyView />} />
          <Route path="hierarchy" element={<FVHierarchyView />} />
          <Route path="validation" element={<ValidationDashboard />} />
          <Route path="simulator" element={<SimulatorPage />} />
          <Route path="applicability" element={<ApplicabilityPage />} />
          <Route path="day1-pnl" element={<Day1PnLDashboard />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </AlertsProvider>
  );
}
