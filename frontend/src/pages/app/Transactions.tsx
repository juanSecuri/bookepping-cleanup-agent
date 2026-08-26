import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Check, X } from 'lucide-react'
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from '@tanstack/react-table'
import {
  api,
  type ChartAccount,
  type Transaction,
  type TransactionCounts,
} from '../../lib/api'
import { useLocale } from '../../i18n'
import { cn } from '../../lib/utils'

type Tab = 'pending' | 'suspense' | 'verified' | 'rejected' | 'all'

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

function confidencePct(tx: Transaction): number | null {
  const raw = tx.category_confidence
  if (raw == null || Number.isNaN(Number(raw))) return null
  const n = Number(raw)
  return n <= 1 ? Math.round(n * 100) : Math.round(n)
}

function confidenceClass(pct: number): string {
  if (pct >= 80) return 'bg-success text-success-foreground'
  if (pct >= 50) return 'bg-warning text-warning-foreground'
  return 'bg-destructive/15 text-destructive'
}

export default function Transactions() {
  const { workspaceId = '' } = useParams()
  const { t } = useLocale()
  const [tab, setTab] = useState<Tab>('pending')
  const [rows, setRows] = useState<Transaction[]>([])
  const [counts, setCounts] = useState<TransactionCounts>({})
  const [accounts, setAccounts] = useState<ChartAccount[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [assignId, setAssignId] = useState<string | null>(null)
  const [assignCode, setAssignCode] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)
  const [sorting, setSorting] = useState<SortingState>([{ id: 'date', desc: true }])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [list, c, coa] = await Promise.all([
        api.listTransactions({
          tenant_id: workspaceId,
          status: tab === 'all' || tab === 'suspense' ? undefined : tab,
          suspense: tab === 'suspense',
        }),
        api.transactionCounts(workspaceId),
        api.chartOfAccounts(workspaceId).catch(() => []),
      ])
      setRows(Array.isArray(list) ? list : [])
      setCounts(c || {})
      setAccounts(Array.isArray(coa) ? coa : [])
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

  async function assignAccount(id: string) {
    const acct = accounts.find((a) => String(a.code) === assignCode)
    if (!acct?.code) {
      setError('Selecciona una cuenta del plan')
      return
    }
    setInfo(null)
    const res = await api.reclassifyTransaction(id, {
      account_code: String(acct.code),
      account_name: String(acct.name ?? acct.code),
    })
    const learned = (res as { learned_rule?: { keyword?: string } }).learned_rule
    if (learned?.keyword) {
      setInfo(`${t('transactions.learned')}: “${learned.keyword}” → ${acct.code}`)
    }
    setAssignId(null)
    setAssignCode('')
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
    { id: 'suspense', label: t('transactions.suspense') },
    { id: 'verified', label: t('transactions.verified') },
    { id: 'rejected', label: t('transactions.rejected') },
    { id: 'all', label: t('transactions.all') },
  ]

  const assignControls = (tx: Transaction) =>
    assignId === tx.id ? (
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <select
          className="min-w-[200px] flex-1 rounded-lg border border-border bg-background px-2 py-1.5 text-sm"
          value={assignCode}
          onChange={(e) => setAssignCode(e.target.value)}
        >
          <option value="">— {t('transactions.assign')} —</option>
          {accounts
            .filter((a) => String(a.code) !== '9999')
            .map((a) => (
              <option key={a.id} value={String(a.code)}>
                {a.code} · {a.name}
              </option>
            ))}
        </select>
        <button
          type="button"
          onClick={() => void assignAccount(tx.id)}
          className="cursor-pointer rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          OK
        </button>
        <button
          type="button"
          onClick={() => {
            setAssignId(null)
            setAssignCode('')
          }}
          className="cursor-pointer text-sm text-muted-foreground"
        >
          {t('common.cancel')}
        </button>
      </div>
    ) : (
      <button
        type="button"
        onClick={() => {
          setAssignId(tx.id)
          setAssignCode('')
        }}
        className="cursor-pointer rounded-md border border-border px-2 py-1 text-xs font-medium hover:border-primary/50"
      >
        {t('transactions.assign')}
      </button>
    )

  const columns = useMemo<ColumnDef<Transaction>[]>(
    () => [
      {
        id: 'select',
        header: '',
        enableSorting: false,
        cell: ({ row }) => (
          <input
            type="checkbox"
            checked={selected.has(row.original.id)}
            onChange={() => toggle(row.original.id)}
          />
        ),
      },
      {
        id: 'date',
        accessorFn: (tx) => txDate(tx),
        header: t('transactions.date'),
      },
      {
        id: 'description',
        accessorFn: (tx) => String(tx.description || tx.id),
        header: t('transactions.description'),
        cell: ({ row }) => (
          <div>
            <div className="max-w-[240px] truncate font-medium">
              {row.original.description || row.original.id}
            </div>
            {assignId === row.original.id && assignControls(row.original)}
          </div>
        ),
      },
      {
        id: 'vendor',
        accessorFn: (tx) => txVendor(tx),
        header: t('transactions.vendor'),
      },
      {
        id: 'account',
        accessorFn: (tx) => txAccount(tx),
        header: t('transactions.account'),
      },
      {
        id: 'amount',
        accessorFn: (tx) => Number(tx.amount ?? 0),
        header: t('transactions.amount'),
        cell: ({ row }) =>
          row.original.amount != null
            ? Number(row.original.amount).toLocaleString(undefined, {
                style: 'currency',
                currency: row.original.currency || 'USD',
              })
            : '—',
      },
      {
        id: 'confidence',
        accessorFn: (tx) => confidencePct(tx) ?? -1,
        header: t('transactions.confidence'),
        cell: ({ row }) => {
          const pct = confidencePct(row.original)
          if (pct == null) return '—'
          return (
            <span
              className={cn(
                'inline-flex rounded-md px-2 py-0.5 text-xs font-medium tabular-nums',
                confidenceClass(pct),
              )}
            >
              {pct}%
            </span>
          )
        },
      },
      {
        id: 'actions',
        header: t('common.actions'),
        enableSorting: false,
        cell: ({ row }) => {
          const tx = row.original
          return (
            <div className="flex flex-wrap gap-1">
              {assignId !== tx.id && (
                <button
                  type="button"
                  onClick={() => {
                    setAssignId(tx.id)
                    setAssignCode('')
                  }}
                  className="cursor-pointer rounded-md border border-border px-2 py-1 text-xs hover:border-primary/40"
                >
                  {t('transactions.assign')}
                </button>
              )}
              <button
                type="button"
                title={t('transactions.approve')}
                onClick={() => void approve(tx.id)}
                className="cursor-pointer rounded-md p-1.5 text-primary hover:bg-secondary"
              >
                <Check className="h-4 w-4" />
              </button>
              <button
                type="button"
                title={t('transactions.reject')}
                onClick={() => void reject(tx.id)}
                className="cursor-pointer rounded-md p-1.5 text-destructive hover:bg-secondary"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          )
        },
      },
    ],
    [accounts, assignCode, assignId, selected, t],
  )

  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  return (
    <div>
      <div className="mb-6 animate-fade-up">
        <h1 className="page-title">{t('transactions.title')}</h1>
        <p className="mt-1.5 text-muted-foreground">{t('transactions.subtitle')}</p>
        {tab === 'suspense' && (
          <p className="mt-2 text-xs text-primary">{t('transactions.suspenseHint')}</p>
        )}
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        {tabs.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => setTab(item.id)}
            className={cn(
              'cursor-pointer rounded-lg px-3 py-1.5 text-sm font-medium transition',
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
            className="cursor-pointer rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground"
          >
            {t('transactions.bulkApprove')} ({selected.size})
          </button>
          <button
            type="button"
            onClick={() => void bulkReject()}
            className="cursor-pointer rounded-lg border border-destructive px-3 py-2 text-sm font-medium text-destructive"
          >
            {t('transactions.bulkReject')}
          </button>
        </div>
      )}

      {info && (
        <div className="mb-4 rounded-lg border border-champagne/25 bg-success px-4 py-3 text-sm text-success-foreground">
          {info}
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
        <>
          <div className="space-y-3 md:hidden">
            {rows.map((tx) => {
              const pct = confidencePct(tx)
              return (
                <article
                  key={tx.id}
                  className="soft-shadow rounded-xl border border-border bg-card p-4"
                >
                  <div className="mb-2 flex items-start gap-3">
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={selected.has(tx.id)}
                      onChange={() => toggle(tx.id)}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium">{tx.description || tx.id}</p>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {txDate(tx)} · {txVendor(tx)}
                      </p>
                    </div>
                    <span className="shrink-0 tabular-nums text-sm font-semibold">
                      {tx.amount != null
                        ? Number(tx.amount).toLocaleString(undefined, {
                            style: 'currency',
                            currency: tx.currency || 'USD',
                          })
                        : '—'}
                    </span>
                  </div>
                  <p className="mb-3 truncate text-xs text-muted-foreground">{txAccount(tx)}</p>
                  {assignControls(tx)}
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <span className="rounded-md bg-secondary px-2 py-0.5 text-xs capitalize">
                      {String(tx.status ?? '—')}
                    </span>
                    {pct != null && (
                      <span
                        className={cn(
                          'inline-flex rounded-md px-2 py-0.5 text-xs font-medium tabular-nums',
                          confidenceClass(pct),
                        )}
                      >
                        {pct}%
                      </span>
                    )}
                    <div className="ml-auto flex gap-1">
                      <button
                        type="button"
                        title={t('transactions.approve')}
                        onClick={() => void approve(tx.id)}
                        className="cursor-pointer rounded-md p-2 text-primary hover:bg-secondary"
                      >
                        <Check className="h-4 w-4" />
                      </button>
                      <button
                        type="button"
                        title={t('transactions.reject')}
                        onClick={() => void reject(tx.id)}
                        className="cursor-pointer rounded-md p-2 text-destructive hover:bg-secondary"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                </article>
              )
            })}
          </div>

          <div className="soft-shadow table-scroll hidden rounded-xl border border-border bg-card md:block">
            <table className="w-full min-w-[960px] text-left text-sm">
              <thead className="border-b border-border bg-secondary/50 text-muted-foreground">
                {table.getHeaderGroups().map((hg) => (
                  <tr key={hg.id}>
                    {hg.headers.map((header) => (
                      <th
                        key={header.id}
                        className={cn(
                          'px-3 py-3 font-medium',
                          header.column.getCanSort() && 'cursor-pointer select-none',
                        )}
                        onClick={header.column.getToggleSortingHandler()}
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {{ asc: ' ↑', desc: ' ↓' }[header.column.getIsSorted() as string] ?? null}
                      </th>
                    ))}
                  </tr>
                ))}
              </thead>
              <tbody>
                {table.getRowModel().rows.map((row) => (
                  <tr
                    key={row.id}
                    className="border-b border-border last:border-0 align-top"
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className="px-3 py-3">
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
