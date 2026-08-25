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
import { api, type Period, type PnLReport } from '../../lib/api'
import { useLocale } from '../../i18n'
import { cn } from '../../lib/utils'

function periodClosed(p: Period): boolean {
  const s = String(p.status ?? '').toLowerCase()
  return s === 'closed' || Boolean(p.closed_at)
}

type StatementsBundle = Awaited<ReturnType<typeof api.financialStatements>>

function money(n: number) {
  return n.toLocaleString(undefined, { style: 'currency', currency: 'USD' })
}

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
  const [error, setError] = useState<string | null>(null)

  const loadPeriods = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.listPeriods({ workspace_id: workspaceId })
      setPeriods(Array.isArray(data) ? data : [])
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
      if (data.pnl) setPnl(data.pnl)
    } catch (e) {
      setError(e instanceof Error ? e.message : t('common.error'))
    } finally {
      setLoadingStmt(false)
    }
  }

  async function loadPnl() {
    setError(null)
    try {
      const data = await api.pnlReport({
        workspace_id: workspaceId,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      })
      setPnl(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : t('common.error'))
    }
  }

  async function closePeriod(period: string) {
    await api.closePeriod(period, workspaceId)
    await loadPeriods()
  }

  async function reopenPeriod(period: string) {
    await api.reopenPeriod(period, workspaceId)
    await loadPeriods()
  }

  const chartData = [
    { name: t('reports.revenue'), value: Number(pnl?.revenue ?? pnl?.totalRevenue ?? 0) },
    { name: t('reports.expenses'), value: Number(pnl?.expenses ?? pnl?.totalExpenses ?? 0) },
    { name: t('reports.net'), value: Number(pnl?.net_income ?? pnl?.netIncome ?? 0) },
  ]

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
          Balance + P&amp;L + Cash flow del periodo (desde transacciones verificadas, motor local $0).
          Usa mes <code className="text-xs">YYYY-MM</code> o año <code className="text-xs">YYYY</code>.
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
              className="flex-1 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-50 sm:flex-none"
            >
              {loadingStmt ? t('common.loading') : 'Emitir estados'}
            </button>
            <button
              type="button"
              onClick={() => void loadPnl()}
              className="flex-1 rounded-lg border border-border px-4 py-2 text-sm sm:flex-none"
            >
              {t('reports.load')}
            </button>
          </div>
        </div>

        {bundle && (
          <p className="mb-4 text-xs text-muted-foreground">
            {bundle.period_label} · {bundle.transaction_count ?? 0} txs · motor {bundle.engine}
          </p>
        )}

        {bundle?.pnl && (
          <div className="mb-6 grid gap-4 sm:grid-cols-3">
            {[
              { label: t('reports.revenue'), value: Number(bundle.pnl.revenue ?? 0), tone: 'text-emerald-700' },
              { label: t('reports.expenses'), value: Number(bundle.pnl.expenses ?? 0), tone: 'text-rose-700' },
              { label: t('reports.net'), value: Number(bundle.pnl.net_income ?? 0), tone: 'text-amber-700' },
            ].map((kpi) => (
              <div key={kpi.label} className="rounded-xl border border-border bg-background p-4">
                <p className="text-sm text-muted-foreground">{kpi.label}</p>
                <p className={cn('mt-1 text-2xl font-semibold tabular-nums', kpi.tone)}>
                  {money(kpi.value)}
                </p>
              </div>
            ))}
          </div>
        )}

        {bundle?.balance_sheet && (
          <div className="mb-6 grid gap-4 lg:grid-cols-3">
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
                  <li key={a.code} className="flex justify-between gap-2">
                    <span>{a.name}</span>
                    <span className="tabular-nums">{money(Number(a.amount ?? 0))}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}

        {bundle?.cash_flow && (
          <div className="mb-6 rounded-xl border border-border bg-background p-4">
            <h3 className="mb-2 font-semibold">Cash flow (operativo)</h3>
            <div className="grid gap-3 sm:grid-cols-3">
              <div>
                <p className="text-xs text-muted-foreground">Entradas</p>
                <p className="text-lg font-semibold tabular-nums text-emerald-700">
                  {money(Number(bundle.cash_flow.operating?.inflows ?? 0))}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Salidas</p>
                <p className="text-lg font-semibold tabular-nums text-rose-700">
                  {money(Number(bundle.cash_flow.operating?.outflows ?? 0))}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Neto</p>
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
        <h2 className="mb-3 text-lg font-semibold tracking-tight">{t('reports.periods')}</h2>
        {loading && <p className="text-muted-foreground">{t('common.loading')}</p>}
        {!loading && periods.length === 0 && (
          <div className="soft-shadow rounded-xl border border-dashed border-border bg-card px-6 py-10 text-center">
            <p className="font-medium">{t('reports.periodsEmpty')}</p>
            <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
              {t('reports.periodsEmptyHint')}
            </p>
          </div>
        )}
        <div className="space-y-2">
          {periods.map((p) => {
            const closed = periodClosed(p)
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
                        : 'bg-emerald-50 text-emerald-800',
                    )}
                  >
                    {closed ? t('reports.statusClosed') : t('reports.statusOpen')}
                  </span>
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setPeriodInput(p.period)
                      void loadStatements()
                    }}
                    className="rounded-lg border border-border px-3 py-1.5 text-sm"
                  >
                    Emitir
                  </button>
                  <button
                    type="button"
                    onClick={() => void closePeriod(p.period)}
                    disabled={closed}
                    className="rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground disabled:opacity-40"
                  >
                    {t('reports.close')}
                  </button>
                  <button
                    type="button"
                    onClick={() => void reopenPeriod(p.period)}
                    disabled={!closed}
                    className="rounded-lg border border-border px-3 py-1.5 text-sm disabled:opacity-40"
                  >
                    {t('reports.reopen')}
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      </section>

      {pnl && !bundle && (
        <section>
          <h2 className="mb-3 text-lg font-semibold tracking-tight">{t('reports.pnl')}</h2>
          <div className="soft-shadow h-64 rounded-xl border border-border bg-card p-4">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="value" fill="var(--primary)" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}
    </div>
  )
}
