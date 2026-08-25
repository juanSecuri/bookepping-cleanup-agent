import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Sprout } from 'lucide-react'
import { api, type ChartAccount } from '../../lib/api'
import { useLocale } from '../../i18n'

export default function ChartOfAccounts() {
  const { workspaceId = '' } = useParams()
  const { t } = useLocale()
  const [accounts, setAccounts] = useState<ChartAccount[]>([])
  const [loading, setLoading] = useState(true)
  const [seeding, setSeeding] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.chartOfAccounts(workspaceId)
      setAccounts(Array.isArray(data) ? data : [])
    } catch (e) {
      setError(e instanceof Error ? e.message : t('common.error'))
      setAccounts([])
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
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : t('common.error'))
    } finally {
      setSeeding(false)
    }
  }

  const grouped = useMemo(() => {
    const map = new Map<string, ChartAccount[]>()
    for (const acct of accounts) {
      const cat = String(acct.category || 'Other')
      const list = map.get(cat) || []
      list.push(acct)
      map.set(cat, list)
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b))
  }, [accounts])

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
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            {t('coa.emptyHint')}
          </p>
          <button
            type="button"
            onClick={() => void seed()}
            disabled={seeding}
            className="mt-5 inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground disabled:opacity-60"
          >
            <Sprout className="h-4 w-4" />
            {seeding ? t('coa.seeding') : t('coa.seed')}
          </button>
        </div>
      )}

      <div className="space-y-6">
        {grouped.map(([category, rows]) => (
          <section key={category}>
            <div className="mb-2 flex items-center gap-2">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                {category}
              </h2>
              <span className="rounded-md bg-secondary px-2 py-0.5 text-xs text-muted-foreground">
                {rows.length} {t('coa.count')}
              </span>
            </div>
            <div className="soft-shadow table-scroll rounded-xl border border-border bg-card">
              <table className="w-full min-w-[480px] text-left text-sm">
                <thead className="border-b border-border bg-secondary/50 text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3 font-medium">{t('coa.code')}</th>
                    <th className="px-4 py-3 font-medium">{t('coa.name')}</th>
                    <th className="px-4 py-3 font-medium">{t('coa.subcategory')}</th>
                    <th className="px-4 py-3 font-medium">{t('coa.category')}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((acct) => (
                    <tr key={acct.id} className="border-b border-border last:border-0">
                      <td className="px-4 py-3 font-mono text-xs">{String(acct.code ?? '—')}</td>
                      <td className="px-4 py-3 font-medium">{String(acct.name ?? acct.id)}</td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {String(acct.subcategory ?? '—')}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {String(acct.category ?? '—')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ))}
      </div>
    </div>
  )
}
