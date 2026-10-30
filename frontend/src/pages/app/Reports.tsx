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
  type Period,
  type PnLLineItem,
  type QbReport,
  type QbReportKey,
  type QbRow,
  type StatementsBundle,
  type Transaction,
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

/** QuickBooks prints plain numbers (no $), negatives with a minus sign. */
function qbNumber(n: number | null | undefined) {
  if (n == null) return ''
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const MONTH_LABELS = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
const MONTH_KEYS = ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12']

function shortMonthLabels(locale: string): string[] {
  return locale === 'en'
    ? ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    : MONTH_LABELS
}

const btnPrimary =
  'cursor-pointer rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition duration-200 hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:cursor-not-allowed disabled:opacity-50'
const btnSecondary =
  'cursor-pointer rounded-lg border border-border bg-card px-4 py-2 text-sm font-medium transition duration-200 hover:border-primary/50 hover:bg-secondary focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:cursor-not-allowed disabled:opacity-50'

const NON_DRILL_CODES = new Set(['NI', '3020'])

/**
 * One QuickBooks-layout report (Profit and Loss / Balance Sheet).
 * Rows come from the API already in template order; the Excel download uses the same rows.
 */
function QbReportCard({
  company,
  report,
  showMonths,
  fiscalYear,
  onAccountClick,
  onDownload,
  downloading,
}: {
  company: string
  report: QbReport
  showMonths: boolean
  fiscalYear: string
  onAccountClick?: (row: QbRow) => void
  onDownload: () => void
  downloading: boolean
}) {
  const { t, locale } = useLocale()
  const monthHeaders = shortMonthLabels(locale).map((m) => `${m} ${fiscalYear}`)
  const isBalance = report.balanced !== undefined

  return (
    <div className="animate-fade-up overflow-hidden rounded-xl border border-border bg-card soft-shadow-lift">
      <div className="relative border-b border-border bg-[color-mix(in_srgb,var(--accent-cream)_35%,var(--bg-card))] px-4 py-5 text-center">
        <p className="text-sm font-semibold">{company}</p>
        <h3 className="mt-1 font-display text-2xl font-semibold tracking-wide">{report.title}</h3>
        <p className="mt-1 text-sm text-muted-foreground">{report.period}</p>
        <div className="mt-3 flex flex-wrap items-center justify-center gap-2 sm:absolute sm:right-4 sm:top-4 sm:mt-0">
          {isBalance && (
            <span
              className={cn(
                'rounded-md px-2 py-1 text-xs font-medium',
                report.balanced
                  ? 'bg-success text-success-foreground'
                  : 'bg-warning text-warning-foreground',
              )}
              title={t('reports.balanceEquationHint')}
            >
              {report.balanced
                ? `✓ ${t('reports.balanceOk')}`
                : `Δ ${qbNumber(report.imbalance ?? 0)}`}
            </span>
          )}
          <button type="button" className={btnSecondary} onClick={onDownload} disabled={downloading}>
            {downloading ? t('common.loading') : t('reports.downloadExcel')}
          </button>
        </div>
      </div>
      <div className="table-scroll">
        <table className={cn('w-full text-left text-sm', showMonths ? 'min-w-[1100px]' : 'min-w-0')}>
          <thead>
            <tr className="border-b border-border text-muted-foreground">
              <th className="px-4 py-2 font-medium" />
              {showMonths &&
                monthHeaders.map((m) => (
                  <th key={m} className="px-2 py-2 text-right text-xs font-medium">
                    {m}
                  </th>
                ))}
              <th className="px-3 py-2 text-right font-semibold text-foreground sm:px-4">
                {t('reports.totalColumn')}
              </th>
            </tr>
          </thead>
          <tbody>
            {report.rows.map((row, i) => {
              const strong = row.kind === 'total' || row.kind === 'summary'
              const clickable = Boolean(
                onAccountClick && row.kind === 'account' && row.code && !NON_DRILL_CODES.has(row.code),
              )
              const isLast = i === report.rows.length - 1
              return (
                <tr
                  key={`${i}-${row.label}`}
                  className={cn(
                    'transition-colors duration-150',
                    clickable &&
                      'cursor-pointer hover:bg-[color-mix(in_srgb,var(--accent-cream)_10%,transparent)]',
                  )}
                  onClick={clickable ? () => onAccountClick?.(row) : undefined}
                  onKeyDown={
                    clickable
                      ? (e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault()
                            onAccountClick?.(row)
                          }
                        }
                      : undefined
                  }
                  tabIndex={clickable ? 0 : undefined}
                  role={clickable ? 'button' : undefined}
                  title={clickable ? t('reports.drillHint') : undefined}
                >
                  <td
                    className={cn('py-1.5 pr-2', strong && 'font-semibold')}
                    style={{ paddingLeft: `${0.75 + row.depth * 1}rem` }}
                  >
                    {row.label}
                  </td>
                  {showMonths &&
                    MONTH_KEYS.map((mk) => (
                      <td
                        key={mk}
                        className={cn(
                          'px-2 py-1.5 text-right text-xs tabular-nums',
                          strong && 'border-t border-border font-semibold',
                        )}
                      >
                        {row.kind === 'header' ? '' : qbNumber(row.byMonth?.[mk] ?? 0)}
                      </td>
                    ))}
                  <td
                    className={cn(
                      'whitespace-nowrap px-3 py-1.5 text-right tabular-nums sm:px-4',
                      strong && 'border-t border-border font-semibold',
                      isLast && 'border-b-4 border-double border-border',
                    )}
                  >
                    {qbNumber(row.amount)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/** One amount line of the Cash Flow statement. */
function CfAmountRow({
  label,
  amount,
  indentClass = 'pl-6',
  bold = false,
}: {
  label: string
  amount: number
  indentClass?: string
  bold?: boolean
}) {
  return (
    <tr className="border-t border-border/60">
      <td className={cn('px-4 py-1.5', indentClass, bold && 'font-bold')}>{label}</td>
      <td
        className={cn(
          'px-4 py-1.5 text-right tabular-nums',
          bold && 'font-bold',
        )}
      >
        {money(amount)}
      </td>
    </tr>
  )
}

function CashFlowStatement({
  bundle,
  netIncome,
  cfMonthly,
}: {
  bundle: StatementsBundle
  netIncome: number
  cfMonthly: Array<{ period?: string; inflows: number; outflows: number; net: number }>
}) {
  const { t } = useLocale()
  const cf = bundle.cash_flow
  const detail = bundle.cash_flow_detail

  const operatingLines = detail?.operating ?? []
  const investingLines = detail?.investing ?? []
  const financingLines = detail?.financing ?? []

  const operatingNet = Number(cf?.operating?.net ?? 0)
  const opSubtotal = Number(detail?.operatingSubtotal ?? operatingNet)
  const invSubtotal = Number(detail?.investingSubtotal ?? cf?.investing?.net ?? 0)
  const finSubtotal = Number(detail?.financingSubtotal ?? cf?.financing?.net ?? 0)
  const netTotal = Number(detail?.netTotal ?? cf?.netChange ?? 0)

  const showInvesting =
    investingLines.length > 0 || Math.abs(invSubtotal) > 0.0001
  const showFinancing =
    financingLines.length > 0 || Math.abs(finSubtotal) > 0.0001

  function CfDetailRows(lines: PnLLineItem[], indentClass = 'pl-10') {
    if (lines.length === 0) return null
    return lines.map((row) => (
      <tr
        key={`${row.code}-${row.name}`}
        className="border-t border-border/40 hover:bg-[color-mix(in_srgb,var(--accent-cream)_6%,transparent)]"
      >
        <td className={cn('px-4 py-1', indentClass, 'text-sm')}>
          <span className="font-mono text-xs text-muted-foreground">{row.code}</span> {row.name}
        </td>
        <td className="px-4 py-1 text-right tabular-nums text-sm">
          {money(Number(row.amount ?? 0))}
        </td>
      </tr>
    ))
  }

  function CfSectionHeader(title: string) {
    return (
      <tr className="border-t-2 border-border bg-secondary/25">
        <td colSpan={2} className="px-4 py-2 text-xs font-bold tracking-wide">
          {title}
        </td>
      </tr>
    )
  }

  return (
    <div className="space-y-4">
      <div className="table-scroll overflow-hidden rounded-xl border border-border bg-card soft-shadow-lift">
        <div className="border-b border-border px-4 py-3">
          <h3 className="font-display text-lg tracking-wide">{t('reports.cfStatementTitle')}</h3>
        </div>
        <table className="w-full min-w-[360px] text-left text-sm">
          <tbody>
            {CfSectionHeader(t('reports.cfOperatingActivities'))}
            <CfAmountRow label={t('reports.cfNetIncomeLine')} amount={netIncome} />
            <CfAmountRow label={t('reports.cfOperatingNet')} amount={operatingNet} indentClass="pl-8" />
            {CfDetailRows(operatingLines)}
            <CfAmountRow
              label={t('reports.cfNetCashOperating')}
              amount={opSubtotal}
              indentClass="pl-6"
              bold
            />

            {showInvesting && (
              <>
                {CfSectionHeader(t('reports.cfInvestingActivities'))}
                {CfDetailRows(investingLines, 'pl-6')}
                {investingLines.length === 0 && (
                  <CfAmountRow label={t('reports.emptySection')} amount={invSubtotal} indentClass="pl-6" />
                )}
                <CfAmountRow
                  label={t('reports.cfNetCashInvesting')}
                  amount={invSubtotal}
                  indentClass="pl-6"
                  bold
                />
              </>
            )}

            {showFinancing && (
              <>
                {CfSectionHeader(t('reports.cfFinancingActivities'))}
                {CfDetailRows(financingLines, 'pl-6')}
                {financingLines.length === 0 && (
                  <CfAmountRow label={t('reports.emptySection')} amount={finSubtotal} indentClass="pl-6" />
                )}
                <CfAmountRow
                  label={t('reports.cfNetCashFinancing')}
                  amount={finSubtotal}
                  indentClass="pl-6"
                  bold
                />
              </>
            )}

            <tr className="border-t-2 border-border bg-[color-mix(in_srgb,var(--accent-cream)_25%,var(--bg-card))]">
              <td className="px-4 py-3 font-display text-sm font-bold tracking-wide">
                {t('reports.cfNetIncreasePeriod')}
              </td>
              <td className="px-4 py-3 text-right font-bold tabular-nums">{money(netTotal)}</td>
            </tr>
          </tbody>
        </table>
      </div>

      {cfMonthly.length > 0 && (
        <div className="h-44 rounded-xl border border-border bg-background p-3 soft-shadow-lift">
          <h4 className="mb-1 text-xs font-semibold text-muted-foreground">
            {t('reports.cfMonthly')} — <span className="text-[var(--positive)]">■</span> /{' '}
            <span className="text-[var(--negative)]">■</span>
          </h4>
          <ResponsiveContainer width="100%" height="85%">
            <BarChart data={cfMonthly} stackOffset="sign">
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="period" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} width={48} />
              <Tooltip
                formatter={(v) => money(Number(v ?? 0))}
                contentStyle={{
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border)',
                  borderRadius: 8,
                }}
              />
              <Bar dataKey="inflows" name="In" stackId="cf" fill="var(--positive)" radius={[4, 4, 0, 0]} />
              <Bar dataKey="outflows" name="Out" stackId="cf" fill="var(--negative)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

export default function Reports() {
  const { workspaceId = '' } = useParams()
  const { t, locale } = useLocale()
  const monthLabels = shortMonthLabels(locale)
  const [periods, setPeriods] = useState<Period[]>([])
  const [bundle, setBundle] = useState<StatementsBundle | null>(null)
  const [availableYears, setAvailableYears] = useState<string[]>([])
  const [fiscalYear, setFiscalYear] = useState('')
  const [month, setMonth] = useState<string>('') // '' = Jan–Dec columns for that year
  const [showMonths, setShowMonths] = useState(false) // QuickBooks template = single Total column
  const [downloading, setDownloading] = useState<QbReportKey | 'package' | null>(null)
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
  const [drillAccount, setDrillAccount] = useState<PnLLineItem | null>(null)
  const [drillTxs, setDrillTxs] = useState<Transaction[]>([])
  const [drillLoading, setDrillLoading] = useState(false)
  const [drillError, setDrillError] = useState<string | null>(null)

  const loadMeta = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [periodsData, yearsData, avail, workspace] = await Promise.all([
        api.listPeriods({ workspace_id: workspaceId }),
        api.listFiscalYears(workspaceId),
        api.availableYears(workspaceId),
        api.getWorkspace(workspaceId).catch(() => null),
      ])
      setPeriods(Array.isArray(periodsData) ? periodsData : [])
      setFiscalYears(Array.isArray(yearsData.years) ? yearsData.years : [])
      const ceiling =
        workspace?.max_fiscal_year != null && !Number.isNaN(Number(workspace.max_fiscal_year))
          ? Number(workspace.max_fiscal_year)
          : 2025
      // Prefer all discovered years (docs/Drive/txs); verified_years alone hid 2024
      const rawYears = avail.years?.length
        ? avail.years
        : avail.verified_years?.length
          ? avail.verified_years
          : []
      const years = rawYears.filter((y) => {
        const n = Number(y)
        return !Number.isNaN(n) && n <= ceiling
      })
      setAvailableYears(years)
      // CPA: 2025 and below, month columns — never a lump of every year
      const def =
        years.includes('2025')
          ? '2025'
          : avail.default_year && years.includes(String(avail.default_year))
            ? String(avail.default_year)
            : years[0] || String(Math.min(ceiling, new Date().getFullYear()))
      setFiscalYear((prev) => {
        if (prev && years.includes(prev)) return prev
        return String(def)
      })
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
  const revTotal = Number(displayPnl?.totalRevenue ?? 0)
  const expTotal = Number(displayPnl?.totalExpenses ?? 0)
  const net = Number(displayPnl?.netIncome ?? revTotal - expTotal)
  const qb = bundle?.qb ?? null

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
  const reportParams = {
    workspace_id: workspaceId,
    fiscal_year: fiscalYear || undefined,
    month: month ? Number(month) : undefined,
  }

  async function download(kind: QbReportKey | 'package') {
    setDownloading(kind)
    setError(null)
    try {
      if (kind === 'package') await api.downloadStatementsPackage(reportParams)
      else await api.downloadQbReport(kind, reportParams)
    } catch (e) {
      setError(e instanceof Error ? e.message : t('common.error'))
    } finally {
      setDownloading(null)
    }
  }

  const drillDateFrom = useMemo(() => {
    if (!fiscalYear) return undefined
    if (month) return `${fiscalYear}-${month}-01`
    return `${fiscalYear}-01-01`
  }, [fiscalYear, month])

  const drillDateTo = useMemo(() => {
    if (!fiscalYear) return undefined
    if (month) {
      const y = Number(fiscalYear)
      const m = Number(month)
      const last = new Date(y, m, 0).getDate()
      return `${fiscalYear}-${month}-${String(last).padStart(2, '0')}`
    }
    return `${fiscalYear}-12-31`
  }, [fiscalYear, month])

  const openPnLDrill = useCallback(
    async (row: QbRow) => {
      if (!row.code || !workspaceId || !fiscalYear) return
      setDrillAccount({ code: row.code, name: row.label })
      setDrillLoading(true)
      setDrillError(null)
      setDrillTxs([])
      try {
        const txs = await api.listTransactions({
          tenant_id: workspaceId,
          account_code: String(row.code),
          date_from: drillDateFrom,
          date_to: drillDateTo,
          status: 'verified,closed',
          limit: 2000,
        })
        const rows = Array.isArray(txs) ? txs : []
        setDrillTxs(rows)
      } catch (e) {
        setDrillError(e instanceof Error ? e.message : t('common.error'))
      } finally {
        setDrillLoading(false)
      }
    },
    [workspaceId, fiscalYear, drillDateFrom, drillDateTo, t],
  )

  function closePnLDrill() {
    setDrillAccount(null)
    setDrillTxs([])
    setDrillError(null)
  }

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
        <h2 className="mb-1 font-display text-xl tracking-wide">{t('reports.statementsTitle')}</h2>
        <p className="mb-4 text-sm text-muted-foreground">{t('reports.statementsHint')}</p>

        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
          <label className="w-full text-sm sm:w-auto">
            {t('reports.year')}
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
            {t('reports.month')}
            <select
              className="mt-1 block w-full rounded-lg border border-border bg-background px-3 py-2 sm:w-40"
              value={month}
              onChange={(e) => setMonth(e.target.value)}
            >
              <option value="">{t('reports.monthAll')}</option>
              {monthLabels.map((label, i) => (
                <option key={MONTH_KEYS[i]} value={MONTH_KEYS[i]}>
                  {label} ({MONTH_KEYS[i]})
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
              {loadingStmt ? t('common.loading') : t('reports.refresh')}
            </button>
            <button
              type="button"
              className={cn(btnSecondary, 'flex-1 sm:flex-none')}
              onClick={() => void download('package')}
              disabled={downloading !== null || !fiscalYear}
              title={t('reports.packageHint')}
            >
              {downloading === 'package' ? t('common.loading') : t('reports.downloadPackage')}
            </button>
            <button
              type="button"
              className={cn(btnSecondary, 'flex-1 sm:flex-none')}
              onClick={() => setShowMonths((v) => !v)}
              aria-pressed={showMonths}
            >
              {showMonths ? t('reports.columnsTotal') : t('reports.columnsMonthly')}
            </button>
          </div>
        </div>

        <p className="mb-4 text-xs text-muted-foreground">{t('reports.layoutHint')}</p>
        {bundle && (
          <p className="mb-4 text-xs text-muted-foreground">
            {bundle.period_label} · {bundle.transaction_count ?? 0} {t('reports.verifiedTxs')}
            {(bundle.pending_count ?? 0) > 0 && (
              <>
                {' '}
                ·{' '}
                <Link
                  to={`/app/${workspaceId}/transactions`}
                  className="text-primary underline-offset-2 hover:underline"
                >
                  {bundle.pending_count} {t('reports.pendingReview')}
                </Link>
              </>
            )}{' '}
            · {bundle.engine}
          </p>
        )}

        {bundle && (bundle.transaction_count ?? 0) === 0 && (
          <div className="mb-4 rounded-lg border border-warning/40 bg-warning/10 px-4 py-3 text-sm">
            {t('reports.emptyPeriod').replace('{period}', periodLabel)}
            {(bundle.pending_count ?? 0) > 0 ? (
              <>
                {' '}
                {t('reports.emptyPendingHint').replace('{n}', String(bundle.pending_count))}{' '}
                <Link className="underline" to={`/app/${workspaceId}/transactions`}>
                  {t('nav.transactions')}
                </Link>
              </>
            ) : (
              <> {t('reports.emptyImportHint')}</>
            )}
          </div>
        )}

        {/* ── QuickBooks reports (template layout) ───────────────────────── */}
        {displayPnl && (
          <div className="mb-6 grid gap-4 sm:grid-cols-3">
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
        )}

        {qb && (
          <div className="mb-8 space-y-6">
            <QbReportCard
              company={qb.company}
              report={qb.profit_and_loss}
              showMonths={showMonths}
              fiscalYear={fiscalYear}
              onAccountClick={(row) => void openPnLDrill(row)}
              onDownload={() => void download('profit-and-loss')}
              downloading={downloading === 'profit-and-loss'}
            />
          </div>
        )}

        {/* ── Balance chain alerts ────────────────────────────────────────── */}
        {bundle?.balance_chain_alerts && bundle.balance_chain_alerts.length > 0 && (
          <div className="mb-6 rounded-xl border border-destructive/40 bg-destructive/10 p-4">
            <h3 className="mb-2 font-semibold text-destructive">{t('reports.chainAlerts')}</h3>
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
                      {t('reports.ackChain')}
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        {qb && (
          <div className="mb-8">
            <QbReportCard
              company={qb.company}
              report={qb.balance_sheet}
              showMonths={showMonths}
              fiscalYear={fiscalYear}
              onAccountClick={(row) => void openPnLDrill(row)}
              onDownload={() => void download('balance-sheet')}
              downloading={downloading === 'balance-sheet'}
            />
            <p className="mt-2 text-xs text-muted-foreground">{t('reports.balanceSheetHint')}</p>
          </div>
        )}

        {/* ── Cash flow ───────────────────────────────────────────────────── */}
        {bundle?.cash_flow && (
          <div className="mb-6">
            <CashFlowStatement bundle={bundle} netIncome={net} cfMonthly={cfMonthly} />
          </div>
        )}
      </section>

      {drillAccount && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center"
          role="dialog"
          aria-modal="true"
          aria-labelledby="pnl-drill-title"
          onClick={closePnLDrill}
        >
          <div
            className="max-h-[85vh] w-full max-w-3xl overflow-hidden rounded-xl border border-border bg-card soft-shadow-lift"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
              <div>
                <h3 id="pnl-drill-title" className="font-display text-lg tracking-wide">
                  {t('reports.pnlDetail')}
                </h3>
                <p className="mt-0.5 text-sm text-muted-foreground">
                  <span className="font-mono text-xs">{drillAccount.code}</span> ·{' '}
                  {drillAccount.name} · {periodLabel}
                </p>
              </div>
              <button type="button" className={btnSecondary} onClick={closePnLDrill}>
                {t('common.cancel')}
              </button>
            </div>
            <div className="table-scroll max-h-[60vh] overflow-auto p-2">
              {drillLoading && (
                <p className="px-3 py-6 text-sm text-muted-foreground">{t('common.loading')}</p>
              )}
              {drillError && (
                <p className="px-3 py-4 text-sm text-destructive">{drillError}</p>
              )}
              {!drillLoading && !drillError && drillTxs.length === 0 && (
                <p className="px-3 py-6 text-sm text-muted-foreground">{t('reports.drillEmpty')}</p>
              )}
              {!drillLoading && drillTxs.length > 0 && (
                <table className="w-full min-w-[520px] text-left text-sm">
                  <thead className="bg-secondary/40 text-muted-foreground">
                    <tr>
                      <th className="px-3 py-2 font-medium">{t('transactions.date')}</th>
                      <th className="px-3 py-2 font-medium">{t('transactions.description')}</th>
                      <th className="px-3 py-2 font-medium">{t('transactions.vendor')}</th>
                      <th className="px-3 py-2 text-right font-medium">{t('transactions.amount')}</th>
                      <th className="px-3 py-2 font-medium">{t('transactions.status')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {drillTxs.map((tx) => (
                      <tr key={tx.id} className="border-t border-border">
                        <td className="px-3 py-2 whitespace-nowrap text-xs">
                          {String(tx.date ?? tx.transaction_date ?? '—').slice(0, 10)}
                        </td>
                        <td className="px-3 py-2">{tx.description ?? '—'}</td>
                        <td className="px-3 py-2 text-muted-foreground">
                          {tx.vendor ?? tx.vendor_name ?? '—'}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">
                          {money(Number(tx.amount ?? 0))}
                        </td>
                        <td className="px-3 py-2 text-xs capitalize">{tx.status ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border px-4 py-3">
              <p className="text-xs text-muted-foreground">
                {drillTxs.length} {t('reports.txCount')}
              </p>
              <Link
                to={`/app/${workspaceId}/transactions`}
                className={cn(btnPrimary, 'text-center')}
                onClick={closePnLDrill}
              >
                {t('reports.viewInTransactions')}
              </Link>
            </div>
          </div>
        </div>
      )}

      <section className="mb-8">
        <h2 className="mb-3 font-display text-xl tracking-wide">{t('reports.yearClose')}</h2>
        <p className="mb-3 max-w-2xl text-sm text-muted-foreground">{t('reports.yearCloseHint')}</p>
        <div className="mb-4 flex flex-wrap items-end gap-3">
          <label className="text-sm">
            {t('reports.year')}
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
            {closingYear
              ? t('common.loading')
              : t('reports.closeYear').replace('{year}', yearInput)}
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
                    {t('reports.reopenYear')}
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
                    {t('reports.viewPeriod')}
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
