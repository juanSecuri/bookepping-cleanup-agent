const API_BASE = import.meta.env.VITE_API_URL || ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...init?.headers,
    },
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(text || `Request failed: ${res.status}`)
  }
  if (res.status === 204) return undefined as T
  const contentType = res.headers.get('content-type') || ''
  if (contentType.includes('application/json')) return res.json() as Promise<T>
  return undefined as T
}

export type Workspace = {
  id: string
  name: string
  description?: string | null
  legal_name?: string | null
  created_at?: string
}

export type WorkspaceStats = {
  documents?: number
  pending_transactions?: number
  verified_transactions?: number
  rejected_transactions?: number
  unmatched_movements?: number
  periods_open?: number
  totalIncome?: number
  totalExpenses?: number
  netIncome?: number
  [key: string]: unknown
}

export type DriveStatus = {
  configured?: boolean
  default_folder_id?: string
  default_folder_name?: string
  [key: string]: unknown
}

export type DriveBrowseNode = {
  id: string
  name: string
  mime_type?: string
  path?: string
  is_folder?: boolean
  size?: number | null
  children?: DriveBrowseNode[]
  [key: string]: unknown
}

export type DriveSyncResult = {
  discovered?: number
  imported?: number
  skipped?: number
  failed?: unknown[]
  [key: string]: unknown
}

export const DEFAULT_DRIVE_FOLDER_ID = '1db-aXczr9hHkv207U5gjEDmUfitN8MmT'
export const DEFAULT_DRIVE_FOLDER_NAME = 'My Xcell Network CORP'

export type Document = {
  id: string
  workspace_id?: string
  tenant_id?: string
  filename?: string
  name?: string
  status?: string
  created_at?: string
  [key: string]: unknown
}

export type Transaction = {
  id: string
  tenant_id?: string
  workspace_id?: string
  description?: string
  amount?: number
  currency?: string
  status?: string
  category?: string
  account_code?: string
  chart_of_accounts_code?: string
  account_name?: string
  date?: string
  transaction_date?: string
  vendor?: string
  vendor_name?: string
  type?: string
  transaction_type?: string
  category_confidence?: number
  [key: string]: unknown
}

export type TransactionCounts = {
  pending?: number
  verified?: number
  rejected?: number
  all?: number
  [key: string]: number | undefined
}

export type ChartAccount = {
  id: string
  code?: string
  name?: string
  category?: string
  account_type?: string
  subcategory?: string
  description?: string | null
  is_active?: boolean
  workspace_id?: string
  [key: string]: unknown
}

export type Movement = {
  id: string
  description?: string
  amount?: number
  debit?: number
  credit?: number
  date?: string
  bank?: string
  bank_name?: string
  matched?: boolean
  transaction_id?: string | null
  [key: string]: unknown
}

export type Period = {
  period: string
  status?: string
  closed_at?: string | null
  transaction_count?: number
  verified_count?: number
  source?: string
  [key: string]: unknown
}

export type PnLLineItem = {
  code?: string
  name?: string
  amount?: number
  txCount?: number
  byMonth?: Record<string, number>
  debits?: number
  credits?: number
  opening?: number
  closing?: number
}

export type PnLReport = {
  revenue?: number
  expenses?: number
  cogs?: number
  operatingExpenses?: number
  net_income?: number
  totalRevenue?: number
  totalExpenses?: number
  totalCogs?: number
  netIncome?: number
  revenueItems?: PnLLineItem[]
  cogsItems?: PnLLineItem[]
  expenseItems?: PnLLineItem[]
  months?: string[]
  granularity?: string
  lines?: Array<{ account?: string; amount?: number; category?: string }>
  [key: string]: unknown
}

export type BalanceLine = {
  code?: string
  name?: string
  amount?: number
  txCount?: number
  debits?: number
  credits?: number
  opening?: number
  closing?: number
}

