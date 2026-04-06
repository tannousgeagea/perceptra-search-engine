import {
  createContext, useContext, useState, useCallback, useEffect,
  type ReactNode,
} from 'react'
import type { AuthState, SessionInfo } from '../types/api'
import { getSession } from '../api/client'

interface AuthContextValue {
  auth: AuthState | null
  session: SessionInfo | null
  isAuthenticated: boolean
  login: (authData: AuthState) => void
  logout: () => void
  updateToken: (token: string) => void
  fetchSession: () => Promise<void>
  displayName: string
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [auth, setAuth] = useState<AuthState | null>(() => {
    try {
      return JSON.parse(localStorage.getItem('auth') ?? 'null')
    } catch {
      return null
    }
  })

  const [session, setSession] = useState<SessionInfo | null>(() => {
    try {
      const stored = JSON.parse(localStorage.getItem('auth') ?? 'null')
      return stored?.session ?? null
    } catch {
      return null
    }
  })

  const login = useCallback((authData: AuthState) => {
    localStorage.setItem('auth', JSON.stringify(authData))
    setAuth(authData)
    if (authData.session) {
      setSession(authData.session)
    }
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem('auth')
    setAuth(null)
    setSession(null)
  }, [])

  const updateToken = useCallback((token: string) => {
    setAuth((prev) => {
      if (!prev) return prev
      const next = { ...prev, token }
      localStorage.setItem('auth', JSON.stringify(next))
      return next
    })
  }, [])

  const fetchSession = useCallback(async () => {
    try {
      const res = await getSession()
      const sessionData = res.data
      setSession(sessionData)
      // Persist session in auth localStorage
      setAuth((prev) => {
        if (!prev) return prev
        const next = { ...prev, session: sessionData }
        localStorage.setItem('auth', JSON.stringify(next))
        return next
      })
    } catch {
      // Session fetch failed — don't clear auth, just leave session as-is
    }
  }, [])

  // On mount, refresh session from backend if authenticated
  useEffect(() => {
    if (auth && !window.location.pathname.includes('/login')) {
      fetchSession()
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const displayName =
    session?.user?.name ||
    session?.user?.email ||
    auth?.email ||
    auth?.apiKeyLabel ||
    'Inspector'

  const value: AuthContextValue = {
    auth,
    session,
    isAuthenticated: !!auth,
    login,
    logout,
    updateToken,
    fetchSession,
    displayName,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
