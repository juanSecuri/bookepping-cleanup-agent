import { useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import BrandMark from '../components/BrandMark'
import { useAuth } from '../auth/AuthProvider'

export default function Login() {
  const { configured, loading, session, signIn, signUp } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from =
    (location.state as { from?: string } | null)?.from || '/workspaces'

  const [mode, setMode] = useState<'signin' | 'signup'>('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  if (!configured) {
    return <Navigate to="/workspaces" replace />
  }
  if (!loading && session) {
    return <Navigate to={from} replace />
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    setInfo(null)
    try {
      if (mode === 'signup') {
        await signUp(email.trim(), password)
        setInfo('Account created. If email confirmation is on, check your inbox; otherwise sign in.')
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
          <h1 className="font-display text-2xl text-foreground">
            {mode === 'signin' ? 'Sign in' : 'Create account'}
          </h1>
          <p className="text-sm text-muted-foreground">
            LedgerAI uses your Supabase account (email + password).
          </p>
        </div>
        <form onSubmit={onSubmit} className="space-y-4">
          <label className="block space-y-1.5 text-sm">
            <span className="text-muted-foreground">Email</span>
            <input
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-md border border-border bg-card px-3 py-2 text-foreground outline-none focus:ring-1 focus:ring-primary"
            />
          </label>
          <label className="block space-y-1.5 text-sm">
            <span className="text-muted-foreground">Password</span>
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
              ? mode === 'signin'
                ? 'Signing in…'
                : 'Creating…'
              : mode === 'signin'
                ? 'Sign in'
                : 'Sign up'}
          </button>
        </form>
        <p className="text-center text-sm text-muted-foreground">
          <button
            type="button"
            className="underline-offset-2 hover:underline"
            onClick={() => {
              setMode((m) => (m === 'signin' ? 'signup' : 'signin'))
              setError(null)
              setInfo(null)
            }}
          >
            {mode === 'signin' ? 'Need an account? Sign up' : 'Have an account? Sign in'}
          </button>
          {' · '}
          <Link to="/" className="underline-offset-2 hover:underline">
            Home
          </Link>
        </p>
      </div>
    </div>
  )
}
