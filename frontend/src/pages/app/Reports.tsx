import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  api,
  type BalanceLine,
  type Period,
  type PnLLineItem,
  type PnLReport,
  type StatementsBundle,
} from '../../lib/api'
import { useLocale } from '../../i18n'
import { cn } from '../../lib/utils'

function periodClosed(p: Period): boolean {
  const s = String(p.status ?? '').toLowerCase()
  return s === 'closed' || Boolean(p.closed_at)
}

function periodSuggested(p: Period): boolean {
  return String(p.status ?? '').toLowerCase() === 'suggested'
}

function money(n: number) {
  return n.toLocaleString(undefined, { style: 'currency', currency: 'USD' })
}

const MONTH_LABELS = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
const MONTH_KEYS = ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12']

function pnlItems(
  pnl: PnLReport | null | undefined,
  key: 'revenueItems' | 'expenseItems' | 'cogsItems',
): PnLLineItem[] {
  if (!pnl) return []
  const items = pnl[key]
  return Array.isArray(items) ? items : []
}

function MonthTable({
  title,
  items,
  total,
  showUncategorizedHint,
}: {
  title: string
  items: PnLLineItem[]
  total: number
  showUncategorizedHint?: boolean
}) {
  return (
    <div className="table-scroll animate-fade-up rounded-xl border border-border bg-card soft-shadow-lift">
      <div className="border-b border-border px-4 py-3">
        <h3 className="font-display text-lg tracking-wide">{title}</h3>
      </div>
      {items.length === 0 ? (
        <p className="px-4 py-6 text-sm text-muted-foreground">—</p>
      ) : (
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="bg-secondary/40 text-muted-foreground">
            <tr>
              <th className="px-3 py-2 font-medium">Código</th>
              <th className="px-3 py-2 font-medium">Cuenta</th>
              {MONTH_LABELS.map((m) => (
                <th key={m} className="px-2 py-2 text-right font-medium">
                  {m}
                </th>
              ))}
              <th className="px-3 py-2 text-right font-medium">Total</th>
            </tr>
          </thead>
          <tbody>
            {items.map((row) => {
              const isSuspense = row.code === '9999'
              return (
                <tr
                  key={`${row.code}-${row.name}`}
                  className="border-t border-border transition-colors duration-200 hover:bg-[color-mix(in_srgb,var(--accent-cream)_8%,transparent)]"
                >
                  <td className="px-3 py-2 font-mono text-xs">{row.code ?? '—'}</td>
                  <td className="px-3 py-2">
                    {row.name ?? '—'}
                    {isSuspense && showUncategorizedHint && (
                      <span
                        className="ml-1 cursor-help text-warning-foreground"
                        title="Txs sin clasificar — ir a Transacciones para resolver"
                      >
                        ⚠️
                      </span>
                    )}
                  </td>
                  {MONTH_KEYS.map((mk) => (
                    <td key={mk} className="px-2 py-2 text-right tabular-nums text-xs">
                      {money(Number(row.byMonth?.[mk] ?? 0))}
                    </td>
                  ))}
                  <td className="px-3 py-2 text-right tabular-nums font-medium">
                    {money(Number(row.amount ?? 0))}
                  </td>
                </tr>
              )
            })}
            <tr className="border-t-2 border-border bg-secondary/30">
              <td colSpan={14} className="px-3 py-2 text-right font-semibold">
                TOTAL {title} {money(total)}
              </td>
            </tr>
          </tbody>
        </table>
      )}
    </div>
  )
}

