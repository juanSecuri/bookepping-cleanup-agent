import { useEffect, useState } from 'react'
import { useLocale } from '../i18n'
import { cn } from '../lib/utils'

const API_BASE = import.meta.env.VITE_API_URL || ''

/**
 * Render Free cold-start banner: pings /health until the instance is awake.
 */
export default function ColdStartBanner() {
  const { t } = useLocale()
  const [waking, setWaking] = useState(false)
  const [dismissed, setDismissed] = useState(false)
  const [ms, setMs] = useState(0)

  useEffect(() => {
    let cancelled = false
    let timer: number | undefined
    const started = performance.now()

    async function ping() {
      const ctrl = new AbortController()
      const timeout = window.setTimeout(() => ctrl.abort(), 2500)
      try {
        const res = await fetch(`${API_BASE}/health`, {
          signal: ctrl.signal,
          cache: 'no-store',
        })
        window.clearTimeout(timeout)
        if (cancelled) return
        if (res.ok) {
          setWaking(false)
          setMs(Math.round(performance.now() - started))
          return
        }
      } catch {
        window.clearTimeout(timeout)
      }
      if (cancelled) return
      setWaking(true)
      setMs(Math.round(performance.now() - started))
      timer = window.setTimeout(() => {
        void ping()
      }, 2000)
    }

    // If first response is slow, show banner immediately after 1.2s
    const slow = window.setTimeout(() => {
      if (!cancelled) setWaking(true)
    }, 1200)

    void ping().finally(() => window.clearTimeout(slow))

    return () => {
      cancelled = true
      if (timer) window.clearTimeout(timer)
      window.clearTimeout(slow)
    }
  }, [])

  if (dismissed || !waking) return null

  return (
    <div
      role="status"
      className={cn(
        'fixed inset-x-0 top-0 z-[60] border-b border-amber-500/40 bg-amber-50 px-4 py-2.5 text-amber-950 shadow-sm',
      )}
    >
      <div className="mx-auto flex max-w-5xl items-center justify-between gap-3">
        <p className="text-sm leading-snug">
          <span className="font-semibold">{t('coldStart.title')}</span>{' '}
          {t('coldStart.body')}
          {ms > 0 && (
            <span className="ml-1 text-amber-800/70">({Math.round(ms / 1000)}s)</span>
          )}
        </p>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          className="shrink-0 cursor-pointer rounded-md border border-amber-700/20 bg-white/70 px-2 py-1 text-xs font-medium transition hover:bg-white"
        >
          {t('coldStart.dismiss')}
        </button>
      </div>
    </div>
  )
}
