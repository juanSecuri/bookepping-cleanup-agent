import { useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import BrandMark from '../components/BrandMark'
import { useAuth } from '../auth/AuthProvider'
import { useLocale } from '../i18n'

type Mode = 'signin' | 'signup' | 'recover'

export default function Login() {
  const { configured, loading, session, signIn, signUp, requestPasswordReset } = useAuth()
  const { t } = useLocale()
  const navigate = useNavigate()
  const location = useLocation()
  const from =
    (location.state as { from?: string } | null)?.from || '/workspaces'

  const [mode, setMode] = useState<Mode>('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  if (!configured) {
    return <Navigate to="/workspaces" replace />
  }
  if (!loading && session && mode !== 'recover') {
    return <Navigate to={from} replace />
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    setInfo(null)
    try {
      if (mode === 'recover') {
        await requestPasswordReset(email.trim())
        setInfo(t('auth.resetSent'))
      } else if (mode === 'signup') {
        await signUp(email.trim(), password)
        setInfo(t('auth.signUpBody'))
        setMode('signin')
      } else {
        await signIn(email.trim(), password)
        navigate(from, { replace: true })
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Auth failed')
    } finally {
      setSaving(false)
    }
  }

  const title =
    mode === 'recover'
      ? t('auth.recoverTitle')
      : mode === 'signup'
        ? t('auth.signUpTitle')
        : t('auth.signInTitle')
  const body =
    mode === 'recover'
      ? t('auth.recoverBody')
      : mode === 'signup'
        ? t('auth.signUpBody')
        : t('auth.signInBody')

  return (
    <div className="relative flex min-h-dvh flex-col items-center justify-center overflow-hidden bg-background px-4">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-80"
        style={{
          background:
            'radial-gradient(ellipse 70% 50% at 50% 0%, color-mix(in srgb, var(--accent-cream) 12%, transparent), transparent 70%)',
        }}
      />
      <div className="relative w-full max-w-sm space-y-8">
        <div className="flex flex-col items-center gap-3 text-center">
          <BrandMark size="md" />
          <h1 className="font-display text-2xl text-foreground">{title}</h1>
          <p className="text-sm text-muted-foreground">{body}</p>
        </div>
        <form onSubmit={onSubmit} className="space-y-4">
          <label className="block space-y-1.5 text-sm">
            <span className="text-muted-foreground">{t('auth.email')}</span>
            <input
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-md border border-border bg-card px-3 py-2 text-foreground outline-none focus:ring-1 focus:ring-primary"
            />
          </label>
          {mode !== 'recover' ? (
            <label className="block space-y-1.5 text-sm">
              <span className="text-muted-foreground">{t('auth.password')}</span>
              <input
                type="password"
                autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
                required
                minLength={6}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-md border border-border bg-card px-3 py-2 text-foreground outline-none focus:ring-1 focus:ring-primary"
              />
            </label>
          ) : null}
          {error ? (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          ) : null}
          {info ? (
            <p className="text-sm text-muted-foreground" role="status">
              {info}
            </p>
          ) : null}
          <button
            type="submit"
            disabled={saving}
            className="w-full rounded-md bg-primary px-3 py-2.5 text-sm font-medium text-primary-foreground disabled:opacity-60"
          >
            {saving
              ? mode === 'recover'
                ? t('auth.sending')
                : mode === 'signin'
                  ? t('auth.signingIn')
                  : t('auth.creating')
              : mode === 'recover'
                ? t('auth.sendReset')
                : mode === 'signin'
                  ? t('auth.signIn')
                  : t('auth.signUp')}
          </button>
        </form>
        <p className="text-center text-sm text-muted-foreground">
          {mode === 'signin' ? (
            <button
              type="button"
              className="underline-offset-2 hover:underline"
              onClick={() => {
                setMode('recover')
                setError(null)
                setInfo(null)
              }}
            >
              {t('auth.forgot')}
            </button>
          ) : (
            <button
              type="button"
              className="underline-offset-2 hover:underline"
              onClick={() => {
                setMode('signin')
                setError(null)
                setInfo(null)
              }}
            >
              {t('auth.backToSignIn')}
            </button>
          )}
          {mode !== 'recover' ? (
            <>
              {' · '}
              <button
                type="button"
                className="underline-offset-2 hover:underline"
                onClick={() => {
                  setMode((m) => (m === 'signin' ? 'signup' : 'signin'))
                  setError(null)
                  setInfo(null)
                }}
              >
                {mode === 'signin' ? t('auth.needAccount') : t('auth.haveAccount')}
              </button>
            </>
          ) : null}
          {' · '}
          <Link to="/" className="underline-offset-2 hover:underline">
            {t('auth.home')}
          </Link>
        </p>
      </div>
    </div>
  )
}
