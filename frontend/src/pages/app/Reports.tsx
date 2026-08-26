import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api, type Period, type PnLLineItem, type PnLReport } from '../../lib/api'
import { useLocale } from '../../i18n'
import { cn } from '../../lib/utils'

function periodClosed(p: Period): boolean {
  const s = String(p.status ?? '').toLowerCase()
  return s === 'closed' || Boolean(p.closed_at)
}

function periodSuggested(p: Period): boolean {
  return String(p.status ?? '').toLowerCase() === 'suggested'
}

type StatementsBundle = Awaited<ReturnType<typeof api.financialStatements>>

function money(n: number) {
  return n.toLocaleString(undefined, { style: 'currency', currency: 'USD' })
}

function periodToDates(period: string): { from?: string; to?: string } {
  const p = period.trim()
  if (/^\d{4}-\d{2}$/.test(p)) {
    const [ys, ms] = p.split('-')
    const y = Number(ys)
    const m = Number(ms)
    const last = new Date(y, m, 0).getDate()
    return { from: `${p}-01`, to: `${p}-${String(last).padStart(2, '0')}` }
  }
  if (/^\d{4}$/.test(p)) {
    return { from: `${p}-01-01`, to: `${p}-12-31` }
  }
  return {}
}

function pnlItems(pnl: PnLReport | null | undefined, key: 'revenueItems' | 'expenseItems'): PnLLineItem[] {
  if (!pnl) return []
  const items = pnl[key]
  return Array.isArray(items) ? items : []
}

