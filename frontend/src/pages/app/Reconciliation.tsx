import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Upload, Link2, Unlink } from 'lucide-react'
import {
  api,
  type Movement,
  type ReconciliationBank,
} from '../../lib/api'
import { useLocale } from '../../i18n'
import { cn } from '../../lib/utils'

type Filter = 'all' | 'matched' | 'unmatched'

type ChainPeriod = {
  statement_month?: string
  bank_account_number?: string
  bank_name?: string
  opening_balance?: number | null
  closing_balance?: number | null
  chain_ok?: boolean | null
  paused?: boolean
  alert_message?: string | null
  chain_delta?: number | null
}

function bankKey(b: Pick<ReconciliationBank, 'bank_name' | 'bank_account_number'>): string {
  return `${b.bank_name}::${b.bank_account_number}`
}

function isMatched(m: Movement): boolean {
  return Boolean(m.matched || m.transaction_id)
}

function shortId(id: string | null | undefined): string {
  if (!id) return '—'
  return id.length > 10 ? `${id.slice(0, 8)}…` : id
}

function money(n: number | string | null | undefined): string {
  if (n == null || n === '') return '—'
  const v = Number(n)
  if (Number.isNaN(v) || v === 0) return v === 0 ? '0' : '—'
  return v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function debitOf(m: Movement): number {
  const raw = m.debit ?? m.debit_amount
  return raw != null ? Number(raw) : 0
}

function creditOf(m: Movement): number {
  const raw = m.credit ?? m.credit_amount
  return raw != null ? Number(raw) : 0
}

function coaLabel(m: Movement): string {
  const code = m.chart_of_accounts_code
  const name = m.chart_of_accounts_name
  if (code && name) return `${code} · ${name}`
  if (code) return String(code)
  if (name) return String(name)
  return '—'
}

function confidencePct(m: Movement): number | null {
  const raw = m.category_confidence
  if (raw == null || Number.isNaN(Number(raw))) return null
  const n = Number(raw)
  return n <= 1 ? Math.round(n * 100) : Math.round(n)
}

export default function Reconciliation() {
  const { workspaceId = '' } = useParams()
  const { t } = useLocale()
  const [banks, setBanks] = useState<ReconciliationBank[]>([])
  const [selectedBankKey, setSelectedBankKey] = useState('')
  const [year, setYear] = useState('')
  const [month, setMonth] = useState('')
  const [movements, setMovements] = useState<Movement[]>([])
  const [chainPeriods, setChainPeriods] = useState<ChainPeriod[]>([])
  const [filter, setFilter] = useState<Filter>('all')
  const [loadingBanks, setLoadingBanks] = useState(true)
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [matchId, setMatchId] = useState<string | null>(null)
  const [txId, setTxId] = useState('')
  const defaultsApplied = useRef(false)

  const selectedBank = useMemo(
    () => banks.find((b) => bankKey(b) === selectedBankKey) ?? null,
    [banks, selectedBankKey],
  )

  const years = useMemo(() => {
    if (!selectedBank) return []
    const set = new Set(selectedBank.months.map((m) => m.slice(0, 4)))
    return Array.from(set).sort((a, b) => b.localeCompare(a))
  }, [selectedBank])

  const monthsForBank = useMemo(() => {
    if (!selectedBank) return []
    const list = year
      ? selectedBank.months.filter((m) => m.startsWith(`${year}-`))
      : selectedBank.months
    return [...list].sort((a, b) => b.localeCompare(a))
  }, [selectedBank, year])

  const statementPeriod = useMemo(() => {
    if (!selectedBank || !month) return null
    return (
      chainPeriods.find(
        (p) =>
          p.statement_month === month &&
          p.bank_account_number === selectedBank.bank_account_number,
      ) ?? null
    )
  }, [chainPeriods, selectedBank, month])

  const loadBanks = useCallback(async () => {
    setLoadingBanks(true)
    setError(null)
    try {
      const [banksRes, chainRes] = await Promise.all([
        api.listReconciliationBanks(workspaceId),
        api.balanceChain(workspaceId).catch(() => null),
      ])
      const list = Array.isArray(banksRes?.banks) ? banksRes.banks : []
      setBanks(list)
      const periods = Array.isArray(chainRes?.periods)
        ? (chainRes.periods as ChainPeriod[])
        : []
      setChainPeriods(periods)

      if (!defaultsApplied.current && list.length > 0) {
        const first = list[0]
        setSelectedBankKey(bankKey(first))
        const latest = first.months[0] || ''
        setMonth(latest)
        setYear(latest ? latest.slice(0, 4) : '')
        defaultsApplied.current = true
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : t('common.error'))
      setBanks([])
    } finally {
      setLoadingBanks(false)
    }
  }, [workspaceId, t])

  useEffect(() => {
    defaultsApplied.current = false
    setSelectedBankKey('')
    setMonth('')
    setYear('')
    setMovements([])
    setBanks([])
  }, [workspaceId])

  useEffect(() => {
    void loadBanks()
  }, [loadBanks])

  const loadMovements = useCallback(async () => {
    if (!selectedBank || !month) {
      setMovements([])
      return
    }
    setLoading(true)
    setError(null)
    try {
      const data = await api.listMovements({
        workspace_id: workspaceId,
        tenant_id: workspaceId,
        statement_month: month,
        bank_account_number: selectedBank.bank_account_number,
        bank_name: selectedBank.bank_name,
        limit: 5000,
      })
      setMovements(Array.isArray(data) ? data : [])
    } catch (e) {
      setError(e instanceof Error ? e.message : t('common.error'))
      setMovements([])
    } finally {
      setLoading(false)
    }
  }, [workspaceId, selectedBank, month, t])

  useEffect(() => {
    void loadMovements()
  }, [loadMovements])

  // Keep month valid when bank or year changes.
  useEffect(() => {
    if (!selectedBank) {
      setMonth('')
      return
    }
    if (month && monthsForBank.includes(month)) return
    setMonth(monthsForBank[0] || '')
  }, [selectedBank, monthsForBank, month])

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
      if (selectedBank) {
        form.append('bank_name', selectedBank.bank_name)
        form.append('bank_account_number', selectedBank.bank_account_number)
      }
      if (month) form.append('statement_month', month)
      await api.uploadStatement(form)
      await loadBanks()
      await loadMovements()
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
      await loadMovements()
    } catch (e) {
      setError(e instanceof Error ? e.message : t('common.error'))
    }
  }

  async function doUnmatch(id: string) {
    try {
      await api.unmatchMovement(id)
      await loadMovements()
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

  function matchActions(m: Movement, compact = false) {
    const matched = isMatched(m)
    if (matched) {
      return (
        <button
          type="button"
          onClick={() => void doUnmatch(m.id)}
          className="inline-flex items-center gap-1 text-sm text-destructive"
        >
          <Unlink className="h-3.5 w-3.5" />
          {t('reconciliation.unmatch')}
        </button>
      )
    }
    if (matchId === m.id) {
      return (
        <div className={cn('flex items-center gap-2', compact && 'flex-wrap')}>
          <input
            className="min-w-0 flex-1 rounded border border-border px-2 py-1 text-xs"
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
      )
    }
    return (
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
    )
  }

  return (
    <div>
      <div className="mb-6 animate-fade-up">
        <h1 className="page-title">{t('reconciliation.title')}</h1>
        <p className="mt-1.5 text-muted-foreground">{t('reconciliation.subtitle')}</p>
      </div>

      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
        <label className="w-full text-sm sm:w-auto sm:min-w-[220px]">
          {t('reconciliation.bank')}
          <select
            className="mt-1 block w-full rounded-lg border border-border bg-background px-3 py-2"
            value={selectedBankKey}
            disabled={loadingBanks || banks.length === 0}
            onChange={(e) => {
              const key = e.target.value
              setSelectedBankKey(key)
              const b = banks.find((x) => bankKey(x) === key)
              const latest = b?.months[0] || ''
              setMonth(latest)
              setYear(latest ? latest.slice(0, 4) : '')
            }}
          >
            {banks.length === 0 && (
              <option value="">{t('reconciliation.selectBank')}</option>
            )}
            {banks.map((b) => (
              <option key={bankKey(b)} value={bankKey(b)}>
                {b.bank_name} · …{b.bank_account_number.slice(-4)} ({b.movement_count})
              </option>
            ))}
          </select>
        </label>
        <label className="w-full text-sm sm:w-auto">
          {t('reconciliation.year')}
          <select
            className="mt-1 block w-full rounded-lg border border-border bg-background px-3 py-2 sm:w-32"
            value={year}
            disabled={!selectedBank}
            onChange={(e) => setYear(e.target.value)}
          >
            <option value="">{t('reconciliation.yearAll')}</option>
            {years.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </label>
        <label className="w-full text-sm sm:w-auto">
          {t('reconciliation.month')}
          <select
            className="mt-1 block w-full rounded-lg border border-border bg-background px-3 py-2 sm:w-40"
            value={month}
            disabled={!selectedBank || monthsForBank.length === 0}
            onChange={(e) => setMonth(e.target.value)}
          >
            {monthsForBank.length === 0 && (
              <option value="">{t('reconciliation.selectMonth')}</option>
            )}
            {monthsForBank.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>
      </div>

      {statementPeriod && (
        <div className="mb-6 rounded-xl border border-border bg-card px-4 py-3 soft-shadow">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-medium">
                {t('reconciliation.statementHeader')} · {month}
                {selectedBank && (
                  <span className="ml-2 text-muted-foreground">
                    {selectedBank.bank_name} · …
                    {selectedBank.bank_account_number.slice(-4)}
                  </span>
                )}
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                {t('reconciliation.opening')}: {money(statementPeriod.opening_balance)}
                {' · '}
                {t('reconciliation.closing')}: {money(statementPeriod.closing_balance)}
              </p>
            </div>
            <span
              className={cn(
                'rounded-md px-2.5 py-1 text-xs font-medium',
                statementPeriod.chain_ok === true && 'bg-success text-success-foreground',
                statementPeriod.chain_ok === false && 'bg-destructive/15 text-destructive',
                statementPeriod.chain_ok == null && 'bg-secondary text-secondary-foreground',
              )}
            >
              {statementPeriod.chain_ok === true
                ? t('reconciliation.chainOk')
                : statementPeriod.chain_ok === false
                  ? t('reconciliation.chainBreak')
                  : t('reconciliation.chainUnknown')}
            </span>
          </div>
          {statementPeriod.alert_message && (
            <p className="mt-2 text-xs text-muted-foreground">{statementPeriod.alert_message}</p>
          )}
        </div>
      )}

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

      {(loadingBanks || loading) && <p className="text-muted-foreground">{t('common.loading')}</p>}

      {!loadingBanks && banks.length === 0 && (
        <div className="soft-shadow rounded-xl border border-dashed border-border bg-card px-6 py-12 text-center">
          <p className="font-medium">{t('reconciliation.noBanks')}</p>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            {t('reconciliation.emptyHint')}
          </p>
        </div>
      )}

      {!loading && !loadingBanks && banks.length > 0 && movements.length === 0 && (
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
              const conf = confidencePct(m)
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
                      </p>
                      <p className="mt-1 text-xs text-muted-foreground">{coaLabel(m)}</p>
                    </div>
                    <div className="shrink-0 text-right text-sm tabular-nums">
                      <div>{t('reconciliation.debit')}: {money(debitOf(m) || null)}</div>
                      <div>{t('reconciliation.credit')}: {money(creditOf(m) || null)}</div>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={cn(
                        'rounded-md px-2 py-0.5 text-xs font-medium',
                        matched
                          ? 'bg-success text-success-foreground'
                          : 'bg-warning text-warning-foreground',
                      )}
                    >
                      {matched
                        ? t('reconciliation.matchedYes')
                        : t('reconciliation.matchedNo')}
                    </span>
                    {conf != null && (
                      <span className="text-xs text-muted-foreground">
                        {t('reconciliation.confidence')}: {conf}%
                      </span>
                    )}
                  </div>
                  <div className="mt-3">{matchActions(m, true)}</div>
                </article>
              )
            })}
          </div>

          <div className="soft-shadow table-scroll hidden rounded-xl border border-border bg-card md:block">
            <table className="w-full min-w-[1100px] text-left text-sm">
              <thead className="border-b border-border bg-secondary/50 text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 font-medium">{t('documents.date')}</th>
                  <th className="px-4 py-3 font-medium">{t('transactions.description')}</th>
                  <th className="px-4 py-3 font-medium">{t('reconciliation.debit')}</th>
                  <th className="px-4 py-3 font-medium">{t('reconciliation.credit')}</th>
                  <th className="px-4 py-3 font-medium">{t('reconciliation.coa')}</th>
                  <th className="px-4 py-3 font-medium">{t('reconciliation.confidence')}</th>
                  <th className="px-4 py-3 font-medium">{t('reconciliation.matched')}</th>
                  <th className="px-4 py-3 font-medium">{t('common.actions')}</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((m) => {
                  const matched = isMatched(m)
                  const conf = confidencePct(m)
                  return (
                    <tr key={m.id} className="border-b border-border last:border-0">
                      <td className="px-4 py-3 whitespace-nowrap text-muted-foreground">
                        {String(m.date ?? '—')}
                      </td>
                      <td className="px-4 py-3">
                        <div className="font-medium">{m.description || m.id}</div>
                        {matched && m.transaction_id && (
                          <div className="font-mono text-xs text-muted-foreground">
                            {shortId(m.transaction_id)}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3 tabular-nums whitespace-nowrap">
                        {debitOf(m) > 0 ? money(debitOf(m)) : '—'}
                      </td>
                      <td className="px-4 py-3 tabular-nums whitespace-nowrap">
                        {creditOf(m) > 0 ? money(creditOf(m)) : '—'}
                      </td>
                      <td className="px-4 py-3 text-sm">{coaLabel(m)}</td>
                      <td className="px-4 py-3 tabular-nums whitespace-nowrap">
                        {conf != null ? `${conf}%` : '—'}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={cn(
                            'rounded-md px-2 py-0.5 text-xs font-medium',
                            matched
                              ? 'bg-success text-success-foreground'
                              : 'bg-warning text-warning-foreground',
                          )}
                        >
                          {matched
                            ? t('reconciliation.matchedYes')
                            : t('reconciliation.matchedNo')}
                        </span>
                      </td>
                      <td className="px-4 py-3">{matchActions(m)}</td>
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
