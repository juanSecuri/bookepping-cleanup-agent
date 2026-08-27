import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  FileText,
  Clock,
  CheckCircle2,
  XCircle,
  Unlink,
  TrendingUp,
  TrendingDown,
  Wallet,
  HardDrive,
  ScanText,
  BookOpen,
  Landmark,
  LineChart,
} from 'lucide-react'
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  PieChart,
  Pie,
  Cell,
} from 'recharts'
import { api, type Workspace, type WorkspaceStats } from '../../lib/api'
import { useLocale } from '../../i18n'
import { cn } from '../../lib/utils'

function formatMoney(n: number, locale: string) {
  return new Intl.NumberFormat(locale === 'es' ? 'es-CO' : 'en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(n)
}

const STAGE_ROUTES = [
  'documents',
  'documents',
  'transactions',
  'reconciliation',
  'reports',
] as const

const PIE_COLORS = ['#DCD0B9', '#0D3D33']

export default function Dashboard() {
  const { workspaceId = '' } = useParams()
  const { t, locale } = useLocale()
  const [stats, setStats] = useState<WorkspaceStats | null>(null)
  const [workspace, setWorkspace] = useState<Workspace | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [years, setYears] = useState<string[]>([])
  const [fiscalYear, setFiscalYear] = useState('')
  const [docSummary, setDocSummary] = useState({
    total: 0,
    processing: 0,
    extracted: 0,
    failed: 0,
    statements: 0,
    invoices: 0,
  })

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const avail = await api.availableYears(workspaceId)
        if (cancelled) return
        const ys = avail.years?.length
          ? avail.years
          : avail.verified_years?.length
            ? avail.verified_years
            : []
        setYears(ys)
        const def =
          avail.default_year && ys.includes(String(avail.default_year))
            ? String(avail.default_year)
            : ys[0] || ''
        setFiscalYear((prev) => prev || def)
      } catch {
        if (!cancelled) setYears([])
      }
    })()
    return () => {
      cancelled = true
    }
  }, [workspaceId])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setError(null)
      try {
        const [data, ws, docs] = await Promise.all([
          api.getWorkspaceStats(
            workspaceId,
            fiscalYear ? { fiscal_year: fiscalYear } : undefined,
          ),
          api.getWorkspace(workspaceId).catch(() => null),
          api.listDocuments({ workspace_id: workspaceId }).catch(() => []),
        ])
        if (cancelled) return
        setStats(data)
        setWorkspace(ws)
        const list = Array.isArray(docs) ? docs : []
        const yearDocs = fiscalYear
          ? list.filter((d) => {
              const hay = [d.folder_group, d.drive_path, d.filename, d.name]
                .filter(Boolean)
                .join('/')
              return hay.includes(fiscalYear)
            })
          : list
        setDocSummary({
          total: yearDocs.length,
          processing: yearDocs.filter((d) => d.status === 'processing').length,
          extracted: yearDocs.filter((d) => d.status === 'extracted').length,
          failed: yearDocs.filter((d) => d.status === 'failed').length,
          statements: yearDocs.filter((d) => d.pipeline_kind === 'statement').length,
          invoices: yearDocs.filter((d) => d.pipeline_kind === 'invoice').length,
        })
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : t('common.error'))
          setStats({})
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [workspaceId, fiscalYear, t])

  const income = Number(stats?.totalIncome ?? 0)
  const expenses = Number(stats?.totalExpenses ?? 0)
  const net = Number(stats?.netIncome ?? income - expenses)
  const pending = Number(stats?.pending_transactions ?? 0)
  const verified = Number(stats?.verified_transactions ?? 0)
  const pendingIncome = Number(stats?.pendingIncome ?? 0)
  const pendingExpenses = Number(stats?.pendingExpenses ?? 0)
  const extractedDocs = Number(stats?.extractedDocs ?? docSummary.extracted ?? 0)
  const showEmptyYearHint =
    Boolean(fiscalYear) &&
    income === 0 &&
    expenses === 0 &&
    (pending > 0 || extractedDocs > 0)

  const kpis = [
    {
      label: t('dashboard.documents'),
      value: Number(stats?.documents ?? docSummary.total ?? 0),
      icon: FileText,
      to: 'documents',
    },
    {
      label: t('dashboard.pending'),
      value: pending,
      icon: Clock,
      to: 'transactions',
    },
    {
      label: t('dashboard.verified'),
      value: verified,
      icon: CheckCircle2,
      to: 'transactions',
    },
    {
      label: t('dashboard.rejected'),
      value: Number(stats?.rejected_transactions ?? 0),
      icon: XCircle,
      to: 'transactions',
    },
    {
      label: t('dashboard.unmatched'),
      value: Number(stats?.unmatched_movements ?? 0),
      icon: Unlink,
      to: 'reconciliation',
    },
  ]

  const moneyKpis = [
    {
      label: t('dashboard.income'),
      value: formatMoney(income, locale),
      icon: TrendingUp,
      tone: 'text-success-foreground',
      bg: 'bg-success',
    },
    {
      label: t('dashboard.expenses'),
      value: formatMoney(expenses, locale),
      icon: TrendingDown,
      tone: 'text-destructive',
      bg: 'bg-destructive/15',
    },
    {
      label: t('dashboard.net'),
      value: formatMoney(net, locale),
      icon: Wallet,
      tone: net >= 0 ? 'text-primary' : 'text-destructive',
      bg: net >= 0 ? 'bg-primary/10' : 'bg-destructive/15',
    },
  ]

  const stages = [
    {
      key: 'dashboard.stage.ingest',
      count: Number(stats?.documents ?? docSummary.total ?? 0),
      backlog: Number(stats?.documents ?? 0) === 0,
    },
    {
      key: 'dashboard.stage.classify',
      count: pending,
      backlog: pending > 0,
      clearIsGood: true,
    },
    {
      key: 'dashboard.stage.review',
      count: pending,
      backlog: pending > 0,
      clearIsGood: true,
    },
    {
      key: 'dashboard.stage.reconcile',
      count: Number(stats?.unmatched_movements ?? 0),
      backlog: Number(stats?.unmatched_movements ?? 0) > 0,
    },
    {
      key: 'dashboard.stage.close',
      count: Number(stats?.periods_open ?? 0),
      backlog: Number(stats?.periods_open ?? 0) > 0,
    },
  ]

  const activeStage = stages.findIndex((s) => s.backlog)
  const showClearHint = verified > 0 && pending === 0

  const barData = [
    {
      name: t('dashboard.income'),
      valor: income,
      fill: '#DCD0B9',
    },
    {
      name: t('dashboard.expenses'),
      valor: expenses,
      fill: '#3d5c52',
    },
    {
      name: t('dashboard.net'),
      valor: Math.abs(net),
      fill: net >= 0 ? '#6fa98c' : '#c45c5c',
    },
  ]

  const pieData = [
    { name: t('dashboard.income'), value: Math.max(income, 0) },
    { name: t('dashboard.expenses'), value: Math.max(expenses, 0) },
  ].filter((d) => d.value > 0)

  const delayClass = [
    'animate-fade-up-delay-1',
    'animate-fade-up-delay-2',
    'animate-fade-up-delay-3',
    'animate-fade-up-delay-4',
  ] as const

  const agentSteps = [
    {
      icon: HardDrive,
      title: t('dashboard.step1Title'),
      body: t('dashboard.step1Body'),
    },
    {
      icon: ScanText,
      title: t('dashboard.step2Title'),
      body: t('dashboard.step2Body'),
    },
    {
      icon: BookOpen,
      title: t('dashboard.step3Title'),
      body: t('dashboard.step3Body'),
    },
    {
      icon: Landmark,
      title: t('dashboard.step4Title'),
      body: t('dashboard.step4Body'),
    },
    {
      icon: LineChart,
      title: t('dashboard.step5Title'),
      body: t('dashboard.step5Body'),
    },
  ]

  return (
    <div>
      <div className="mb-8 animate-fade-up flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="page-title">{t('dashboard.title')}</h1>
          <p className="mt-1.5 text-muted-foreground">
            {workspace?.name
              ? `${workspace.name} · ${t('dashboard.subtitle')}`
              : t('dashboard.subtitle')}
          </p>
        </div>
        <label className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
          {t('dashboard.year')}
          <select
            className="min-w-[7rem] rounded-md border border-border bg-card px-3 py-2 text-sm font-semibold text-foreground"
            value={fiscalYear}
            onChange={(e) => setFiscalYear(e.target.value)}
          >
            <option value="">{t('dashboard.yearAll')}</option>
            {years.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </label>
      </div>

      {loading && <p className="text-muted-foreground">{t('common.loading')}</p>}
      {error && (
        <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {showEmptyYearHint && (
        <div className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-foreground">
          {t('dashboard.emptyYearHint')
            .replace('{year}', fiscalYear)
            .replace('{extracted}', String(extractedDocs))
            .replace('{pending}', String(pending))}{' '}
          <Link className="font-semibold underline-offset-2 hover:underline" to="transactions">
            {t('nav.transactions')}
          </Link>
          {' · '}
          <Link className="font-semibold underline-offset-2 hover:underline" to="reports">
            {t('nav.reports')}
          </Link>
        </div>
      )}

      {(pendingIncome > 0 || pendingExpenses > 0) && (
        <p className="mb-4 text-xs text-muted-foreground">
          {t('dashboard.pendingMoneyHint')
            .replace('{income}', formatMoney(pendingIncome, locale))
            .replace('{expenses}', formatMoney(pendingExpenses, locale))}
        </p>
      )}

      <section className="animate-fade-up-delay-1 soft-shadow mb-6 rounded-xl border border-border bg-card p-5 sm:p-6">
        <h2 className="mb-1 text-lg font-semibold tracking-tight">{t('dashboard.agentTitle')}</h2>
        <p className="mb-4 text-sm text-muted-foreground">
          {t('dashboard.agentIntro')}{' '}
          <strong className="font-semibold text-foreground">{docSummary.total} docs</strong>
          {docSummary.processing > 0 && (
            <>
              {' '}
              · <span className="text-primary">{docSummary.processing} extrayendo</span>
            </>
          )}
          {docSummary.extracted > 0 && (
            <>
              {' '}
              · <span className="text-success-foreground">{docSummary.extracted} listos</span>
            </>
          )}
          {docSummary.statements + docSummary.invoices > 0 && (
            <>
              {' '}
              · {docSummary.statements} estados / {docSummary.invoices} facturas
            </>
          )}
          .
        </p>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          {agentSteps.map((step) => {
            const Icon = step.icon
            return (
              <div
                key={step.title}
                className="rounded-lg border border-border/80 bg-secondary/30 p-3"
              >
                <div className="mb-2 flex h-8 w-8 items-center justify-center rounded-md bg-primary/10 text-primary">
                  <Icon className="h-4 w-4" />
                </div>
                <p className="text-sm font-semibold">{step.title}</p>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{step.body}</p>
              </div>
            )
          })}
        </div>
        <p className="mt-4 text-xs text-muted-foreground">{t('dashboard.pipelineHint')}</p>
      </section>

      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        {moneyKpis.map((kpi, i) => {
          const Icon = kpi.icon
          return (
            <div
              key={kpi.label}
              className={cn(
                'soft-shadow rounded-xl border border-border bg-card p-5 transition hover:border-primary/30',
                delayClass[i] ?? 'animate-fade-up',
              )}
            >
              <div className={cn('mb-3 flex h-9 w-9 items-center justify-center rounded-lg', kpi.bg, kpi.tone)}>
                <Icon className="h-4 w-4" />
              </div>
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {kpi.label}
                {fiscalYear ? ` · ${fiscalYear}` : ''}
              </p>
              <p className="mt-1 font-display text-2xl font-semibold tracking-tight">{kpi.value}</p>
            </div>
          )
        })}
      </div>

      <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {kpis.map((kpi, i) => {
          const Icon = kpi.icon
          return (
            <Link
              key={kpi.label}
              to={kpi.to}
              className={cn(
                'soft-shadow rounded-xl border border-border bg-card p-4 transition hover:border-primary/40',
                delayClass[i % 4] ?? 'animate-fade-up',
              )}
            >
              <div className="mb-2 flex items-center gap-2 text-muted-foreground">
                <Icon className="h-4 w-4" />
                <span className="text-xs font-medium uppercase tracking-wide">{kpi.label}</span>
              </div>
              <p className="font-display text-2xl font-semibold">{kpi.value}</p>
            </Link>
          )
        })}
      </div>

      {showClearHint && (
        <p className="mb-4 text-sm text-success-foreground">{t('dashboard.clearHint')}</p>
      )}

      {activeStage >= 0 && (
        <p className="mb-6 text-sm text-muted-foreground">
          {t('dashboard.focusHint')}{' '}
          <Link className="font-medium text-primary underline-offset-2 hover:underline" to={STAGE_ROUTES[activeStage]}>
            {t(stages[activeStage].key)}
          </Link>
        </p>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="soft-shadow animate-fade-up-delay-2 rounded-xl border border-border bg-card p-5">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            {t('dashboard.chartIncomeExpense')}
          </h2>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={barData}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="name" tick={{ fill: 'var(--muted-foreground)', fontSize: 12 }} />
                <YAxis tick={{ fill: 'var(--muted-foreground)', fontSize: 12 }} />
                <Tooltip />
                <Legend />
                <Bar dataKey="valor" name={t('dashboard.amount')} radius={[4, 4, 0, 0]}>
                  {barData.map((entry) => (
                    <Cell key={entry.name} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="soft-shadow animate-fade-up-delay-3 rounded-xl border border-border bg-card p-5">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            {t('dashboard.chartMix')}
          </h2>
          <div className="h-56">
            {pieData.length === 0 ? (
              <p className="flex h-full items-center justify-center text-sm text-muted-foreground">
                {t('dashboard.noVerifiedMoney')}
              </p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={pieData} dataKey="value" nameKey="name" innerRadius={50} outerRadius={80}>
                    {pieData.map((_, i) => (
                      <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
