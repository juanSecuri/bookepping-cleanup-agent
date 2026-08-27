import { Navigate, useLocation } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useAuth } from './AuthProvider'

/** When Supabase Vite env is set, block /app/* until there is a session. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { configured, loading, session } = useAuth()
  const location = useLocation()

  if (!configured) return children
  if (loading) {
    return (
      <div className="flex min-h-dvh flex-col items-center justify-center gap-3 bg-background text-muted-foreground">
        <p className="text-sm">Verificando sesión…</p>
        <button
          type="button"
          className="text-xs underline-offset-2 hover:underline"
          onClick={() => window.location.reload()}
        >
          Recargar
        </button>
      </div>
    )
  }
  if (!session) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return children
}
