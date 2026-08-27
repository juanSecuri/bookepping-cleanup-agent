import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Sprout } from 'lucide-react'
import { api, type ChartAccount } from '../../lib/api'
import { useLocale } from '../../i18n'
import { cn } from '../../lib/utils'

const TYPE_ORDER = ['asset', 'liability', 'equity', 'income', 'cogs', 'expense'] as const

function normalBalance(type: string): 'debit' | 'credit' {
  const t = type.toLowerCase()
  if (t === 'asset' || t === 'expense' || t === 'cogs') return 'debit'
  return 'credit'
}

function accountType(acct: ChartAccount): string {
  return String(acct.account_type || acct.category || 'other').toLowerCase()
}

export default function ChartOfAccounts() {
  const { workspaceId = '' } = useParams()
  const { t } = useLocale()

  function typeLabel(typ: string): string {
    const key = `coa.type.${typ}`
    const translated = t(key)
    return translated === key ? typ : translated
  }
  const [accounts, setAccounts] = useState<ChartAccount[]>([])
  const [rules, setRules] = useState<Array<Record<string, unknown>>>([])
  const [loading, setLoading] = useState(true)
  const [seeding, setSeeding] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    setAccounts([])
    setRules([])
    setQuery('')
    try {
      const [data, r] = await Promise.all([
        api.chartOfAccounts(workspaceId),
        api.listAccountRules(workspaceId).catch(() => []),
      ])
      setAccounts(Array.isArray(data) ? data : [])
      setRules(Array.isArray(r) ? r : [])
    } catch (e) {
      setError(e instanceof Error ? e.message : t('common.error'))
      setAccounts([])
      setRules([])
    } finally {
      setLoading(false)
    }
  }, [workspaceId, t])

  useEffect(() => {
    void load()
  }, [load])

  async function seed() {
    setSeeding(true)
    setError(null)
    try {
      await api.seedChartOfAccounts(workspaceId)
      await api.seedAccountRules(workspaceId).catch(() => null)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : t('common.error'))
    } finally {
      setSeeding(false)
    }
  }

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return accounts
    return accounts.filter((a) => {
      const hay = [a.code, a.name, a.subcategory, a.description, accountType(a)]
        .map((x) => String(x ?? '').toLowerCase())
        .join(' ')
      return hay.includes(q)
    })
  }, [accounts, query])

  const typeCounts = useMemo(() => {
    const map = new Map<string, number>()
    for (const a of accounts) {
      const typ = accountType(a)
      map.set(typ, (map.get(typ) || 0) + 1)
    }
    return map
  }, [accounts])

  const grouped = useMemo(() => {
    const map = new Map<string, ChartAccount[]>()
    for (const acct of filtered) {
      const cat = accountType(acct)
      const list = map.get(cat) || []
      list.push(acct)
      map.set(cat, list)
    }
    for (const list of map.values()) {
      list.sort((a, b) => String(a.code ?? '').localeCompare(String(b.code ?? '')))
    }
    return [...map.entries()].sort(([a], [b]) => {
      const ia = TYPE_ORDER.indexOf(a as (typeof TYPE_ORDER)[number])
      const ib = TYPE_ORDER.indexOf(b as (typeof TYPE_ORDER)[number])
      const sa = ia === -1 ? 99 : ia
      const sb = ib === -1 ? 99 : ib
      return sa - sb || a.localeCompare(b)
    })
  }, [filtered])

  const activeCount = accounts.filter((a) => a.is_active !== false).length

  return (
    <div>
      <div className="mb-6 animate-fade-up">
        <h1 className="page-title">{t('coa.title')}</h1>
        <p className="mt-1.5 text-muted-foreground">{t('coa.subtitle')}</p>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}
      {loading && <p className="text-muted-foreground">{t('common.loading')}</p>}

      {!loading && accounts.length === 0 && (
        <div className="soft-shadow rounded-xl border border-dashed border-border bg-card px-6 py-12 text-center">
          <p className="font-medium">{t('coa.empty')}</p>
          <p className="mx-auto mt-2 max-w-md text-sm text-foreground/80">
            {t('coa.emptyHint')}
          </p>
          <p className="mx-auto mt-3 max-w-lg text-xs leading-relaxed text-foreground/70">
            {t('coa.seedExplain')}
          </p>
          <button
            type="button"
            onClick={() => void seed()}
            disabled={seeding}
            className="mt-5 inline-flex cursor-pointer items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground transition hover:bg-champagne-bright disabled:opacity-60"
          >
            <Sprout className="h-4 w-4" />
            {seeding ? t('coa.seeding') : t('coa.seed')}
          </button>
        </div>
      )}

      {accounts.length > 0 && (
        <>
          <section className="mb-6">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                  {t('coa.rules')}
                </h2>
                <p className="text-xs text-muted-foreground">{t('coa.rulesHint')}</p>
              </div>
              <button
                type="button"
                onClick={() => void api.seedAccountRules(workspaceId).then(() => load())}
                className="cursor-pointer rounded-lg border border-border px-3 py-1.5 text-xs font-medium hover:border-primary/40"
              >
                {t('coa.seedRules')}
              </button>
            </div>
            {rules.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t('coa.rulesEmpty')}</p>
            ) : (
              <div className="soft-shadow table-scroll rounded-xl border border-border bg-card">
                <table className="w-full min-w-[560px] text-left text-sm">
                  <thead className="border-b border-border bg-secondary/50 text-muted-foreground">
                    <tr>
                      <th className="px-4 py-2 font-medium">{t('coa.keywords')}</th>
                      <th className="px-4 py-2 font-medium">{t('coa.code')}</th>
                      <th className="px-4 py-2 font-medium">{t('coa.account')}</th>
                      <th className="px-4 py-2 font-medium">{t('coa.origin')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rules.slice(0, 40).map((r) => (
                      <tr key={String(r.id)} className="border-b border-border last:border-0">
                        <td className="px-4 py-2 text-xs">
                          {(Array.isArray(r.keywords) ? r.keywords : []).join(', ')}
                        </td>
                        <td className="px-4 py-2 font-mono text-xs">{String(r.account_code)}</td>
                        <td className="px-4 py-2">{String(r.account_name)}</td>
                        <td className="px-4 py-2">
                          <span className="rounded-md bg-secondary px-2 py-0.5 text-[10px] uppercase">
                            {String(r.source ?? '—')}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="mb-6">
            <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-foreground/80">
              {t('coa.summary')}
            </h2>
            <p className="mb-3 text-xs text-foreground/70">{t('coa.seedExplainShort')}</p>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <div className="soft-shadow-lift animate-fade-up rounded-xl border border-border bg-card p-4 transition duration-200 hover:-translate-y-0.5">
                <p className="text-2xl font-semibold tabular-nums text-foreground">{accounts.length}</p>
                <p className="text-sm font-medium text-foreground/75">{t('coa.total')}</p>
              </div>
              <div className="soft-shadow-lift animate-fade-up-delay-1 rounded-xl border border-border bg-card p-4 transition duration-200 hover:-translate-y-0.5">
                <p className="text-2xl font-semibold tabular-nums text-foreground">{activeCount}</p>
                <p className="text-sm font-medium text-foreground/75">{t('coa.active')}</p>
              </div>
              {[...typeCounts.entries()]
                .sort((a, b) => a[0].localeCompare(b[0]))
                .slice(0, 4)
                .map(([typ, count], i) => (
                  <div
                    key={typ}
                    className={cn(
                      'soft-shadow-lift rounded-xl border border-border bg-card p-4 transition duration-200 hover:-translate-y-0.5',
                      i === 0
                        ? 'animate-fade-up-delay-2'
                        : i === 1
                          ? 'animate-fade-up-delay-3'
                          : 'animate-fade-up-delay-4',
                    )}
                  >
                    <p className="text-2xl font-semibold tabular-nums text-foreground">{count}</p>
                    <p className="truncate text-sm font-medium text-foreground/75">
                      {typeLabel(typ)}
                    </p>
                  </div>
                ))}
            </div>
          </section>

          <div className="mb-4">
            <input
              className="w-full max-w-md rounded-lg border border-border bg-background px-3 py-2 text-sm"
              placeholder={`${t('common.search')}…`}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
        </>
      )}

      <div className="space-y-6">
        {grouped.map(([category, rows]) => (
          <section key={category}>
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                {typeLabel(category)}
              </h2>
              <span className="rounded-md bg-secondary px-2 py-0.5 text-xs text-muted-foreground">
                {rows.length} {t('coa.count')}
              </span>
              <span className="rounded-md bg-warning px-2 py-0.5 text-xs text-warning-foreground">
                {t('coa.normalBalance')}:{' '}
                {normalBalance(category) === 'debit' ? t('coa.debit') : t('coa.credit')}
              </span>
            </div>

            <div className="mb-3 space-y-2 md:hidden">
              {rows.map((acct) => {
                const typ = accountType(acct)
                const bal = normalBalance(typ)
                return (
                  <article
                    key={acct.id}
                    className="soft-shadow rounded-xl border border-border bg-card p-4"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="font-mono text-xs text-muted-foreground">{String(acct.code ?? '—')}</p>
                        <p className="font-medium">{String(acct.name ?? acct.id)}</p>
                      </div>
                      <span
                        className={cn(
                          'shrink-0 rounded-md px-2 py-0.5 text-[10px] font-medium',
                          acct.is_active === false
                            ? 'bg-secondary text-muted-foreground'
                            : 'bg-success text-success-foreground',
                        )}
                      >
                        {acct.is_active === false ? t('coa.inactive') : t('coa.active')}
                      </span>
                    </div>
                    <dl className="mt-3 grid grid-cols-2 gap-2 text-xs text-muted-foreground">
                      <div>
                        <dt className="font-medium text-foreground/70">{t('coa.type')}</dt>
                        <dd>{typeLabel(typ)}</dd>
                      </div>
                      <div>
                        <dt className="font-medium text-foreground/70">{t('coa.subcategory')}</dt>
                        <dd>{String(acct.subcategory ?? '—')}</dd>
                      </div>
                      <div>
                        <dt className="font-medium text-foreground/70">{t('coa.normalBalance')}</dt>
                        <dd>{bal === 'debit' ? t('coa.debit') : t('coa.credit')}</dd>
                      </div>
                      <div className="col-span-2">
                        <dt className="font-medium text-foreground/70">{t('coa.description')}</dt>
                        <dd>{String(acct.description ?? acct.subcategory ?? '—')}</dd>
                      </div>
                    </dl>
                  </article>
                )
              })}
            </div>

            <div className="soft-shadow table-scroll hidden rounded-xl border border-border bg-card md:block">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className="border-b border-border bg-secondary/50 text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3 font-medium">{t('coa.code')}</th>
                    <th className="px-4 py-3 font-medium">{t('coa.name')}</th>
                    <th className="px-4 py-3 font-medium">{t('coa.type')}</th>
                    <th className="px-4 py-3 font-medium">{t('coa.subcategory')}</th>
                    <th className="px-4 py-3 font-medium">{t('coa.description')}</th>
                    <th className="px-4 py-3 font-medium">{t('coa.normalBalance')}</th>
                    <th className="px-4 py-3 font-medium">Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((acct) => {
                    const typ = accountType(acct)
                    const bal = normalBalance(typ)
                    return (
                      <tr key={acct.id} className="border-b border-border last:border-0">
                        <td className="px-4 py-3 font-mono text-xs">{String(acct.code ?? '—')}</td>
                        <td className="px-4 py-3 font-medium">{String(acct.name ?? acct.id)}</td>
                        <td className="px-4 py-3 text-muted-foreground">
                          {typeLabel(typ)}
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">
                          {String(acct.subcategory ?? '—')}
                        </td>
                        <td className="max-w-[220px] truncate px-4 py-3 text-muted-foreground">
                          {String(acct.description ?? acct.subcategory ?? '—')}
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">
                          {bal === 'debit' ? t('coa.debit') : t('coa.credit')}
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={cn(
                              'rounded-md px-2 py-0.5 text-xs font-medium',
                              acct.is_active === false
                                ? 'bg-secondary text-muted-foreground'
                                : 'bg-success text-success-foreground',
                            )}
                          >
                            {acct.is_active === false ? t('coa.inactive') : t('coa.active')}
                          </span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </section>
        ))}
      </div>
    </div>
  )
}
