import { FileText, MessageSquare, User as UserIcon } from 'lucide-react'
import { NavLink, useSearchParams } from 'react-router-dom'

import { useCategories } from '../lib/categories'

function navLinkClasses(active: boolean) {
  return `block rounded-lg px-3 py-2 text-sm font-medium ${
    active ? 'bg-blue-50 text-blue-700' : 'text-slate-600 hover:bg-slate-100'
  }`
}

export default function Sidebar({ userEmail, token }: { userEmail: string; token: string }) {
  const [searchParams] = useSearchParams()
  const activeCategory = searchParams.get('category')
  const { categories } = useCategories(token)

  return (
    <aside className="flex h-screen w-64 flex-col border-r border-slate-200 bg-white">
      <div className="flex items-center gap-2 px-5 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-900">
          <FileText className="h-4 w-4 text-white" />
        </div>
        <span className="text-lg font-semibold text-slate-900">DocIntel</span>
      </div>

      <nav className="flex-1 overflow-y-auto px-3">
        <NavLink to="/chat" className={({ isActive }) => navLinkClasses(isActive)}>
          <div className="flex items-center gap-2">
            <MessageSquare className="h-4 w-4" />
            Chat
          </div>
        </NavLink>

        <NavLink to="/documents" end className={({ isActive }) => navLinkClasses(isActive && !activeCategory)}>
          <div className="flex items-center gap-2">
            <FileText className="h-4 w-4" />
            All Documents
          </div>
        </NavLink>

        {categories.map((cat) => (
          <NavLink
            key={cat}
            to={`/documents?category=${encodeURIComponent(cat)}`}
            className={navLinkClasses(activeCategory === cat)}
          >
            {cat}
          </NavLink>
        ))}


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
