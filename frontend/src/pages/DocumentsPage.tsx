import {
  ArrowUpDown,
  FileSpreadsheet,
  FileText,
  Grid3x3,
  LayoutList,
  Lock,
  MessageCircle,
  Plus,
  Search,
  ShieldCheck,
  Sparkles,
  UploadCloud,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useOutletContext, useSearchParams } from 'react-router-dom'

import type { AuthOutletContext } from '../components/RequireAuth'
import Sidebar from '../components/Sidebar'
import { CATEGORIES } from '../lib/categories'
import { listDocuments, type DocumentOut, type SourceFormat } from '../lib/documents'

const STATUS_STYLES: Record<DocumentOut['status'], string> = {
  ready: 'bg-emerald-50 text-emerald-700',
  processing: 'bg-amber-50 text-amber-700',
  failed: 'bg-red-50 text-red-700',
}

const FORMAT_META: Record<SourceFormat, { label: string; icon: typeof FileText; className: string }> = {
  pdf: { label: 'PDF', icon: FileText, className: 'bg-red-50 text-red-500' },
  docx: { label: 'Word', icon: FileText, className: 'bg-blue-50 text-blue-500' },
  markdown: { label: 'Markdown', icon: FileText, className: 'bg-purple-50 text-purple-500' },
  text: { label: 'Text', icon: FileText, className: 'bg-slate-100 text-slate-500' },
  csv: { label: 'CSV', icon: FileSpreadsheet, className: 'bg-emerald-50 text-emerald-500' },
}

const FORMAT_FILTERS: SourceFormat[] = ['pdf', 'docx', 'text', 'markdown', 'csv']

const PAGE_SIZE = 9

function relativeDate(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const days = Math.floor(diffMs / 86_400_000)
  if (days <= 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days < 30) return `${days}d ago`
  return new Date(iso).toLocaleDateString()
}

function EmptyState() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-4 py-20 text-center">
      <div className="mb-6 flex h-24 w-24 items-center justify-center rounded-2xl bg-blue-50">
        <FileText className="h-10 w-10 text-blue-500" />
      </div>
      <h2 className="text-2xl font-bold text-slate-900">No documents yet</h2>
      <p className="mt-2 max-w-md text-sm text-slate-500">
        Upload your company policies, handbooks, or guides to start asking questions and getting
        instant, verified answers.
      </p>
      <Link
        to="/documents/upload"
        className="mt-6 flex items-center gap-2 rounded-lg bg-blue-700 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-800"
      >
        <UploadCloud className="h-4 w-4" />
        Upload your first document
      </Link>

      <div className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="flex items-start gap-3 rounded-xl bg-slate-50 p-4 text-left">
          <MessageCircle className="mt-0.5 h-5 w-5 text-blue-500" />
          <div>
            <p className="text-sm font-semibold text-slate-900">Instant Answers</p>
            <p className="text-xs text-slate-500">Natural Q&A in Chat</p>
          </div>
        </div>
        <div className="flex items-start gap-3 rounded-xl bg-slate-50 p-4 text-left">
          <Sparkles className="mt-0.5 h-5 w-5 text-blue-500" />
          <div>
            <p className="text-sm font-semibold text-slate-900">Cited Sources</p>
            <p className="text-xs text-slate-500">Direct page references</p>
          </div>
        </div>
        <div className="flex items-start gap-3 rounded-xl bg-slate-50 p-4 text-left">
          <ShieldCheck className="mt-0.5 h-5 w-5 text-blue-500" />
          <div>
            <p className="text-sm font-semibold text-slate-900">Private & Secure</p>
            <p className="text-xs text-slate-500">Access-controlled by design</p>
          </div>
        </div>
      </div>

      <p className="mt-8 text-xs text-slate-400">Supports PDF, DOCX, and text files up to 25MB</p>
    </div>
  )
}

