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
      setLoading(true)
      setError(null)
      try {
        const [data, ws, docs] = await Promise.all([
          api.getWorkspaceStats(workspaceId),
          api.getWorkspace(workspaceId).catch(() => null),
          api.listDocuments({ workspace_id: workspaceId }).catch(() => []),
        ])
        if (cancelled) return
        setStats(data)
        setWorkspace(ws)
        const list = Array.isArray(docs) ? docs : []
        setDocSummary({
          total: list.length,
          processing: list.filter((d) => d.status === 'processing').length,
          extracted: list.filter((d) => d.status === 'extracted').length,
          failed: list.filter((d) => d.status === 'failed').length,
          statements: list.filter((d) => d.pipeline_kind === 'statement').length,
          invoices: list.filter((d) => d.pipeline_kind === 'invoice').length,
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
  }, [workspaceId, t])

  const income = Number(stats?.totalIncome ?? 0)
  const expenses = Number(stats?.totalExpenses ?? 0)
  const net = Number(stats?.netIncome ?? income - expenses)
  const pending = Number(stats?.pending_transactions ?? 0)
  const verified = Number(stats?.verified_transactions ?? 0)

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
      <div className="mb-8 animate-fade-up">
        <h1 className="page-title">{t('dashboard.title')}</h1>
        <p className="mt-1.5 text-muted-foreground">
          {workspace?.name
            ? `${workspace.name} · ${t('dashboard.subtitle')}`
            : t('dashboard.subtitle')}
        </p>
      </div>

      {loading && <p className="text-muted-foreground">{t('common.loading')}</p>}
      {error && (
        <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
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
        <p className="mt-4 text-xs text-muted-foreground">
          Estado de cuenta → Conciliación. Factura → Transacciones (revisar / aprobar). Luego emitir
          estados en Reportes.
        </p>
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
              <p className="text-2xl font-semibold tracking-tight tabular-nums">{kpi.value}</p>
              <p className="mt-1 text-sm text-muted-foreground">{kpi.label}</p>
            </div>
          )
        })}
      </div>

      <div className="mb-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        {kpis.map(({ label, value, icon: Icon, to }, i) => (
          <Link
            key={label}
            to={`/app/${workspaceId}/${to}`}
            className={cn(
              'soft-shadow group rounded-xl border border-border bg-card p-4 transition hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-[var(--shadow-lift)]',
              delayClass[Math.min(i, 3)],
            )}
          >
            <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg bg-secondary text-primary transition group-hover:bg-primary/10">
              <Icon className="h-4 w-4" />
            </div>
            <p className="text-2xl font-semibold tabular-nums">{value}</p>
            <p className="text-sm text-muted-foreground">{label}</p>
          </Link>
        ))}
      </div>

      <div className="mb-8 grid gap-4 lg:grid-cols-5">
        <section className="animate-fade-up-delay-2 soft-shadow rounded-xl border border-border bg-card p-5 sm:p-6 lg:col-span-3">
          <h2 className="mb-1 text-lg font-semibold tracking-tight">{t('dashboard.chartTitle')}</h2>
          <p className="mb-4 text-sm text-foreground/75">
            {t('dashboard.chartSubtitle')}
          </p>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={barData}
                layout="vertical"
                margin={{ top: 8, right: 16, left: 8, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
                <XAxis
                  type="number"
                  tick={{ fontSize: 12, fill: 'var(--chart-tick)' }}
                  stroke="var(--chart-tick)"
                />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={96}
                  tick={{ fontSize: 12, fill: 'var(--chart-tick)', fontWeight: 600 }}
                  stroke="var(--chart-tick)"
                />
                <Tooltip
                  formatter={(value) => formatMoney(Number(value ?? 0), locale)}
                  labelStyle={{ color: 'var(--chart-tooltip-fg)', fontWeight: 600 }}
                  itemStyle={{ color: 'var(--chart-tooltip-fg)' }}
                  contentStyle={{
                    borderRadius: 8,
                    border: '1px solid var(--chart-tooltip-border)',
                    background: 'var(--chart-tooltip-bg)',
                    color: 'var(--chart-tooltip-fg)',
                    boxShadow: 'var(--shadow-lift)',
                  }}
                />
                <Bar dataKey="valor" radius={[0, 6, 6, 0]} maxBarSize={28}>
                  {barData.map((entry) => (
                    <Cell key={entry.name} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="animate-fade-up-delay-3 soft-shadow rounded-xl border border-border bg-card p-5 sm:p-6 lg:col-span-2">
          <h2 className="mb-1 text-lg font-semibold tracking-tight">Composición</h2>
          <p className="mb-4 text-sm text-muted-foreground">Peso ingresos vs gastos.</p>
          <div className="h-64 w-full">
            {pieData.length === 0 ? (
              <p className="flex h-full items-center justify-center text-sm text-muted-foreground">
                Sin montos verificados aún
              </p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={pieData}
                    dataKey="value"
                    nameKey="name"
                    innerRadius={58}
                    outerRadius={88}
                    paddingAngle={3}
                  >
                    {pieData.map((_, i) => (
                      <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value) => formatMoney(Number(value ?? 0), locale)} />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>
        </section>
      </div>

      <section className="animate-fade-up-delay-3">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
          <h2 className="text-lg font-semibold tracking-tight">{t('dashboard.pipeline')}</h2>
          {showClearHint && (
            <p className="text-xs text-muted-foreground">{t('dashboard.stage.clearHint')}</p>
          )}
        </div>
        <div className="grid gap-3 md:grid-cols-5">
          {stages.map((stage, i) => {
            const isActive = i === (activeStage >= 0 ? activeStage : 0)
            const clearGood = Boolean(stage.clearIsGood) && stage.count === 0 && verified > 0
            const to = `/app/${workspaceId}/${STAGE_ROUTES[i]}`
            return (
              <Link
                key={stage.key}
                to={to}
                title={t('dashboard.stage.open')}
                className={cn(
                  'soft-shadow relative block rounded-xl border bg-card p-4 transition hover:-translate-y-0.5 hover:border-primary/40',
                  isActive
                    ? 'border-primary/50 pipeline-pulse'
                    : 'border-border hover:border-primary/25',
                )}
              >
                <div className="mb-2 flex items-center justify-between">
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    {String(i + 1).padStart(2, '0')}
                  </p>
                  {isActive && <span className="h-1.5 w-1.5 rounded-full bg-primary" />}
                </div>
                <p className="font-medium">{t(stage.key)}</p>
                <p
                  className={cn(
                    'mt-3 text-2xl font-semibold tabular-nums',
                    clearGood ? 'text-success-foreground' : isActive ? 'text-primary' : 'text-foreground',
                  )}
                >
                  {stage.count}
                </p>
                {clearGood && (
                  <p className="mt-1 text-[11px] text-success-foreground/80">{t('dashboard.stage.clear')}</p>
                )}
              </Link>
            )
          })}
        </div>
      </section>
    </div>
  )
}
