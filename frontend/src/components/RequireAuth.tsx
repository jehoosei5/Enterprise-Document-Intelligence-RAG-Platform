import { useEffect, useState } from 'react'
import { Navigate, Outlet } from 'react-router-dom'

import { clearToken, fetchCurrentUser, getToken, type UserOut } from '../lib/auth'

export interface AuthOutletContext {
  user: UserOut
  token: string
}

export default function RequireAuth() {
  const [status, setStatus] = useState<'checking' | 'authed' | 'unauthed'>('checking')
  const [context, setContext] = useState<AuthOutletContext | null>(null)

  useEffect(() => {
    const token = getToken()
    if (!token) {
      setStatus('unauthed')
      return
    }
    fetchCurrentUser(token)
      .then((user) => {
        setContext({ user, token })
        setStatus('authed')
      })
      .catch(() => {
        clearToken()
        setStatus('unauthed')
      })
  }, [])

  if (status === 'checking') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 text-sm text-slate-400">
        Loading…
      </div>
    )
  }

  if (status === 'unauthed' || !context) {
    return <Navigate to="/login" replace />
  }

  return <Outlet context={context} />
}