function DocCard({ doc }: { doc: DocumentOut }) {
  const meta = FORMAT_META[doc.source_format]
  const Icon = meta.icon
  return (
    <div className="flex flex-col rounded-xl border border-slate-200 bg-white p-4 transition hover:shadow-sm">
      <div className="flex items-start justify-between">
        <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${meta.className}`}>
          <Icon className="h-5 w-5" />
        </div>
        <div className="flex items-center gap-2">
          {doc.category && (
            <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">
              {doc.category}
            </span>
          )}
          {!doc.is_public && <Lock className="h-3.5 w-3.5 text-slate-400" aria-label="Just me" />}
        </div>
      </div>
      <p className="mt-3 line-clamp-2 text-sm font-semibold text-slate-900">{doc.title}</p>
      <div className="mt-2 flex items-center gap-2">
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium capitalize ${STATUS_STYLES[doc.status]}`}>
          {doc.status}
        </span>
      </div>
      <div className="mt-auto flex items-center justify-between pt-4 text-xs text-slate-400">
        <span>Updated {relativeDate(doc.updated_at)}</span>
      </div>
    </div>
  )
}

function DocRow({ doc }: { doc: DocumentOut }) {
  const meta = FORMAT_META[doc.source_format]
  const Icon = meta.icon
  return (
    <div className="flex items-center gap-4 border-b border-slate-100 px-5 py-4 last:border-0">
      <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${meta.className}`}>
        <Icon className="h-5 w-5" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-slate-900">{doc.title}</p>
        <p className="truncate text-xs text-slate-400">{doc.filename}</p>
      </div>
      {doc.category && (
        <span className="shrink-0 rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">
          {doc.category}
        </span>
      )}
      <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium capitalize ${STATUS_STYLES[doc.status]}`}>
        {doc.status}
      </span>
      <span className="shrink-0 text-slate-400">{doc.is_public ? null : <Lock className="h-4 w-4" />}</span>
      <span className="w-20 shrink-0 text-right text-xs text-slate-400">{relativeDate(doc.updated_at)}</span>
    </div>
  )
}