export type StatementsBundle = {
  period_label?: string
  transaction_count?: number
  pending_count?: number
  engine?: string
  fiscal_year?: string
  month?: number
  granularity?: string
  pnl?: PnLReport
  balance_sheet?: {
    assets?: BalanceLine[]
    liabilities?: BalanceLine[]
    equity?: BalanceLine[]
    totalAssets?: number
    totalLiabilities?: number
    totalEquity?: number
    imbalance?: number
    balanced?: boolean
    equation?: string
    note?: string
  }
  cash_flow?: {
    operating?: { inflows?: number; outflows?: number; net?: number }
    investing?: { inflows?: number; outflows?: number; net?: number }
    financing?: { inflows?: number; outflows?: number; net?: number; note?: string }
    netChange?: number
    note?: string
  }
  cash_flow_monthly?: Array<{ period?: string; inflows?: number; outflows?: number; net?: number }>
  cash_flow_annual?: Array<{ period?: string; inflows?: number; outflows?: number; net?: number }>
  cash_flow_detail?: {
    operating?: PnLLineItem[]
    investing?: PnLLineItem[]
    financing?: PnLLineItem[]
    operatingSubtotal?: number
    investingSubtotal?: number
    financingSubtotal?: number
    netTotal?: number
  }
  balance_chain_alerts?: Array<{
    statement_month?: string
    bank_account_number?: string
    bank_name?: string
    chain_ok?: boolean | null
    paused?: boolean
    chain_delta?: number | null
    alert_message?: string | null
    opening_balance?: number | null
    closing_balance?: number | null
  }>
}

