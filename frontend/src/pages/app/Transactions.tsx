import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Check, X } from 'lucide-react'
import { api, type Transaction, type TransactionCounts } from '../../lib/api'
import { useLocale } from '../../i18n'
import { cn } from '../../lib/utils'

type Tab = 'pending' | 'verified' | 'rejected' | 'all'

function txDate(tx: Transaction): string {
  return String(tx.date ?? tx.transaction_date ?? '—')
}

function txVendor(tx: Transaction): string {
  return String(tx.vendor ?? tx.vendor_name ?? '—')
}

function txAccount(tx: Transaction): string {
  const code = tx.account_code ?? tx.chart_of_accounts_code
  const name = tx.account_name ?? tx.category
  if (code && name) return `${code} · ${name}`
  if (code) return String(code)
  if (name) return String(name)
  return '—'
}

function txType(tx: Transaction): string {
  return String(tx.type ?? tx.transaction_type ?? '—')
}

function confidencePct(tx: Transaction): number | null {
  const raw = tx.category_confidence
  if (raw == null || Number.isNaN(Number(raw))) return null
  const n = Number(raw)
  return n <= 1 ? Math.round(n * 100) : Math.round(n)
}

function confidenceClass(pct: number): string {
  if (pct >= 80) return 'bg-emerald-50 text-emerald-800'
  if (pct >= 50) return 'bg-amber-50 text-amber-800'
  return 'bg-rose-50 text-rose-800'
}

export default function Transactions() {
  const { workspaceId = '' } = useParams()
  const { t } = useLocale()
  const [tab, setTab] = useState<Tab>('pending')
  const [rows, setRows] = useState<Transaction[]>([])
  const [counts, setCounts] = useState<TransactionCounts>({})
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [list, c] = await Promise.all([
        api.listTransactions({
          tenant_id: workspaceId,
          status: tab === 'all' ? undefined : tab,
        }),
        api.transactionCounts(workspaceId),
      ])
      setRows(Array.isArray(list) ? list : [])
      setCounts(c || {})
      setSelected(new Set())
    } catch (e) {
      setError(e instanceof Error ? e.message : t('common.error'))
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [workspaceId, tab, t])

  useEffect(() => {
    void load()
  }, [load])

  async function approve(id: string) {
    await api.approveTransaction(id)
    await load()
  }

  async function reject(id: string) {
    await api.rejectTransaction(id)
    await load()
  }

  async function bulkApprove() {
    await api.bulkApprove([...selected])
    await load()
  }

  async function bulkReject() {
    await api.bulkReject([...selected])
    await load()
  }

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const tabs: { id: Tab; label: string }[] = [
    { id: 'pending', label: t('transactions.pending') },
    { id: 'verified', label: t('transactions.verified') },
    { id: 'rejected', label: t('transactions.rejected') },
    { id: 'all', label: t('transactions.all') },
  ]

  return (
    <div>
      <div className="mb-6 animate-fade-up">
        <h1 className="page-title">{t('transactions.title')}</h1>
        <p className="mt-1.5 text-muted-foreground">{t('transactions.subtitle')}</p>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        {tabs.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => setTab(item.id)}
            className={cn(
              'rounded-lg px-3 py-1.5 text-sm font-medium transition',
              tab === item.id
                ? 'bg-primary text-primary-foreground'
                : 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
            )}
          >
            {item.label}
            {counts[item.id] != null && (
              <span className="ml-1.5 opacity-80">({counts[item.id]})</span>
            )}
          </button>
        ))}
      </div>

      {selected.size > 0 && (
        <div className="mb-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void bulkApprove()}
            className="rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground"
          >
            {t('transactions.bulkApprove')} ({selected.size})
          </button>
          <button
            type="button"
            onClick={() => void bulkReject()}
            className="rounded-lg border border-destructive px-3 py-2 text-sm font-medium text-destructive"
          >
            {t('transactions.bulkReject')}
          </button>
        </div>
      )}

      {error && (
        <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}
      {loading && <p className="text-muted-foreground">{t('common.loading')}</p>}
      {!loading && rows.length === 0 && (
        <div className="soft-shadow rounded-xl border border-border bg-card px-6 py-10 text-center">
          <p className="text-muted-foreground">{t('transactions.empty')}</p>
        </div>
      )}

      {rows.length > 0 && (
        <div className="soft-shadow overflow-x-auto rounded-xl border border-border bg-card">
          <table className="w-full min-w-[960px] text-left text-sm">
            <thead className="border-b border-border bg-secondary/50 text-muted-foreground">
              <tr>
                <th className="w-10 px-3 py-3" />
                <th className="px-3 py-3 font-medium">{t('transactions.date')}</th>
                <th className="px-3 py-3 font-medium">{t('transactions.description')}</th>
                <th className="px-3 py-3 font-medium">{t('transactions.vendor')}</th>
                <th className="px-3 py-3 font-medium">{t('transactions.account')}</th>
                <th className="px-3 py-3 font-medium">{t('transactions.amount')}</th>
                <th className="px-3 py-3 font-medium">{t('transactions.type')}</th>
                <th className="px-3 py-3 font-medium">{t('transactions.confidence')}</th>
                <th className="px-3 py-3 font-medium">{t('transactions.status')}</th>
                <th className="px-3 py-3 font-medium">{t('common.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((tx) => {
                const pct = confidencePct(tx)
                return (
                  <tr key={tx.id} className="border-b border-border last:border-0">
                    <td className="px-3 py-3">
                      <input
                        type="checkbox"
                        checked={selected.has(tx.id)}
                        onChange={() => toggle(tx.id)}
                      />
                    </td>
                    <td className="px-3 py-3 whitespace-nowrap text-muted-foreground">
                      {txDate(tx)}
                    </td>
                    <td className="px-3 py-3">
                      <div className="max-w-[220px] truncate font-medium">
                        {tx.description || tx.id}
                      </div>
                    </td>
                    <td className="px-3 py-3 text-muted-foreground">{txVendor(tx)}</td>
                    <td className="px-3 py-3">
                      <span className="max-w-[180px] truncate block">{txAccount(tx)}</span>
                    </td>
                    <td className="px-3 py-3 tabular-nums whitespace-nowrap">
                      {tx.amount != null
                        ? Number(tx.amount).toLocaleString(undefined, {
                            style: 'currency',
                            currency: tx.currency || 'USD',
                          })
                        : '—'}
                    </td>
                    <td className="px-3 py-3 capitalize text-muted-foreground">{txType(tx)}</td>
                    <td className="px-3 py-3">
                      {pct != null ? (
                        <span
                          className={cn(
                            'inline-flex rounded-md px-2 py-0.5 text-xs font-medium tabular-nums',
                            confidenceClass(pct),
                          )}
                        >
                          {pct}%
                        </span>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="px-3 py-3">
                      <span className="rounded-md bg-secondary px-2 py-0.5 text-xs capitalize">
                        {String(tx.status ?? '—')}
                      </span>
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex gap-1">
                        <button
                          type="button"
                          title={t('transactions.approve')}
                          onClick={() => void approve(tx.id)}
                          className="rounded-md p-1.5 text-primary hover:bg-secondary"
                        >
                          <Check className="h-4 w-4" />
                        </button>
                        <button
                          type="button"
                          title={t('transactions.reject')}
                          onClick={() => void reject(tx.id)}
                          className="rounded-md p-1.5 text-destructive hover:bg-secondary"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
