import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import type { Session, User } from '@supabase/supabase-js'
import {
  authConfigured,
  getSupabase,
  syncTokenFromSession,
} from '../lib/supabase'

type AuthContextValue = {
  configured: boolean
  loading: boolean
  session: Session | null
  user: User | null
  signIn: (email: string, password: string) => Promise<void>
  signUp: (email: string, password: string) => Promise<void>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(authConfigured)
  const [session, setSession] = useState<Session | null>(null)

  useEffect(() => {
    if (!authConfigured) {
      setLoading(false)
      return
    }
    const sb = getSupabase()
    if (!sb) {
      setLoading(false)
      return
    }

    let cancelled = false
    void sb.auth.getSession().then(({ data }) => {
      if (cancelled) return
      setSession(data.session)
      syncTokenFromSession(data.session)
      setLoading(false)
    })

    const { data: sub } = sb.auth.onAuthStateChange((_event, next) => {
      setSession(next)
      syncTokenFromSession(next)
      setLoading(false)
    })

    return () => {
      cancelled = true
      sub.subscription.unsubscribe()
    }
  }, [])

  const signIn = useCallback(async (email: string, password: string) => {
    const sb = getSupabase()
    if (!sb) throw new Error('Supabase auth is not configured')
    const { error } = await sb.auth.signInWithPassword({ email, password })
    if (error) throw error
  }, [])

  const signUp = useCallback(async (email: string, password: string) => {
    const sb = getSupabase()
    if (!sb) throw new Error('Supabase auth is not configured')
    const { error } = await sb.auth.signUp({ email, password })
    if (error) throw error
  }, [])

  const signOut = useCallback(async () => {
    const sb = getSupabase()
    if (!sb) return
    await sb.auth.signOut()
    syncTokenFromSession(null)
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      configured: authConfigured,
      loading,
      session,
      user: session?.user ?? null,
      signIn,
      signUp,
      signOut,
    }),
    [loading, session, signIn, signUp, signOut],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
