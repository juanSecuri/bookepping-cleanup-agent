import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Upload, Link2, Unlink } from 'lucide-react'
import { api, type Movement } from '../../lib/api'
import { useLocale } from '../../i18n'
import { cn } from '../../lib/utils'

type Filter = 'all' | 'matched' | 'unmatched'

function isMatched(m: Movement): boolean {
  return Boolean(m.matched || m.transaction_id)
}

function shortId(id: string | null | undefined): string {
  if (!id) return '—'
  return id.length > 10 ? `${id.slice(0, 8)}…` : id
}

export default function Reconciliation() {
  const { workspaceId = '' } = useParams()
  const { t } = useLocale()
  const [movements, setMovements] = useState<Movement[]>([])
  const [filter, setFilter] = useState<Filter>('all')
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [matchId, setMatchId] = useState<string | null>(null)
  const [txId, setTxId] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.listMovements({
        workspace_id: workspaceId,
        tenant_id: workspaceId,
      })
      setMovements(Array.isArray(data) ? data : [])
    } catch (e) {
      setError(e instanceof Error ? e.message : t('common.error'))
      setMovements([])
    } finally {
      setLoading(false)
    }
  }, [workspaceId, t])

  useEffect(() => {
    void load()
  }, [load])

  const matchedCount = useMemo(() => movements.filter(isMatched).length, [movements])
  const unmatchedCount = movements.length - matchedCount

  const filtered = useMemo(() => {
    if (filter === 'matched') return movements.filter(isMatched)
    if (filter === 'unmatched') return movements.filter((m) => !isMatched(m))
    return movements
  }, [movements, filter])

  async function onUpload(file: File) {
    setUploading(true)
    setError(null)
    try {
      const form = new FormData()
      form.append('file', file)
      form.append('workspace_id', workspaceId)
      form.append('tenant_id', workspaceId)
      await api.uploadStatement(form)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : t('common.error'))
    } finally {
      setUploading(false)
    }
  }

  async function doMatch(id: string) {
    if (!txId.trim()) return
    try {
      await api.matchMovement(id, txId.trim())
      setMatchId(null)
      setTxId('')
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : t('common.error'))
    }
  }

  async function doUnmatch(id: string) {
    try {
      await api.unmatchMovement(id)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : t('common.error'))
    }
  }

  const kpis = [
    { label: t('reconciliation.total'), value: movements.length },
    { label: t('reconciliation.matched'), value: matchedCount },
    { label: t('reconciliation.unmatched'), value: unmatchedCount },
  ]

  const filters: { id: Filter; label: string; count: number }[] = [
    { id: 'all', label: t('reconciliation.filterAll'), count: movements.length },
    { id: 'matched', label: t('reconciliation.filterMatched'), count: matchedCount },
    { id: 'unmatched', label: t('reconciliation.filterUnmatched'), count: unmatchedCount },
  ]

  return (
    <div>
      <div className="mb-6 animate-fade-up">
        <h1 className="page-title">{t('reconciliation.title')}</h1>
        <p className="mt-1.5 text-muted-foreground">{t('reconciliation.subtitle')}</p>
      </div>

      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        {kpis.map((kpi) => (
          <div
            key={kpi.label}
            className="soft-shadow rounded-xl border border-border bg-card p-4"
          >
            <p className="text-sm text-muted-foreground">{kpi.label}</p>
            <p className="mt-1 text-2xl font-semibold tabular-nums">{kpi.value}</p>
          </div>
        ))}
      </div>

      <div className="mb-6 flex flex-wrap items-start gap-4">
        <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground">
          <Upload className="h-4 w-4" />
          {uploading ? t('documents.uploading') : t('reconciliation.upload')}
          <input
            type="file"
            className="hidden"
            accept=".csv,.pdf,.ofx,.qfx,.xlsx"
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) void onUpload(f)
            }}
          />
        </label>
        <p className="max-w-md text-sm text-muted-foreground">{t('reconciliation.uploadNote')}</p>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold tracking-tight">{t('reconciliation.movements')}</h2>
        <div className="flex flex-wrap gap-2">
          {filters.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setFilter(item.id)}
              className={cn(
                'rounded-lg px-3 py-1.5 text-sm font-medium transition',
                filter === item.id
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
              )}
            >
              {item.label}
              <span className="ml-1.5 opacity-80">({item.count})</span>
            </button>
          ))}
        </div>
      </div>

      {loading && <p className="text-muted-foreground">{t('common.loading')}</p>}
      {!loading && movements.length === 0 && (
        <div className="soft-shadow rounded-xl border border-dashed border-border bg-card px-6 py-12 text-center">
          <p className="font-medium">{t('reconciliation.empty')}</p>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            {t('reconciliation.emptyHint')}
          </p>
        </div>
      )}

      {!loading && movements.length > 0 && filtered.length === 0 && (
        <p className="text-sm text-muted-foreground">{t('reconciliation.empty')}</p>
      )}

      {filtered.length > 0 && (
        <>
          <div className="space-y-3 md:hidden">
            {filtered.map((m) => {
              const matched = isMatched(m)
              return (
                <article
                  key={m.id}
                  className="soft-shadow rounded-xl border border-border bg-card p-4"
                >
                  <div className="mb-2 flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-medium">{m.description || m.id}</p>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {String(m.date ?? '—')}
                        {(m.bank || m.bank_name) && ` · ${String(m.bank ?? m.bank_name)}`}
                      </p>
                    </div>
                    <span className="shrink-0 tabular-nums text-sm font-semibold">
                      {m.amount != null ? Number(m.amount).toLocaleString() : '—'}
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={cn(
                        'rounded-md px-2 py-0.5 text-xs font-medium',
                        matched
                          ? 'bg-emerald-50 text-emerald-800'
                          : 'bg-amber-50 text-amber-800',
                      )}
                    >
                      {matched
                        ? t('reconciliation.matchedYes')
                        : t('reconciliation.matchedNo')}
                    </span>
                    {matched && (
                      <span className="font-mono text-xs text-muted-foreground">
                        {shortId(m.transaction_id)}
                      </span>
                    )}
                  </div>
                  <div className="mt-3">
                    {matched ? (
                      <button
                        type="button"
                        onClick={() => void doUnmatch(m.id)}
                        className="inline-flex items-center gap-1 text-sm text-destructive"
                      >
                        <Unlink className="h-3.5 w-3.5" />
                        {t('reconciliation.unmatch')}
                      </button>
                    ) : matchId === m.id ? (
                      <div className="flex flex-wrap items-center gap-2">
                        <input
                          className="min-w-0 flex-1 rounded border border-border px-2 py-1.5 text-xs"
                          placeholder="transaction_id"
                          value={txId}
                          onChange={(e) => setTxId(e.target.value)}
                        />
                        <button
                          type="button"
                          onClick={() => void doMatch(m.id)}
                          className="text-sm font-medium text-primary"
                        >
                          OK
                        </button>
                        <button
                          type="button"
                          onClick={() => setMatchId(null)}
                          className="text-sm text-muted-foreground"
                        >
                          {t('common.cancel')}
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => {
                          setMatchId(m.id)
                          setTxId('')
                        }}
                        className="inline-flex items-center gap-1 text-sm text-primary"
                      >
                        <Link2 className="h-3.5 w-3.5" />
                        {t('reconciliation.match')}
                      </button>
                    )}
                  </div>
                </article>
              )
            })}
          </div>

          <div className="soft-shadow table-scroll hidden rounded-xl border border-border bg-card md:block">
            <table className="w-full min-w-[800px] text-left text-sm">
              <thead className="border-b border-border bg-secondary/50 text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 font-medium">{t('documents.date')}</th>
                  <th className="px-4 py-3 font-medium">{t('transactions.description')}</th>
                  <th className="px-4 py-3 font-medium">{t('transactions.amount')}</th>
                  <th className="px-4 py-3 font-medium">{t('reconciliation.matched')}</th>
                  <th className="px-4 py-3 font-medium">{t('reconciliation.txId')}</th>
                  <th className="px-4 py-3 font-medium">{t('common.actions')}</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((m) => {
                  const matched = isMatched(m)
                  return (
                    <tr key={m.id} className="border-b border-border last:border-0">
                      <td className="px-4 py-3 whitespace-nowrap text-muted-foreground">
                        {String(m.date ?? '—')}
                      </td>
                      <td className="px-4 py-3">
                        <div className="font-medium">{m.description || m.id}</div>
                        {(m.bank || m.bank_name) && (
                          <div className="text-xs text-muted-foreground">
                            {String(m.bank ?? m.bank_name)}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3 tabular-nums whitespace-nowrap">
                        {m.amount != null ? Number(m.amount).toLocaleString() : '—'}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={cn(
                            'rounded-md px-2 py-0.5 text-xs font-medium',
                            matched
                              ? 'bg-emerald-50 text-emerald-800'
                              : 'bg-amber-50 text-amber-800',
                          )}
                        >
                          {matched
                            ? t('reconciliation.matchedYes')
                            : t('reconciliation.matchedNo')}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                        {shortId(m.transaction_id)}
                      </td>
                      <td className="px-4 py-3">
                        {matched ? (
                          <button
                            type="button"
                            onClick={() => void doUnmatch(m.id)}
                            className="inline-flex items-center gap-1 text-sm text-destructive"
                          >
                            <Unlink className="h-3.5 w-3.5" />
                            {t('reconciliation.unmatch')}
                          </button>
                        ) : matchId === m.id ? (
                          <div className="flex items-center gap-2">
                            <input
                              className="rounded border border-border px-2 py-1 text-xs"
                              placeholder="transaction_id"
                              value={txId}
                              onChange={(e) => setTxId(e.target.value)}
                            />
                            <button
                              type="button"
                              onClick={() => void doMatch(m.id)}
                              className="text-sm font-medium text-primary"
                            >
                              OK
                            </button>
                            <button
                              type="button"
                              onClick={() => setMatchId(null)}
                              className="text-sm text-muted-foreground"
                            >
                              {t('common.cancel')}
                            </button>
                          </div>
                        ) : (
                          <button
                            type="button"
                            onClick={() => {
                              setMatchId(m.id)
                              setTxId('')
                            }}
                            className="inline-flex items-center gap-1 text-sm text-primary"
                          >
                            <Link2 className="h-3.5 w-3.5" />
                            {t('reconciliation.match')}
                          </button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
