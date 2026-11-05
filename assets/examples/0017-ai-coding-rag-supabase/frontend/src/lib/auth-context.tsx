import {
  createContext,
  useContext,
  useEffect,
  useState,
  type PropsWithChildren,
} from 'react'
import type { Session } from '@supabase/supabase-js'
import { supabase } from '@/lib/supabase'

interface AuthContextValue {
  session: Session | null
  isLoading: boolean
  error: string | null
}

const AuthContext = createContext<AuthContextValue | null>(null)

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Unable to load the sign-in session.'
}

export function AuthProvider({ children }: PropsWithChildren) {
  const [session, setSession] = useState<Session | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      if (active) {
        setSession(nextSession)
        setError(null)
        setIsLoading(false)
      }
    })

    void supabase.auth
      .getSession()
      .then(({ data, error: sessionError }) => {
        if (!active) return
        if (sessionError) {
          setError(sessionError.message)
          return
        }
        setSession(data.session)
      })
      .catch((sessionError: unknown) => {
        if (active) setError(errorMessage(sessionError))
      })
      .finally(() => {
        if (active) setIsLoading(false)
      })

    return () => {
      active = false
      subscription.unsubscribe()
    }
  }, [])

  return (
    <AuthContext.Provider value={{ session, isLoading, error }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used inside AuthProvider.')
  }
  return context
}