function BalanceSection({
  title,
  lines,
  total,
  defaultOpen = true,
}: {
  title: string
  lines: BalanceLine[]
  total: number
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="animate-fade-up rounded-xl border border-border bg-card soft-shadow-lift">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-3 text-left transition-colors duration-200 hover:bg-secondary/30"
      >
        <span className="font-display text-lg tracking-wide">
          {open ? '▼' : '▶'} {title}
        </span>
        <span className="tabular-nums font-semibold">{money(total)}</span>
      </button>
      {open && (
        <div className="table-scroll border-t border-border">
          {lines.length === 0 ? (
            <p className="px-4 py-4 text-sm text-muted-foreground">(vacío)</p>
          ) : (
            <table className="w-full min-w-[560px] text-left text-sm">
              <thead className="bg-secondary/40 text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 font-medium">Código</th>
                  <th className="px-3 py-2 font-medium">Cuenta</th>
                  <th className="px-3 py-2 text-right font-medium">Saldo Inicial</th>
                  <th className="px-3 py-2 text-right font-medium">Débitos</th>
                  <th className="px-3 py-2 text-right font-medium">Créditos</th>
                  <th className="px-3 py-2 text-right font-medium">Saldo Final</th>
                </tr>
              </thead>
              <tbody>
                {lines.map((row) => (
                  <tr
                    key={`${row.code}-${row.name}`}
                    className="border-t border-border transition-colors duration-200 hover:bg-[color-mix(in_srgb,var(--accent-cream)_8%,transparent)]"
                  >
                    <td className="px-3 py-2 font-mono text-xs">{row.code ?? '—'}</td>
                    <td className="px-3 py-2">{row.name ?? '—'}</td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {money(Number(row.opening ?? 0))}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {money(Number(row.debits ?? 0))}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {money(Number(row.credits ?? 0))}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums font-medium">
                      {money(Number(row.closing ?? row.amount ?? 0))}
                    </td>
                  </tr>
                ))}
                <tr className="border-t-2 border-border bg-secondary/30">
                  <td colSpan={6} className="px-3 py-2 text-right font-semibold">
                    TOTAL {title} {money(total)}
                  </td>
                </tr>
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}

const btnPrimary =
  'cursor-pointer rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition duration-200 hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:cursor-not-allowed disabled:opacity-50'
const btnSecondary =
  'cursor-pointer rounded-lg border border-border bg-card px-4 py-2 text-sm font-medium transition duration-200 hover:border-primary/50 hover:bg-secondary focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:cursor-not-allowed disabled:opacity-50'

export default function Reports() {
  const { workspaceId = '' } = useParams()
  const { t } = useLocale()
  const [periods, setPeriods] = useState<Period[]>([])
  const [bundle, setBundle] = useState<StatementsBundle | null>(null)
  const [availableYears, setAvailableYears] = useState<string[]>([])
  const [fiscalYear, setFiscalYear] = useState('')
  const [month, setMonth] = useState<string>('') // '' = whole year
  const [loading, setLoading] = useState(true)
  const [loadingStmt, setLoadingStmt] = useState(false)
  const [error, setError] = useState<string | null>(null)
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
  const [yearsReady, setYearsReady] = useState(false)

  const loadMeta = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [periodsData, yearsData, avail] = await Promise.all([
        api.listPeriods({ workspace_id: workspaceId }),
        api.listFiscalYears(workspaceId),
        api.availableYears(workspaceId),
      ])
      setPeriods(Array.isArray(periodsData) ? periodsData : [])
      setFiscalYears(Array.isArray(yearsData.years) ? yearsData.years : [])
      const years = avail.verified_years?.length
        ? avail.verified_years
        : avail.years?.length
          ? avail.years
          : []
      setAvailableYears(years)
      const def = avail.default_year || years[0] || String(new Date().getFullYear())
      setFiscalYear((prev) => prev || String(def))
      setYearInput(String(def))
      setYearsReady(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : t('common.error'))
      setPeriods([])
      setYearsReady(true)
    } finally {
      setLoading(false)
    }
  }, [workspaceId, t])

  useEffect(() => {
    void loadMeta()
  }, [loadMeta])

  const loadStatements = useCallback(async () => {
    if (!fiscalYear) return
    setLoadingStmt(true)
    setError(null)
    try {
      const data = await api.financialStatements({
        workspace_id: workspaceId,
        fiscal_year: fiscalYear,
        month: month ? Number(month) : undefined,
      })
      setBundle(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : t('common.error'))
      setBundle(null)
    } finally {
      setLoadingStmt(false)
    }
  }, [workspaceId, fiscalYear, month, t])

  // Auto-load when year is ready / changes
  useEffect(() => {
    if (!yearsReady || !fiscalYear) return
    void loadStatements()
  }, [yearsReady, fiscalYear, month, loadStatements])

  async function closePeriod(period: string) {
    setError(null)
    try {
      await api.closePeriod(period, workspaceId)
      await loadMeta()
    } catch (e) {
      setError(e instanceof Error ? e.message : t('common.error'))
    }
  }

  async function reopenPeriod(period: string) {
    setError(null)
    try {
      await api.reopenPeriod(period, workspaceId)
      await loadMeta()
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
      await loadMeta()
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
      await loadMeta()
    } catch (e) {
      setError(e instanceof Error ? e.message : t('common.error'))
    }
  }

  const displayPnl = bundle?.pnl || null
  const revTotal = Number(displayPnl?.revenue ?? displayPnl?.totalRevenue ?? 0)
  const expTotal = Number(displayPnl?.expenses ?? displayPnl?.totalExpenses ?? 0)
  const cogsTotal = Number(displayPnl?.cogs ?? displayPnl?.totalCogs ?? 0)
  const opexTotal = Number(
    displayPnl?.operatingExpenses ??
      pnlItems(displayPnl, 'expenseItems').reduce((s, r) => s + Number(r.amount ?? 0), 0),
  )
  const net = Number(displayPnl?.net_income ?? displayPnl?.netIncome ?? revTotal - expTotal)

  const cfMonthly = useMemo(() => {
    const rows = bundle?.cash_flow_monthly || []
    return rows.map((r) => ({
      period: r.period,
      inflows: Number(r.inflows ?? 0),
      outflows: -Math.abs(Number(r.outflows ?? 0)),
      net: Number(r.net ?? 0),
    }))
  }, [bundle])

  const periodLabel = month ? `${fiscalYear}-${month}` : fiscalYear
  const exportHref = api.exportStatementsUrl({
    workspace_id: workspaceId,
    fiscal_year: fiscalYear || undefined,
    month: month ? Number(month) : undefined,
  })

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

      <section className="mb-8 rounded-xl border border-border bg-card p-5 soft-shadow-lift">
        <h2 className="mb-1 font-display text-xl tracking-wide">Estados financieros</h2>
        <p className="mb-4 text-sm text-muted-foreground">
          Balance + P&amp;L por cuenta/mes + Cash flow O/I/F. Solo txs <strong>verificadas</strong>.
          Año completo = columnas mensuales; año + mes = detalle del mes.
        </p>

        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
          <label className="w-full text-sm sm:w-auto">
            Año
            <select
              className="mt-1 block w-full rounded-lg border border-border bg-background px-3 py-2 sm:w-36"
              value={fiscalYear}
              onChange={(e) => setFiscalYear(e.target.value)}
            >
              {availableYears.length === 0 && (
                <option value={fiscalYear || String(new Date().getFullYear())}>
                  {fiscalYear || new Date().getFullYear()}
                </option>
              )}
              {availableYears.map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          </label>
          <label className="w-full text-sm sm:w-auto">
            Mes (opcional)
            <select
              className="mt-1 block w-full rounded-lg border border-border bg-background px-3 py-2 sm:w-40"
              value={month}
              onChange={(e) => setMonth(e.target.value)}
            >
              <option value="">Todo el año</option>
              {MONTH_KEYS.map((mk, i) => (
                <option key={mk} value={mk}>
                  {MONTH_LABELS[i]} ({mk})
                </option>
              ))}
            </select>
          </label>
          <div className="flex w-full flex-wrap gap-2 sm:w-auto">
            <button
              type="button"
              onClick={() => void loadStatements()}
              disabled={loadingStmt || !fiscalYear}
              className={cn(btnPrimary, 'flex-1 sm:flex-none')}
            >
              {loadingStmt ? t('common.loading') : 'Actualizar'}
            </button>
            <a
              className={cn(btnSecondary, 'flex-1 text-center sm:flex-none')}
              href={exportHref}
            >
              Export Excel
            </a>
          </div>
        </div>

        {bundle && (
          <p className="mb-4 text-xs text-muted-foreground">
            {bundle.period_label} · {bundle.transaction_count ?? 0} txs verificadas
            {(bundle.pending_count ?? 0) > 0 && (
              <>
                {' '}
                ·{' '}
                <Link
                  to={`/app/${workspaceId}/transactions`}
                  className="text-primary underline-offset-2 hover:underline"
                >
                  {bundle.pending_count} pendientes de revisar
                </Link>
              </>
            )}{' '}
            · motor {bundle.engine}
          </p>
        )}

        {bundle && (bundle.transaction_count ?? 0) === 0 && (
          <div className="mb-4 rounded-lg border border-warning/40 bg-warning/10 px-4 py-3 text-sm">
            No hay txs verificadas en {periodLabel}.
            {(bundle.pending_count ?? 0) > 0 ? (
              <>
                {' '}
                Hay {bundle.pending_count} en revisión —{' '}
                <Link className="underline" to={`/app/${workspaceId}/transactions`}>
                  apruébalas en Transacciones
                </Link>{' '}
                para que entren al P&amp;L.
              </>
            ) : (
              <> Importa extractos desde Documentos / Drive y clasifica.</>
            )}
          </div>
        )}

        {/* ── P&L ─────────────────────────────────────────────────────────── */}
        {displayPnl && (
          <div className="mb-8 space-y-4">
            <h3 className="font-display text-xl tracking-wide">{t('reports.pnl')}</h3>
            <div className="grid gap-4 sm:grid-cols-3">
              {[
                { label: t('reports.revenue'), value: revTotal, tone: 'text-[var(--positive)]' },
                { label: t('reports.expenses'), value: expTotal, tone: 'text-[var(--negative)]' },
                { label: t('reports.net'), value: net, tone: 'text-primary' },
              ].map((kpi) => (
                <div
                  key={kpi.label}
                  className="animate-fade-up rounded-xl border border-border bg-background p-4 soft-shadow-lift"
                >
                  <p className="text-sm text-muted-foreground">{kpi.label}</p>
                  <p className={cn('mt-1 text-2xl font-semibold tabular-nums', kpi.tone)}>
                    {money(kpi.value)}
                  </p>
                </div>
              ))}
            </div>

            <MonthTable
              title="INGRESOS"
              items={pnlItems(displayPnl, 'revenueItems')}
              total={revTotal}
            />
            <MonthTable
              title="COSTO DE VENTAS"
              items={pnlItems(displayPnl, 'cogsItems')}
              total={cogsTotal}
            />
            <MonthTable
              title="GASTOS OPERATIVOS"
              items={pnlItems(displayPnl, 'expenseItems')}
              total={opexTotal}
              showUncategorizedHint
            />

            <div className="rounded-xl border border-border bg-secondary/20 px-4 py-3 text-right">
              <span className="font-display text-lg font-semibold tracking-wide">
                UTILIDAD NETA {money(net)}
              </span>
            </div>
          </div>
        )}

        {/* ── Balance chain alerts ────────────────────────────────────────── */}
        {bundle?.balance_chain_alerts && bundle.balance_chain_alerts.length > 0 && (
          <div className="mb-6 rounded-xl border border-destructive/40 bg-destructive/10 p-4">
            <h3 className="mb-2 font-semibold text-destructive">Alertas de cadenazo bancario</h3>
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
                      className={btnSecondary}
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

        {/* ── Balance ─────────────────────────────────────────────────────── */}
        {bundle?.balance_sheet && (
          <div className="mb-8 space-y-4">
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <span
                className={
                  bundle.balance_sheet.balanced
                    ? 'rounded-md bg-success px-2 py-1 font-medium text-success-foreground'
                    : 'rounded-md bg-warning px-2 py-1 font-medium text-warning-foreground'
                }
              >
                {bundle.balance_sheet.balanced
                  ? '✅ Balance cuadrado: A = P + E'
                  : `Descuadre Δ ${money(Number(bundle.balance_sheet.imbalance ?? 0))}`}
              </span>
              {bundle.balance_sheet.equation && (
                <span className="text-muted-foreground">{bundle.balance_sheet.equation}</span>
              )}
            </div>
            <div className="grid gap-4 lg:grid-cols-3">
              {[
                {
                  label: 'Activos',
                  value: Number(bundle.balance_sheet.totalAssets ?? 0),
                },
                {
                  label: 'Pasivos',
                  value: Number(bundle.balance_sheet.totalLiabilities ?? 0),
                },
                {
                  label: 'Patrimonio',
                  value: Number(bundle.balance_sheet.totalEquity ?? 0),
                },
              ].map((kpi) => (
                <div
                  key={kpi.label}
                  className="rounded-xl border border-border bg-background p-4 soft-shadow-lift"
                >
                  <p className="text-sm text-muted-foreground">{kpi.label}</p>
                  <p className="mt-1 text-xl font-semibold tabular-nums">{money(kpi.value)}</p>
                </div>
              ))}
            </div>
            <BalanceSection
              title="ACTIVOS"
              lines={bundle.balance_sheet.assets || []}
              total={Number(bundle.balance_sheet.totalAssets ?? 0)}
            />
            <BalanceSection
              title="PASIVOS"
              lines={bundle.balance_sheet.liabilities || []}
              total={Number(bundle.balance_sheet.totalLiabilities ?? 0)}
            />
            <BalanceSection
              title="PATRIMONIO"
              lines={bundle.balance_sheet.equity || []}
              total={Number(bundle.balance_sheet.totalEquity ?? 0)}
            />
          </div>
        )}

        {/* ── Cash flow ───────────────────────────────────────────────────── */}
        {bundle?.cash_flow && (
          <div className="mb-6 space-y-4">
            {cfMonthly.length > 0 && (
              <div className="h-72 rounded-xl border border-border bg-background p-4 soft-shadow-lift">
                <h3 className="mb-2 text-sm font-semibold">
                  Cash flow mensual — entradas{' '}
                  <span className="text-[var(--positive)]">■</span> / salidas{' '}
                  <span className="text-[var(--negative)]">■</span>
                </h3>
                <ResponsiveContainer width="100%" height="90%">
                  <BarChart data={cfMonthly} stackOffset="sign">
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis dataKey="period" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip
                      formatter={(v) => money(Number(v ?? 0))}
                      contentStyle={{
                        background: 'var(--bg-card)',
                        border: '1px solid var(--border)',
                        borderRadius: 8,
                      }}
                    />
                    <Bar
                      dataKey="inflows"
                      name="Entradas"
                      stackId="cf"
                      fill="var(--positive)"
                      radius={[6, 6, 0, 0]}
                    />
                    <Bar
                      dataKey="outflows"
                      name="Salidas"
                      stackId="cf"
                      fill="var(--negative)"
                      radius={[6, 6, 0, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}

            <div className="table-scroll rounded-xl border border-border bg-card soft-shadow-lift">
              <div className="border-b border-border px-4 py-3">
                <h3 className="font-display text-lg tracking-wide">Cash flow — detalle O / I / F</h3>
              </div>
              <table className="w-full min-w-[420px] text-left text-sm">
                <thead className="bg-secondary/40 text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 font-medium">Tipo</th>
                    <th className="px-3 py-2 font-medium">Código</th>
                    <th className="px-3 py-2 font-medium">Cuenta</th>
                    <th className="px-3 py-2 text-right font-medium">Monto</th>
                    <th className="px-3 py-2 text-right font-medium"># txs</th>
                  </tr>
                </thead>
                <tbody>
                  {(
                    [
                      ['OPERATIVO', 'operating', 'operatingSubtotal'],
                      ['INVERSIÓN', 'investing', 'investingSubtotal'],
                      ['FINANCIACIÓN', 'financing', 'financingSubtotal'],
                    ] as const
                  ).flatMap(([label, key, sub]) => {
                    const lines = bundle.cash_flow_detail?.[key] || []
                    const subtotal = Number(
                      bundle.cash_flow_detail?.[sub] ??
                        bundle.cash_flow?.[
                          key === 'operating'
                            ? 'operating'
                            : key === 'investing'
                              ? 'investing'
                              : 'financing'
                        ]?.net ??
                        0,
                    )
                    const rows =
                      lines.length === 0
                        ? [
                            <tr key={`${key}-empty`} className="border-t border-border">
                              <td className="px-3 py-2 font-medium">{label}</td>
                              <td colSpan={2} className="px-3 py-2 text-muted-foreground">
                                (vacío)
                              </td>
                              <td className="px-3 py-2 text-right tabular-nums">{money(subtotal)}</td>
                              <td />
                            </tr>,
                          ]
                        : lines.map((row) => (
                            <tr
                              key={`${key}-${row.code}-${row.name}`}
                              className="border-t border-border transition-colors duration-200 hover:bg-[color-mix(in_srgb,var(--accent-cream)_8%,transparent)]"
                            >
                              <td className="px-3 py-2 font-medium">{label}</td>
                              <td className="px-3 py-2 font-mono text-xs">{row.code}</td>
                              <td className="px-3 py-2">{row.name}</td>
                              <td className="px-3 py-2 text-right tabular-nums">
                                {money(Number(row.amount ?? 0))}
                              </td>
                              <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">
                                {row.txCount ?? '—'}
                              </td>
                            </tr>
                          ))
                    return [
                      ...rows,
                      <tr key={`${key}-sub`} className="border-t border-border bg-secondary/20">
                        <td colSpan={3} className="px-3 py-2 text-right font-semibold">
                          SUBTOTAL {label}
                        </td>
                        <td className="px-3 py-2 text-right font-semibold tabular-nums">
                          {money(subtotal)}
                        </td>
                        <td />
                      </tr>,
                    ]
                  })}
                  <tr className="border-t-2 border-border bg-secondary/40">
                    <td colSpan={3} className="px-3 py-3 text-right font-display text-base font-semibold">
                      FLUJO NETO TOTAL
                    </td>
                    <td className="px-3 py-3 text-right font-semibold tabular-nums">
                      {money(
                        Number(
                          bundle.cash_flow_detail?.netTotal ?? bundle.cash_flow?.netChange ?? 0,
                        ),
                      )}
                    </td>
                    <td />
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>

      <section className="mb-8">
        <h2 className="mb-3 font-display text-xl tracking-wide">Cierre anual</h2>
        <p className="mb-3 max-w-2xl text-sm text-muted-foreground">
          Al cerrar el año, la utilidad neta del P&amp;L se acumula en Utilidades retenidas (3020).
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
                    className={btnSecondary}
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
        <h2 className="mb-3 font-display text-xl tracking-wide">{t('reports.periods')}</h2>
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
                          ? 'bg-warning text-warning-foreground'
                          : 'bg-success text-success-foreground',
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
                      const [y, m] = p.period.split('-')
                      if (y) setFiscalYear(y)
                      if (m) setMonth(m)
                    }}
                    className={btnSecondary}
                  >
                    Ver periodo
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
