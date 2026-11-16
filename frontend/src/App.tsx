import type { ReactElement } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import Layout from "./components/Layout";
import AlertsPage from "./pages/AlertsPage";
import ApprovalsPage from "./pages/ApprovalsPage";
import AuditPage from "./pages/AuditPage";
import BillsPage from "./pages/BillsPage";
import DashboardPage from "./pages/DashboardPage";
import LoginPage from "./pages/LoginPage";
import NewBillPage from "./pages/NewBillPage";
import ReportsPage from "./pages/ReportsPage";
import SettingsPage from "./pages/SettingsPage";
import StockPage from "./pages/StockPage";
import SyncPage from "./pages/SyncPage";
import UsersPage from "./pages/UsersPage";

function Guard({ perms, children }: { perms: string[]; children: ReactElement }) {
  const { can } = useAuth();
  return perms.some(can) ? children : <Navigate to="/" replace />;
}

export default function App() {
  const { status } = useAuth();
  if (status === "loading") return <div className="grid min-h-screen place-items-center text-muted">Loading…</div>;
  if (status === "anonymous") return <LoginPage />;
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<DashboardPage />} />
        <Route path="bills/new" element={<Guard perms={["bill.create"]}><NewBillPage /></Guard>} />
        <Route path="bills" element={<Guard perms={["bill.view"]}><BillsPage /></Guard>} />
        <Route path="stock" element={<Guard perms={["stock.view"]}><StockPage /></Guard>} />
        <Route path="approvals" element={<Guard perms={["stock.request", "stock.approve"]}><ApprovalsPage /></Guard>} />
        <Route path="alerts" element={<Guard perms={["stock.view"]}><AlertsPage /></Guard>} />
        <Route path="reports" element={<Guard perms={["reports.view"]}><ReportsPage /></Guard>} />
        <Route path="sync" element={<Guard perms={["sync.view"]}><SyncPage /></Guard>} />
        <Route path="audit" element={<Guard perms={["audit.view"]}><AuditPage /></Guard>} />
        <Route path="users" element={<Guard perms={["users.manage"]}><UsersPage /></Guard>} />
        <Route path="settings" element={<Guard perms={["settings.manage"]}><SettingsPage /></Guard>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
