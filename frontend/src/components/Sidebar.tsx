import { FileText, MessageSquare, User as UserIcon } from 'lucide-react'
import { NavLink, useSearchParams } from 'react-router-dom'

import { CATEGORIES } from '../lib/categories'

function navLinkClasses(active: boolean) {
  return `block rounded-lg px-3 py-2 text-sm font-medium ${
    active ? 'bg-blue-50 text-blue-700' : 'text-slate-600 hover:bg-slate-100'
  }`
}

export default function Sidebar({ userEmail }: { userEmail: string }) {
  const [searchParams] = useSearchParams()
  const activeCategory = searchParams.get('category')

  return (
    <aside className="flex h-screen w-64 flex-col border-r border-slate-200 bg-white">
      <div className="flex items-center gap-2 px-5 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-900">
          <FileText className="h-4 w-4 text-white" />
        </div>
        <span className="text-lg font-semibold text-slate-900">DocIntel</span>
      </div>

      <nav className="flex-1 overflow-y-auto px-3">
        <p className="px-3 pb-2 text-xs font-semibold tracking-wide text-slate-400">WORKSPACE</p>

        <NavLink to="/documents" end className={({ isActive }) => navLinkClasses(isActive && !activeCategory)}>
          All Documents
        </NavLink>

        {CATEGORIES.map((cat) => (
          <NavLink
            key={cat.value}
            to={`/documents?category=${encodeURIComponent(cat.value)}`}
            className={navLinkClasses(activeCategory === cat.value)}
          >
            {cat.label}
          </NavLink>
        ))}

        <div
          title="Chat isn't built yet"
          className="mt-1 flex cursor-not-allowed items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-slate-300"
        >
          <MessageSquare className="h-4 w-4" />
          Chat
        </div>
      </nav>

      <div className="flex items-center gap-2 border-t border-slate-200 px-4 py-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-600 text-white">
          <UserIcon className="h-4 w-4" />
        </div>
        <span className="truncate text-sm font-medium text-slate-700">{userEmail}</span>
      </div>
    </aside>
  )
}
