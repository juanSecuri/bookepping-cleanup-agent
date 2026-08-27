import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { LocaleProvider } from './i18n'
import { ThemeProvider } from './components/ThemeProvider'
import ColdStartBanner from './components/ColdStartBanner'
import { AuthProvider } from './auth/AuthProvider'
import { RequireAuth } from './auth/RequireAuth'
import Landing from './pages/Landing'
import Login from './pages/Login'
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
    <ThemeProvider>
      <LocaleProvider>
        <AuthProvider>
          <ColdStartBanner />
          <BrowserRouter>
            <Routes>
              <Route path="/" element={<Landing />} />
              <Route path="/login" element={<Login />} />
              <Route path="/workspaces" element={<Workspaces />} />
              <Route
                path="/app/:workspaceId"
                element={
                  <RequireAuth>
                    <Layout />
                  </RequireAuth>
                }
              >
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
        </AuthProvider>
      </LocaleProvider>
    </ThemeProvider>
  )
}