export const api = {
  listWorkspaces: () => request<Workspace[]>('/api/workspaces'),
  queueStatus: () => request<{ status: string; queue: Record<string, number> }>('/api/queue/status'),
  health: () => request<{ status: string; queue?: Record<string, number> }>('/health'),
  createWorkspace: (body: { name: string; description?: string }) =>
    request<Workspace>('/api/workspaces', { method: 'POST', body: JSON.stringify(body) }),
  deleteWorkspace: (id: string) =>
    request<{ deleted: boolean; id: string; name?: string }>(`/api/workspaces/${id}`, {
      method: 'DELETE',
    }),
  getWorkspace: (id: string) => request<Workspace>(`/api/workspaces/${id}`),
  getWorkspaceStats: (id: string) => request<WorkspaceStats>(`/api/workspaces/${id}/stats`),

  listDocuments: (params?: { workspace_id?: string; tenant_id?: string }) => {
    const q = new URLSearchParams()
    if (params?.workspace_id) q.set('workspace_id', params.workspace_id)
    if (params?.tenant_id) q.set('tenant_id', params.tenant_id)
    const qs = q.toString()
    return request<Document[]>(`/api/documents${qs ? `?${qs}` : ''}`)
  },
  createDocument: (body: Record<string, unknown>) =>
    request<Document>('/api/documents', { method: 'POST', body: JSON.stringify(body) }),
  uploadDocument: (form: FormData) =>
    request<Document>('/api/documents/upload', { method: 'POST', body: form }),
  documentFileUrl: (document_id: string, workspace_id: string) =>
    `${API_BASE}/api/documents/${encodeURIComponent(document_id)}/file?workspace_id=${encodeURIComponent(workspace_id)}`,

  listTransactions: (params: { tenant_id: string; status?: string; suspense?: boolean }) => {
    const q = new URLSearchParams({ tenant_id: params.tenant_id })
    if (params.status) q.set('status', params.status)
    if (params.suspense) q.set('suspense', 'true')
    return request<Transaction[]>(`/api/transactions?${q}`)
  },
  transactionCounts: (tenant_id: string) =>
    request<TransactionCounts>(`/api/transactions/counts?tenant_id=${encodeURIComponent(tenant_id)}`),
  listAccountRules: (workspace_id: string) =>
    request<Array<Record<string, unknown>>>(
      `/api/account-rules?workspace_id=${encodeURIComponent(workspace_id)}`,
    ),
  seedAccountRules: (workspace_id: string) =>
    request<{ rules?: number }>('/api/account-rules/seed', {
      method: 'POST',
      body: JSON.stringify({ workspace_id }),
    }),
  approveTransaction: (id: string) =>
    request<Transaction>(`/api/transactions/${id}/approve`, { method: 'POST' }),
  rejectTransaction: (id: string, reason?: string) =>
    request<Transaction>(`/api/transactions/${id}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
  reclassifyTransaction: (id: string, body: Record<string, unknown>) =>
    request<Transaction>(`/api/transactions/${id}/reclassify`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  bulkApprove: (ids: string[]) =>
    request<{ updated?: number }>('/api/transactions/bulk-approve', {
      method: 'POST',
      body: JSON.stringify({ ids }),
    }),
  bulkReject: (ids: string[], reason?: string) =>
    request<{ updated?: number }>('/api/transactions/bulk-reject', {
      method: 'POST',
      body: JSON.stringify({ ids, reason }),
    }),

  chartOfAccounts: (workspace_id: string) =>
    request<ChartAccount[]>(`/api/chart-of-accounts?workspace_id=${encodeURIComponent(workspace_id)}`),
  seedChartOfAccounts: (workspace_id: string) =>
    request<{ seeded?: number; accounts?: ChartAccount[] }>('/api/chart-of-accounts/seed', {
      method: 'POST',
      body: JSON.stringify({ workspace_id }),
    }),

  listMovements: (params?: { workspace_id?: string; tenant_id?: string }) => {
    const q = new URLSearchParams()
    if (params?.workspace_id) q.set('workspace_id', params.workspace_id)
    if (params?.tenant_id) q.set('tenant_id', params.tenant_id)
    const qs = q.toString()
    return request<Movement[]>(`/api/movements${qs ? `?${qs}` : ''}`)
  },
  matchMovement: (id: string, transaction_id: string) =>
    request<Movement>(`/api/movements/${id}/match`, {
      method: 'POST',
      body: JSON.stringify({ transaction_id }),
    }),
  unmatchMovement: (id: string) =>
    request<Movement>(`/api/movements/${id}/unmatch`, { method: 'POST' }),

  uploadStatement: (form: FormData) =>
    request<unknown>('/api/statements', { method: 'POST', body: form }),

  listPeriods: (params?: { workspace_id?: string }) => {
    const q = new URLSearchParams()
    if (params?.workspace_id) q.set('workspace_id', params.workspace_id)
    const qs = q.toString()
    return request<Period[]>(`/api/periods${qs ? `?${qs}` : ''}`)
  },
  closePeriod: (period: string, workspace_id: string) =>
    request<Period>(`/api/periods/${encodeURIComponent(period)}/close`, {
      method: 'POST',
      body: JSON.stringify({ workspace_id }),
    }),
  reopenPeriod: (period: string, workspace_id: string) =>
    request<Period>(`/api/periods/${encodeURIComponent(period)}/reopen`, {
      method: 'POST',
      body: JSON.stringify({ workspace_id }),
    }),

  pnlReport: (params: {
    workspace_id: string
    date_from?: string
    date_to?: string
    fiscal_year?: string
    month?: number
    period?: string
  }) => {
    const q = new URLSearchParams({ workspace_id: params.workspace_id })
    if (params.date_from) q.set('date_from', params.date_from)
    if (params.date_to) q.set('date_to', params.date_to)
    if (params.fiscal_year) q.set('fiscal_year', params.fiscal_year)
    if (params.month != null) q.set('month', String(params.month))
    if (params.period) q.set('period', params.period)
    return request<PnLReport>(`/api/reports/pnl?${q}`)
  },
  availableYears: (workspace_id: string) =>
    request<{
      years: string[]
      verified_years?: string[]
      default_year?: string | null
    }>(`/api/available-years?workspace_id=${encodeURIComponent(workspace_id)}`),
  financialStatements: (params: {
    workspace_id: string
    period?: string
    date_from?: string
    date_to?: string
    fiscal_year?: string
    month?: number
  }) => {
    const q = new URLSearchParams({ workspace_id: params.workspace_id })
    if (params.period) q.set('period', params.period)
    if (params.date_from) q.set('date_from', params.date_from)
    if (params.date_to) q.set('date_to', params.date_to)
    if (params.fiscal_year) q.set('fiscal_year', params.fiscal_year)
    if (params.month != null) q.set('month', String(params.month))
    return request<StatementsBundle>(`/api/reports/statements?${q}`)
  },

  balanceChain: (workspace_id: string) =>
    request<{
      workspace_id: string
      periods: Array<Record<string, unknown>>
      alerts: Array<Record<string, unknown>>
      alert_count: number
    }>(`/api/reports/balance-chain?workspace_id=${encodeURIComponent(workspace_id)}`),

  ackBalanceChain: (body: {
    workspace_id: string
    statement_month: string
    bank_account_number: string
  }) =>
    request<{ ok: boolean; period?: Record<string, unknown> }>(
      '/api/reports/balance-chain/ack',
      { method: 'POST', body: JSON.stringify(body) },
    ),


  listFiscalYears: (workspace_id: string) =>
    request<{ years: Array<Record<string, unknown>> }>(
      `/api/fiscal-years?workspace_id=${encodeURIComponent(workspace_id)}`,
    ),
  closeFiscalYear: (fiscal_year: string, body: {
    workspace_id: string
    notes?: string
    allow_suspense?: boolean
  }) =>
    request<{
      fiscal_year: string
      status: string
      net_income: number
      total_revenue: number
      total_expenses: number
      retained_earnings_after: number
      transaction_count: number
      note?: string
    }>(`/api/fiscal-years/${encodeURIComponent(fiscal_year)}/close`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  reopenFiscalYear: (fiscal_year: string, workspace_id: string) =>
    request<{ fiscal_year: string; status?: string }>(
      `/api/fiscal-years/${encodeURIComponent(fiscal_year)}/reopen`,
      { method: 'POST', body: JSON.stringify({ workspace_id }) },
    ),

  exportStatementsUrl: (params: {
    workspace_id: string
    period?: string
    date_from?: string
    date_to?: string
    fiscal_year?: string
    month?: number
  }) => {
    const q = new URLSearchParams({ workspace_id: params.workspace_id })
    if (params.period) q.set('period', params.period)
    if (params.date_from) q.set('date_from', params.date_from)
    if (params.date_to) q.set('date_to', params.date_to)
    if (params.fiscal_year) q.set('fiscal_year', params.fiscal_year)
    if (params.month != null) q.set('month', String(params.month))
    return `${API_BASE}/api/reports/export.xlsx?${q}`
  },

  sqlReportViews: (params: { workspace_id: string; period?: string }) => {
    const q = new URLSearchParams({ workspace_id: params.workspace_id })
    if (params.period) q.set('period', params.period)
    return request<{
      pnl_by_month?: Array<Record<string, unknown>>
      cash_flow_by_month?: Array<Record<string, unknown>>
      balance_by_year?: Array<Record<string, unknown>>
      engine?: string
    }>(`/api/reports/sql?${q}`)
  },

  driveStatus: () => request<DriveStatus>('/api/drive/status'),
  driveLink: (body: { workspace_id: string; folder_id: string; folder_name?: string }) =>
    request<{ workspace_id?: string; drive_folder_id?: string; drive_folder_name?: string }>(
      '/api/drive/link',
      { method: 'POST', body: JSON.stringify(body) },
    ),
  driveBrowse: (folder_id?: string) => {
    const q = new URLSearchParams()
    if (folder_id) q.set('folder_id', folder_id)
    q.set('depth', '1')
    return request<DriveBrowseNode>(`/api/drive/browse?${q}`)
  },
  driveChildren: (folder_id: string, parent_path?: string) => {
    const q = new URLSearchParams({ folder_id })
    if (parent_path) q.set('parent_path', parent_path)
    return request<DriveBrowseNode[]>(`/api/drive/children?${q}`)
  },
  driveSync: (body: {
    workspace_id: string
    folder_id?: string
    max_files?: number
    ingest?: boolean
  }) =>
    request<DriveSyncResult>('/api/drive/sync', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  driveImportFiles: (body: {
    workspace_id: string
    files: Array<{ id: string; name: string; path?: string; mime_type?: string }>
    ingest?: boolean
  }) =>
    request<DriveSyncResult>('/api/drive/import-files', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  driveImportFolder: (body: {
    workspace_id: string
    folder_id: string
    max_files?: number
    ingest?: boolean
  }) =>
    request<DriveSyncResult>('/api/drive/import-folder', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
}