function PnLDetailTables({
  pnl,
  t,
}: {
  pnl: PnLReport
  t: (key: string) => string
}) {
  const revenue = pnlItems(pnl, 'revenueItems')
  const expenses = pnlItems(pnl, 'expenseItems')
  const revTotal = Number(pnl.revenue ?? pnl.totalRevenue ?? 0)
  const expTotal = Number(pnl.expenses ?? pnl.totalExpenses ?? 0)
  const net = Number(pnl.net_income ?? pnl.netIncome ?? revTotal - expTotal)

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-3">
        {[
          { label: t('reports.revenue'), value: revTotal, tone: 'text-emerald-700' },
          { label: t('reports.expenses'), value: expTotal, tone: 'text-rose-700' },
          { label: t('reports.net'), value: net, tone: 'text-amber-700' },
        ].map((kpi) => (
          <div key={kpi.label} className="rounded-xl border border-border bg-background p-4">
            <p className="text-sm text-muted-foreground">{kpi.label}</p>
            <p className={cn('mt-1 text-2xl font-semibold tabular-nums', kpi.tone)}>
              {money(kpi.value)}
            </p>
          </div>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="table-scroll rounded-xl border border-border bg-background">
          <div className="border-b border-border px-4 py-3">
            <h3 className="font-semibold">{t('reports.revenue')}</h3>
            <p className="text-xs text-muted-foreground">{t('reports.pnlDetail')}</p>
          </div>
          {revenue.length === 0 ? (
            <p className="px-4 py-6 text-sm text-muted-foreground">—</p>
          ) : (
            <table className="w-full min-w-[320px] text-left text-sm">
              <thead className="bg-secondary/40 text-muted-foreground">
                <tr>
                  <th className="px-4 py-2 font-medium">Código</th>
                  <th className="px-4 py-2 font-medium">Cuenta</th>
                  <th className="px-4 py-2 text-right font-medium">Monto</th>
                  <th className="px-4 py-2 text-right font-medium">{t('reports.txCount')}</th>
                </tr>
              </thead>
              <tbody>
                {revenue.map((row) => (
                  <tr key={`${row.code}-${row.name}`} className="border-t border-border">
                    <td className="px-4 py-2 font-mono text-xs">{row.code ?? '—'}</td>
                    <td className="px-4 py-2">{row.name ?? '—'}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{money(Number(row.amount ?? 0))}</td>
                    <td className="px-4 py-2 text-right tabular-nums text-muted-foreground">
                      {row.txCount ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="table-scroll rounded-xl border border-border bg-background">
          <div className="border-b border-border px-4 py-3">
            <h3 className="font-semibold">{t('reports.expenses')}</h3>
            <p className="text-xs text-muted-foreground">{t('reports.pnlDetail')}</p>
          </div>
          {expenses.length === 0 ? (
            <p className="px-4 py-6 text-sm text-muted-foreground">—</p>
          ) : (
            <table className="w-full min-w-[320px] text-left text-sm">
              <thead className="bg-secondary/40 text-muted-foreground">
                <tr>
                  <th className="px-4 py-2 font-medium">Código</th>
                  <th className="px-4 py-2 font-medium">Cuenta</th>
                  <th className="px-4 py-2 text-right font-medium">Monto</th>
                  <th className="px-4 py-2 text-right font-medium">{t('reports.txCount')}</th>
                </tr>
              </thead>
              <tbody>
                {expenses.map((row) => (
                  <tr key={`${row.code}-${row.name}`} className="border-t border-border">
                    <td className="px-4 py-2 font-mono text-xs">{row.code ?? '—'}</td>
                    <td className="px-4 py-2">{row.name ?? '—'}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{money(Number(row.amount ?? 0))}</td>
                    <td className="px-4 py-2 text-right tabular-nums text-muted-foreground">
                      {row.txCount ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}

const btnPrimary =
  'cursor-pointer rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-amber-600 hover:opacity-95 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:cursor-not-allowed disabled:opacity-50'
const btnSecondary =
  'cursor-pointer rounded-lg border border-border bg-card px-4 py-2 text-sm font-medium transition hover:border-primary/50 hover:bg-secondary focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:cursor-not-allowed disabled:opacity-50'

export default function Reports() {
  const { workspaceId = '' } = useParams()
  const { t } = useLocale()
  const [periods, setPeriods] = useState<Period[]>([])
  const [pnl, setPnl] = useState<PnLReport | null>(null)
  const [bundle, setBundle] = useState<StatementsBundle | null>(null)
  const [periodInput, setPeriodInput] = useState(() => {
    const d = new Date()
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
  })
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [loading, setLoading] = useState(true)
  const [loadingStmt, setLoadingStmt] = useState(false)
  const [loadingPnl, setLoadingPnl] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pnlLoaded, setPnlLoaded] = useState(false)
  const [fiscalYears, setFiscalYears] = useState<
    Array<{
      fiscal_year?: string
      status?: string
      net_income?: number
      retained_earnings_after?: number
      transaction_count?: number
    }>
  >([])
  const [yearInput, setYearInput] = useState(() => String(new Date().getFullYear()))
  const [closingYear, setClosingYear] = useState(false)

  const loadPeriods = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [periodsData, yearsData] = await Promise.all([
        api.listPeriods({ workspace_id: workspaceId }),
        api.listFiscalYears(workspaceId),
      ])
      setPeriods(Array.isArray(periodsData) ? periodsData : [])
      setFiscalYears(Array.isArray(yearsData.years) ? yearsData.years : [])
    } catch (e) {
      setError(e instanceof Error ? e.message : t('common.error'))
      setPeriods([])
    } finally {
      setLoading(false)
    }
  }, [workspaceId, t])

  useEffect(() => {
    void loadPeriods()
  }, [loadPeriods])

  async function loadStatements() {
    setLoadingStmt(true)
    setError(null)
    try {
      const data = await api.financialStatements({
        workspace_id: workspaceId,
        period: periodInput || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      })
      setBundle(data)
      if (data.pnl) {
        setPnl(data.pnl)
        setPnlLoaded(true)
      }
      await loadPeriods()
    } catch (e) {
      setError(e instanceof Error ? e.message : t('common.error'))
    } finally {
      setLoadingStmt(false)
    }
  }

  async function loadPnl() {
    setLoadingPnl(true)
    setError(null)
    setPnlLoaded(true)
    try {
      const derived = !dateFrom && !dateTo ? periodToDates(periodInput) : {}
      const data = await api.pnlReport({
        workspace_id: workspaceId,
        date_from: dateFrom || derived.from,
        date_to: dateTo || derived.to,
      })
      setPnl(data)
      // Keep statement KPIs in sync when only loading P&L
      setBundle((prev) => (prev ? { ...prev, pnl: data } : prev))
    } catch (e) {
      setError(e instanceof Error ? e.message : t('common.error'))
      setPnl(null)
    } finally {
      setLoadingPnl(false)
    }
  }

  async function closePeriod(period: string) {
    setError(null)
    try {
      await api.closePeriod(period, workspaceId)
      await loadPeriods()
    } catch (e) {
      setError(e instanceof Error ? e.message : t('common.error'))
    }
  }

  async function reopenPeriod(period: string) {
    setError(null)
    try {
      await api.reopenPeriod(period, workspaceId)
      await loadPeriods()
    } catch (e) {
      setError(e instanceof Error ? e.message : t('common.error'))
    }
  }

  async function closeFiscalYear() {
    setClosingYear(true)
    setError(null)
    try {
      const res = await api.closeFiscalYear(yearInput, {
        workspace_id: workspaceId,
        allow_suspense: false,
      })
      await loadPeriods()
      setError(null)
      alert(
        `Año ${res.fiscal_year} cerrado. NI ${money(res.net_income)} → RE acumulada ${money(res.retained_earnings_after)}.`,
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : t('common.error'))
    } finally {
      setClosingYear(false)
    }
  }

  async function reopenFiscalYear(year: string) {
    setError(null)
    try {
      await api.reopenFiscalYear(year, workspaceId)
      await loadPeriods()
    } catch (e) {
      setError(e instanceof Error ? e.message : t('common.error'))
    }
  }

  const displayPnl = pnl || bundle?.pnl || null
  const chartData = displayPnl
    ? [
        { name: t('reports.revenue'), value: Number(displayPnl.revenue ?? displayPnl.totalRevenue ?? 0) },
        { name: t('reports.expenses'), value: Number(displayPnl.expenses ?? displayPnl.totalExpenses ?? 0) },
        { name: t('reports.net'), value: Number(displayPnl.net_income ?? displayPnl.netIncome ?? 0) },
      ]
    : []

  const cfMonthly = bundle?.cash_flow_monthly || []

  return (
    <div>
      <div className="mb-6 animate-fade-up">
        <h1 className="page-title">{t('reports.title')}</h1>
        <p className="mt-1.5 text-muted-foreground">{t('reports.subtitle')}</p>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <section className="mb-8 rounded-xl border border-border bg-card p-5">
        <h2 className="mb-1 text-lg font-semibold tracking-tight">Emitir estados financieros</h2>
        <p className="mb-4 text-sm text-muted-foreground">
          Balance + P&amp;L detallado + Cash flow (txs verificadas, motor local $0). Periodo{' '}
          <code className="text-xs">YYYY-MM</code> o <code className="text-xs">YYYY</code>. Si no
          pones fechas, «Cargar P&amp;L» usa el periodo.
        </p>
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
          <label className="w-full text-sm sm:w-auto">
            Periodo
            <input
              className="mt-1 block w-full rounded-lg border border-border bg-background px-3 py-2 sm:w-44"
              placeholder="2026-05 o 2026"
              value={periodInput}
              onChange={(e) => setPeriodInput(e.target.value)}
            />
          </label>
          <label className="w-full text-sm sm:w-auto">
            {t('reports.from')}
            <input
              type="date"
              className="mt-1 block w-full rounded-lg border border-border bg-background px-3 py-2"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
            />
          </label>
          <label className="w-full text-sm sm:w-auto">
            {t('reports.to')}
            <input
              type="date"
              className="mt-1 block w-full rounded-lg border border-border bg-background px-3 py-2"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
            />
          </label>
          <div className="flex w-full flex-wrap gap-2 sm:w-auto">
            <button
              type="button"
              onClick={() => void loadStatements()}
              disabled={loadingStmt}
              className={cn(btnPrimary, 'flex-1 sm:flex-none')}
            >
              {loadingStmt ? t('common.loading') : t('reports.emit')}
            </button>
            <button
              type="button"
              onClick={() => void loadPnl()}
              disabled={loadingPnl}
              className={cn(btnSecondary, 'flex-1 sm:flex-none')}
            >
              {loadingPnl ? t('common.loading') : t('reports.load')}
            </button>
            <a
              className={cn(btnSecondary, 'flex-1 text-center sm:flex-none')}
              href={api.exportStatementsUrl({
                workspace_id: workspaceId,
                period: periodInput || undefined,
                date_from: dateFrom || undefined,
                date_to: dateTo || undefined,
              })}
            >
              Export Excel
            </a>
          </div>
        </div>

        {bundle && (
          <p className="mb-4 text-xs text-muted-foreground">
            {bundle.period_label} · {bundle.transaction_count ?? 0} txs · motor {bundle.engine}
          </p>
        )}

        {displayPnl && (
          <div className="mb-6">
            <h3 className="mb-3 text-base font-semibold tracking-tight">{t('reports.pnl')}</h3>
            <PnLDetailTables pnl={displayPnl} t={t} />
            <div className="mt-4 h-56 rounded-xl border border-border bg-background p-3">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} />
                  <Tooltip formatter={(v) => money(Number(v ?? 0))} />
                  <Bar dataKey="value" fill="var(--primary)" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {pnlLoaded && !displayPnl && !loadingPnl && (
          <p className="mb-4 text-sm text-muted-foreground">{t('reports.pnlEmpty')}</p>
        )}

        {bundle?.balance_chain_alerts && bundle.balance_chain_alerts.length > 0 && (
          <div className="mb-6 rounded-xl border border-rose-300 bg-rose-50 p-4 dark:border-rose-800 dark:bg-rose-950/40">
            <h3 className="mb-2 font-semibold text-rose-900 dark:text-rose-100">
              Alertas de cadenazo bancario
            </h3>
            <ul className="space-y-3 text-sm">
              {bundle.balance_chain_alerts.map((a) => (
                <li
                  key={`${a.statement_month}-${a.bank_account_number}`}
                  className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between"
                >
                  <div>
                    <p className="font-medium">
                      {a.statement_month} · {a.bank_name || 'Banco'} · …
                      {(a.bank_account_number || '').slice(-4)}
                    </p>
                    <p className="text-muted-foreground">{a.alert_message || 'Descuadre de saldos'}</p>
                  </div>
                  {a.paused && a.statement_month && a.bank_account_number && (
                    <button
                      type="button"
                      className="shrink-0 rounded-md border border-rose-400 px-3 py-1.5 text-xs font-medium hover:bg-rose-100 dark:hover:bg-rose-900"
                      onClick={() =>
                        void (async () => {
                          try {
                            await api.ackBalanceChain({
                              workspace_id: workspaceId,
                              statement_month: a.statement_month!,
                              bank_account_number: a.bank_account_number!,
                            })
                            await loadStatements()
                          } catch (e) {
                            setError(e instanceof Error ? e.message : t('common.error'))
                          }
                        })()
                      }
                    >
                      Marcar revisado
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        {bundle?.balance_sheet && (
          <div className="mb-6">
            <div className="mb-3 flex flex-wrap items-center gap-3 text-sm">
              <span
                className={
                  bundle.balance_sheet.balanced
                    ? 'rounded-md bg-emerald-100 px-2 py-1 font-medium text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200'
                    : 'rounded-md bg-amber-100 px-2 py-1 font-medium text-amber-900 dark:bg-amber-950 dark:text-amber-100'
                }
              >
                {bundle.balance_sheet.balanced
                  ? 'Balance cuadrado (A = P + Patrimonio)'
                  : `Descuadre Δ ${money(Number(bundle.balance_sheet.imbalance ?? 0))}`}
              </span>
              {bundle.balance_sheet.equation && (
                <span className="text-muted-foreground">{bundle.balance_sheet.equation}</span>
              )}
            </div>
            <div className="grid gap-4 lg:grid-cols-3">
              <div className="rounded-xl border border-border bg-background p-4">
                <h3 className="mb-2 font-semibold">Balance — Activos</h3>
                <p className="mb-2 text-xl font-semibold tabular-nums">
                  {money(Number(bundle.balance_sheet.totalAssets ?? 0))}
                </p>
                <ul className="space-y-1 text-sm text-muted-foreground">
                  {(bundle.balance_sheet.assets || []).map((a) => (
                    <li key={a.code} className="flex justify-between gap-2">
                      <span>{a.name}</span>
                      <span className="tabular-nums">{money(Number(a.amount ?? 0))}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="rounded-xl border border-border bg-background p-4">
                <h3 className="mb-2 font-semibold">Pasivos</h3>
                <p className="mb-2 text-xl font-semibold tabular-nums">
                  {money(Number(bundle.balance_sheet.totalLiabilities ?? 0))}
                </p>
                <ul className="space-y-1 text-sm text-muted-foreground">
                  {(bundle.balance_sheet.liabilities || []).length === 0 && <li>—</li>}
                  {(bundle.balance_sheet.liabilities || []).map((a) => (
                    <li key={a.code} className="flex justify-between gap-2">
                      <span>{a.name}</span>
                      <span className="tabular-nums">{money(Number(a.amount ?? 0))}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="rounded-xl border border-border bg-background p-4">
                <h3 className="mb-2 font-semibold">Patrimonio</h3>
                <p className="mb-2 text-xl font-semibold tabular-nums">
                  {money(Number(bundle.balance_sheet.totalEquity ?? 0))}
                </p>
                <ul className="space-y-1 text-sm text-muted-foreground">
                  {(bundle.balance_sheet.equity || []).map((a) => (
                    <li key={a.code || a.name} className="flex justify-between gap-2">
                      <span>{a.name}</span>
                      <span className="tabular-nums">{money(Number(a.amount ?? 0))}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        )}

        {bundle?.cash_flow && (
          <div className="mb-6 rounded-xl border border-border bg-background p-4">
            <h3 className="mb-2 font-semibold">Cash flow (O / I / F)</h3>
            <div className="grid gap-3 sm:grid-cols-4">
              <div>
                <p className="text-xs text-muted-foreground">Operativo neto</p>
                <p className="text-lg font-semibold tabular-nums">
                  {money(Number(bundle.cash_flow.operating?.net ?? 0))}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Inversión neto</p>
                <p className="text-lg font-semibold tabular-nums">
                  {money(Number(bundle.cash_flow.investing?.net ?? 0))}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Financiación neto</p>
                <p className="text-lg font-semibold tabular-nums">
                  {money(Number(bundle.cash_flow.financing?.net ?? 0))}
                </p>
                <p className="text-xs text-muted-foreground">Incluye Owner&apos;s Draws</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Cambio neto</p>
                <p className="text-lg font-semibold tabular-nums">
                  {money(Number(bundle.cash_flow.netChange ?? 0))}
                </p>
              </div>
            </div>
            {bundle.cash_flow.note && (
              <p className="mt-2 text-xs text-muted-foreground">{bundle.cash_flow.note}</p>
            )}
          </div>
        )}

        {cfMonthly.length > 0 && (
          <div className="mb-2 h-64 rounded-xl border border-border bg-background p-4">
            <h3 className="mb-2 text-sm font-semibold">Cash flow mensual</h3>
            <ResponsiveContainer width="100%" height="90%">
              <BarChart data={cfMonthly}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="period" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend />
                <Bar dataKey="inflows" name="Entradas" fill="#047857" radius={[4, 4, 0, 0]} />
                <Bar dataKey="outflows" name="Salidas" fill="#be123c" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </section>

      <section className="mb-8">
        <h2 className="mb-3 text-lg font-semibold tracking-tight">Cierre anual</h2>
        <p className="mb-3 max-w-2xl text-sm text-muted-foreground">
          Al cerrar el año, la utilidad neta del P&amp;L se acumula en Utilidades retenidas (3020)
          para los balances siguientes. Requiere txs verificadas y sin Suspense (9999).
        </p>
        <div className="mb-4 flex flex-wrap items-end gap-3">
          <label className="text-sm">
            Año
            <input
              className="mt-1 block w-28 rounded-md border border-border bg-background px-3 py-2"
              value={yearInput}
              onChange={(e) => setYearInput(e.target.value.replace(/\D/g, '').slice(0, 4))}
              placeholder="2025"
            />
          </label>
          <button
            type="button"
            disabled={closingYear || yearInput.length !== 4}
            onClick={() => void closeFiscalYear()}
            className={btnPrimary}
          >
            {closingYear ? 'Cerrando…' : `Cerrar año ${yearInput}`}
          </button>
        </div>
        {fiscalYears.length > 0 && (
          <ul className="space-y-2">
            {fiscalYears.map((y) => (
              <li
                key={String(y.fiscal_year)}
                className="soft-shadow flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3"
              >
                <div>
                  <p className="font-medium">{y.fiscal_year}</p>
                  <p className="text-sm text-muted-foreground">
                    {y.status} · NI {money(Number(y.net_income ?? 0))} ·{' '}
                    {Number(y.transaction_count ?? 0)} txs
                  </p>
                </div>
                {y.status === 'closed' && y.fiscal_year && (
                  <button
                    type="button"
                    className="rounded-md border border-border px-3 py-1.5 text-xs font-medium hover:bg-muted"
                    onClick={() => void reopenFiscalYear(String(y.fiscal_year))}
                  >
                    Reabrir año
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mb-8">
        <h2 className="mb-3 text-lg font-semibold tracking-tight">{t('reports.periods')}</h2>
        {loading && <p className="text-muted-foreground">{t('common.loading')}</p>}
        {!loading && periods.length === 0 && (
          <div className="soft-shadow rounded-xl border border-dashed border-border bg-card px-6 py-10 text-center">
            <p className="font-medium">{t('reports.periodsEmpty')}</p>
            <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
              {t('reports.periodsEmptyHint')}
            </p>
            <button
              type="button"
              onClick={() => void closePeriod(periodInput)}
              className={cn(btnPrimary, 'mt-5')}
            >
              {t('reports.close')} ({periodInput})
            </button>
          </div>
        )}
        <div className="space-y-2">
          {periods.map((p) => {
            const closed = periodClosed(p)
            const suggested = periodSuggested(p)
            return (
              <div
                key={p.period}
                className="soft-shadow flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3"
              >
                <div className="flex flex-wrap items-center gap-3">
                  <p className="font-medium">{p.period}</p>
                  <span
                    className={cn(
                      'rounded-md px-2 py-0.5 text-xs font-medium',
                      closed
                        ? 'bg-secondary text-muted-foreground'
                        : suggested
                          ? 'bg-amber-50 text-amber-900'
                          : 'bg-emerald-50 text-emerald-800',
                    )}
                  >
                    {closed
                      ? t('reports.statusClosed')
                      : suggested
                        ? t('reports.statusSuggested')
                        : t('reports.statusOpen')}
                  </span>
                  {(p.verified_count ?? p.transaction_count) != null && (
                    <span className="text-xs text-muted-foreground">
                      {Number(p.verified_count ?? p.transaction_count)} {t('reports.txCount')}
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setPeriodInput(p.period)
                      void loadStatements()
                    }}
                    className={btnSecondary}
                  >
                    {t('reports.emit')}
                  </button>
                  <button
                    type="button"
                    onClick={() => void closePeriod(p.period)}
                    disabled={closed}
                    className={cn(btnPrimary, 'disabled:opacity-40')}
                  >
                    {t('reports.close')}
                  </button>
                  <button
                    type="button"
                    onClick={() => void reopenPeriod(p.period)}
                    disabled={!closed || suggested}
                    className={cn(btnSecondary, 'disabled:opacity-40')}
                  >
                    {t('reports.reopen')}
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      </section>
    </div>
  )
}
