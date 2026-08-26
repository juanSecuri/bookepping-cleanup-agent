import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { LocaleProvider } from './i18n'
import ColdStartBanner from './components/ColdStartBanner'
import Landing from './pages/Landing'
import Workspaces from './pages/Workspaces'
import Layout from './pages/app/Layout'
import Dashboard from './pages/app/Dashboard'
import Documents from './pages/app/Documents'
import Transactions from './pages/app/Transactions'
import Reconciliation from './pages/app/Reconciliation'
import Reports from './pages/app/Reports'
import ChartOfAccounts from './pages/app/ChartOfAccounts'

export default function App() {
  return (
    <LocaleProvider>
      <ColdStartBanner />
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/workspaces" element={<Workspaces />} />
          <Route path="/app/:workspaceId" element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="documents" element={<Documents />} />
            <Route path="transactions" element={<Transactions />} />
            <Route path="reconciliation" element={<Reconciliation />} />
            <Route path="reports" element={<Reports />} />
            <Route path="chart-of-accounts" element={<ChartOfAccounts />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </LocaleProvider>
  )
}
