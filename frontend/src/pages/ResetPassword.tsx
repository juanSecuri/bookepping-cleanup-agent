import { useEffect, useState, type FormEvent } from 'react'
import { Link, Navigate } from 'react-router-dom'
import type { AuthChangeEvent } from '@supabase/supabase-js'
import BrandMark from '../components/BrandMark'
import { useAuth } from '../auth/AuthProvider'
import { useLocale } from '../i18n'
import { authConfigured, getSupabase } from '../lib/supabase'

function recoveryInUrl(): boolean {
  const hash = window.location.hash
  const search = window.location.search
  return (
    hash.includes('type=recovery') ||
    search.includes('type=recovery') ||
    hash.includes('access_token=') ||
    search.includes('code=')
  )
}

export default function ResetPassword() {
  const { configured, loading, session, updatePassword } = useAuth()
  const { t } = useLocale()
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [fromRecovery, setFromRecovery] = useState(recoveryInUrl)
  const [done, setDone] = useState(false)

  useEffect(() => {
    const sb = getSupabase()
    if (!sb) return
    const { data } = sb.auth.onAuthStateChange((event: AuthChangeEvent) => {
      if (event === 'PASSWORD_RECOVERY') setFromRecovery(true)
    })
    return () => data.subscription.unsubscribe()
  }, [])

  if (!configured && !authConfigured) {
    return <Navigate to="/login" replace />
  }
  if (!configured) {
    return <Navigate to="/workspaces" replace />
  }

  const canSetPassword = fromRecovery || Boolean(session)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setInfo(null)
    if (password !== confirm) {
      setError(t('auth.passwordMismatch'))
      return
    }
    setSaving(true)
    try {
      await updatePassword(password)
      setDone(true)
      setInfo(t('auth.resetDone'))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Auth failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="relative flex min-h-dvh flex-col items-center justify-center overflow-hidden bg-background px-4">
      <div className="relative w-full max-w-sm space-y-8">
        <div className="flex flex-col items-center gap-3 text-center">
          <BrandMark size="md" />
          <h1 className="font-display text-2xl text-foreground">{t('auth.resetTitle')}</h1>
          <p className="text-sm text-muted-foreground">
            {canSetPassword ? t('auth.resetBody') : t('auth.resetMissing')}
          </p>
        </div>
        {loading ? (
          <p className="text-center text-sm text-muted-foreground">{t('auth.resetBody')}</p>
        ) : canSetPassword && !done ? (
          <form onSubmit={onSubmit} className="space-y-4">
            <label className="block space-y-1.5 text-sm">
              <span className="text-muted-foreground">{t('auth.newPassword')}</span>
              <input
                type="password"
                autoComplete="new-password"
                required
                minLength={6}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-md border border-border bg-card px-3 py-2 text-foreground outline-none focus:ring-1 focus:ring-primary"
              />
            </label>
            <label className="block space-y-1.5 text-sm">
              <span className="text-muted-foreground">{t('auth.confirmPassword')}</span>
              <input
                type="password"
                autoComplete="new-password"
                required
                minLength={6}
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                className="w-full rounded-md border border-border bg-card px-3 py-2 text-foreground outline-none focus:ring-1 focus:ring-primary"
              />
            </label>
            {error ? (
              <p className="text-sm text-destructive" role="alert">
                {error}
              </p>
            ) : null}
            <button
              type="submit"
              disabled={saving}
              className="w-full rounded-md bg-primary px-3 py-2.5 text-sm font-medium text-primary-foreground disabled:opacity-60"
            >
              {saving ? t('auth.savingPassword') : t('auth.savePassword')}
            </button>
          </form>
        ) : (
          <p className="text-center text-sm text-muted-foreground" role="status">
            {info ?? t('auth.resetMissing')}
          </p>
        )}
        <p className="text-center text-sm text-muted-foreground">
          <Link to="/login" className="underline-offset-2 hover:underline">
            {done ? t('auth.signIn') : t('auth.requestNewLink')}
          </Link>
        </p>
      </div>
    </div>
  )
}