export default function DocumentsPage() {
  const { token, user } = useOutletContext<AuthOutletContext>()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const category = searchParams.get('category')

  const [documents, setDocuments] = useState<DocumentOut[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [formatFilter, setFormatFilter] = useState<SourceFormat | null>(null)
  const [sort, setSort] = useState<'updated' | 'title'>('updated')
  const [view, setView] = useState<'grid' | 'list'>('grid')
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)
  const [dragActive, setDragActive] = useState(false)

  useEffect(() => {
    setDocuments(null)
    setError(null)
    setVisibleCount(PAGE_SIZE)
    listDocuments(token, category ?? undefined)
      .then(setDocuments)
      .catch((e: Error) => setError(e.message))
  }, [token, category])

  const filtered = useMemo(() => {
    if (!documents) return []
    let result = documents
    if (formatFilter) result = result.filter((d) => d.source_format === formatFilter)
    if (search.trim()) {
      const q = search.trim().toLowerCase()
      result = result.filter((d) => d.title.toLowerCase().includes(q) || d.filename.toLowerCase().includes(q))
    }
    return [...result].sort((a, b) =>
      sort === 'title' ? a.title.localeCompare(b.title) : b.updated_at.localeCompare(a.updated_at),
    )
  }, [documents, formatFilter, search, sort])

  const visible = filtered.slice(0, visibleCount)
  const heading = category ? CATEGORIES.find((c) => c.value === category)?.label ?? category : 'All Documents'

  function goToUploadWithFile(file: File) {
    navigate('/documents/upload', { state: { droppedFile: file } })
  }

  return (
    <div className="flex h-screen bg-slate-50">
      <Sidebar userEmail={user.email} />

      <div className="flex flex-1 flex-col overflow-hidden">
        <header className="flex items-center justify-between border-b border-slate-200 bg-white px-8 py-4">
          <div className="flex max-w-md flex-1 items-center gap-2 rounded-lg bg-slate-100 px-3 py-2">
            <Search className="h-4 w-4 text-slate-400" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search policies, handbooks, forms…"
              className="w-full bg-transparent text-sm text-slate-700 placeholder:text-slate-400 outline-none"
            />
          </div>
          <Link
            to="/documents/upload"
            className="flex items-center gap-2 rounded-lg bg-blue-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-800"
          >
            <Plus className="h-4 w-4" />
            Upload Document
          </Link>
        </header>

        {documents && documents.length > 0 && (
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white px-8 py-4">
            <div className="flex items-center gap-3">
              <h1 className="text-lg font-semibold text-slate-900">{heading}</h1>
              <span className="text-sm text-slate-400">{filtered.length} documents</span>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => setFormatFilter(null)}
                className={`rounded-full px-3 py-1 text-xs font-medium ${
                  formatFilter === null ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-600'
                }`}
              >
                All types
              </button>
              {FORMAT_FILTERS.map((fmt) => (
                <button
                  key={fmt}
                  type="button"
                  onClick={() => setFormatFilter((f) => (f === fmt ? null : fmt))}
                  className={`rounded-full px-3 py-1 text-xs font-medium ${
                    formatFilter === fmt ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-600'
                  }`}
                >
                  {FORMAT_META[fmt].label}
                </button>
              ))}

              <button
                type="button"
                onClick={() => setSort((s) => (s === 'updated' ? 'title' : 'updated'))}
                className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600"
              >
                <ArrowUpDown className="h-3.5 w-3.5" />
                {sort === 'updated' ? 'Last modified' : 'Title A–Z'}
              </button>

              <div className="flex items-center rounded-lg border border-slate-200 p-0.5">
                <button
                  type="button"
                  onClick={() => setView('grid')}
                  aria-label="Grid view"
                  className={`rounded-md p-1.5 ${view === 'grid' ? 'bg-slate-900 text-white' : 'text-slate-400'}`}
                >
                  <Grid3x3 className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={() => setView('list')}
                  aria-label="List view"
                  className={`rounded-md p-1.5 ${view === 'list' ? 'bg-slate-900 text-white' : 'text-slate-400'}`}
                >
                  <LayoutList className="h-4 w-4" />
                </button>
              </div>
            </div>
          </div>
        )}

        {error && <div className="m-8 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

        {!error && documents === null && (
          <div className="flex flex-1 items-center justify-center text-sm text-slate-400">Loading…</div>
        )}

        {!error && documents !== null && documents.length === 0 && <EmptyState />}

        {!error && documents !== null && documents.length > 0 && (
          <div
            className="flex-1 overflow-y-auto px-8 py-6"
            onDragOver={(e) => {
              e.preventDefault()
              setDragActive(true)
            }}
            onDragLeave={() => setDragActive(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDragActive(false)
              const f = e.dataTransfer.files?.[0]
              if (f) goToUploadWithFile(f)
            }}
          >
            {view === 'grid' ? (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {visible.map((doc) => (
                  <DocCard key={doc.id} doc={doc} />
                ))}
              </div>
            ) : (
              <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
                {visible.map((doc) => (
                  <DocRow key={doc.id} doc={doc} />
                ))}
              </div>
            )}

            {visibleCount < filtered.length && (
              <div className="mt-4 flex items-center justify-center gap-3 text-sm text-slate-500">
                <span>
                  Showing {visible.length} of {filtered.length}
                </span>
                <button
                  type="button"
                  onClick={() => setVisibleCount((c) => c + PAGE_SIZE)}
                  className="rounded-lg border border-slate-200 px-3 py-1.5 font-medium text-slate-700 hover:bg-slate-100"
                >
                  Show more
                </button>
              </div>
            )}

            <div
              className={`mt-6 flex items-center justify-between rounded-xl border-2 border-dashed px-6 py-4 transition ${
                dragActive ? 'border-blue-400 bg-blue-50' : 'border-slate-200 bg-white'
              }`}
            >
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50 text-blue-500">
                  <UploadCloud className="h-4 w-4" />
                </div>
                <div>
                  <p className="text-sm font-medium text-slate-900">Need to share an updated policy?</p>
                  <p className="text-xs text-slate-500">
                    Drag and drop files here or browse your computer to publish immediately.
                  </p>
                </div>
              </div>
              <Link
                to="/documents/upload"
                className="shrink-0 rounded-lg border border-slate-200 px-3.5 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100"
              >
                Browse Files
              </Link>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
