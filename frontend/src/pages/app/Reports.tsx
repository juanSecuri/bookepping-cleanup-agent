import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, type Period, type PnLReport } from '../../lib/api'
import { useLocale } from '../../i18n'
import { cn } from '../../lib/utils'

function periodClosed(p: Period): boolean {
  const s = String(p.status ?? '').toLowerCase()
  return s === 'closed' || Boolean(p.closed_at)
}

export default function Reports() {
  const { workspaceId = '' } = useParams()
  const { t } = useLocale()
  const [periods, setPeriods] = useState<Period[]>([])
  const [pnl, setPnl] = useState<PnLReport | null>(null)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [loading, setLoading] = useState(true)
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
    { name: t('reports.revenue'), value: Number(pnl?.revenue ?? 0) },
    { name: t('reports.expenses'), value: Number(pnl?.expenses ?? 0) },
    { name: t('reports.net'), value: Number(pnl?.net_income ?? 0) },
  ]

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

      <section>
        <h2 className="mb-2 text-lg font-semibold tracking-tight">{t('reports.pnl')}</h2>
        <p className="mb-4 max-w-3xl text-sm leading-relaxed text-muted-foreground">
          {t('reports.pnlExplain')}
        </p>
        <div className="mb-4 flex flex-wrap items-end gap-3">
          <label className="text-sm">
            {t('reports.from')}
            <input
              type="date"
              className="mt-1 block rounded-lg border border-border bg-card px-3 py-2"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
            />
          </label>
          <label className="text-sm">
            {t('reports.to')}
            <input
              type="date"
              className="mt-1 block rounded-lg border border-border bg-card px-3 py-2"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
            />
          </label>
          <button
            type="button"
            onClick={() => void loadPnl()}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground"
          >
            {t('reports.load')}
          </button>
        </div>

        {!pnl && (
          <div className="soft-shadow rounded-xl border border-border bg-card px-6 py-8 text-center">
            <p className="text-sm text-muted-foreground">{t('reports.pnlEmpty')}</p>
          </div>
        )}

        {pnl && (
          <>
            <div className="mb-6 grid gap-4 sm:grid-cols-3">
              {[
                { label: t('reports.revenue'), value: pnl.revenue, tone: 'text-emerald-700' },
                { label: t('reports.expenses'), value: pnl.expenses, tone: 'text-rose-700' },
                { label: t('reports.net'), value: pnl.net_income, tone: 'text-amber-700' },
              ].map((kpi) => (
                <div
                  key={kpi.label}
                  className="soft-shadow rounded-xl border border-border bg-card p-4"
                >
                  <p className="text-sm text-muted-foreground">{kpi.label}</p>
                  <p className={cn('mt-1 text-2xl font-semibold tabular-nums', kpi.tone)}>
                    {Number(kpi.value ?? 0).toLocaleString(undefined, {
                      style: 'currency',
                      currency: 'USD',
                    })}
                  </p>
                </div>
              ))}
            </div>
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
          </>
        )}

        <div className="mt-8 rounded-xl border border-dashed border-border bg-secondary/30 px-5 py-4">
          <p className="text-sm font-semibold">{t('reports.ideaTitle')}</p>
          <p className="mt-1 text-sm text-muted-foreground">{t('reports.ideaBody')}</p>
        </div>
      </section>
    </div>
  )
}
