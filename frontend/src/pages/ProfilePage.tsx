import { ArrowLeft, Calendar, LogOut, User as UserIcon } from 'lucide-react'
import { Link, useNavigate, useOutletContext } from 'react-router-dom'

import type { AuthOutletContext } from '../components/RequireAuth'
import { clearToken } from '../lib/auth'

export default function ProfilePage() {
  const { user } = useOutletContext<AuthOutletContext>()
  const navigate = useNavigate()

  function handleSignOut() {
    clearToken()
    navigate('/login', { replace: true })
  }

  // Format the ISO join date to something readable
  const joinDate = new Date(user.created_at).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })

  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      <header className="flex h-16 shrink-0 items-center border-b border-slate-200 bg-white px-8">
        <Link
          to="/chat"
          className="flex items-center gap-1.5 text-sm font-medium text-slate-500 transition hover:text-slate-900"
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </Link>
      </header>

      <main className="mx-auto w-full max-w-2xl px-6 py-12 flex-1">
        <h1 className="text-3xl font-bold text-slate-900">Your Profile</h1>
        <p className="mt-2 text-sm text-slate-500">Manage your account settings and preferences.</p>

        <div className="mt-8 overflow-hidden rounded-2xl bg-white shadow-sm border border-slate-100">
          <div className="p-8">
            <div className="flex items-center gap-5">
              <div className="flex h-20 w-20 items-center justify-center rounded-full bg-blue-100 text-blue-600">
                <UserIcon className="h-10 w-10" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-slate-900">{user.email}</h2>
                <div className="mt-1 flex items-center gap-1.5 text-sm text-slate-500">
                  <Calendar className="h-4 w-4" />
                  <span>Joined {joinDate}</span>
                </div>
              </div>
            </div>
          </div>
          
          <div className="border-t border-slate-100 bg-slate-50 p-6">
            <h3 className="text-sm font-semibold text-slate-900">Account Actions</h3>
            <p className="mt-1 mb-4 text-xs text-slate-500">
              You are currently signed in as {user.email}.
            </p>
            <button
              onClick={handleSignOut}
              className="flex items-center gap-2 rounded-lg bg-white border border-slate-200 px-4 py-2 text-sm font-semibold text-red-600 shadow-sm transition hover:bg-red-50 hover:border-red-200"
            >
              <LogOut className="h-4 w-4" />
              Sign Out
            </button>
          </div>
        </div>
      </main>
    </div>
  )
}
