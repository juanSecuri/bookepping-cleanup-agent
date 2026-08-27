import { createClient, type Session, type SupabaseClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL?.trim() || ''
const anon = import.meta.env.VITE_SUPABASE_ANON_KEY?.trim() || ''

/** True when frontend auth gate should run (both Vite env vars present). */
export const authConfigured = Boolean(url && anon)

let client: SupabaseClient | null = null

export function getSupabase(): SupabaseClient | null {
  if (!authConfigured) return null
  if (!client) {
    client = createClient(url, anon, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
    })
  }
  return client
}

const TOKEN_KEY = 'ledgerai.access_token'

export function getStoredAccessToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setStoredAccessToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* ignore */
  }
}

export function syncTokenFromSession(session: Session | null): void {
  setStoredAccessToken(session?.access_token ?? null)
}
