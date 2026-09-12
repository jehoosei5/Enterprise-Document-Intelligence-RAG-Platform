import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Files,
  Globe2,
  Lock,
  Search,
  ShieldCheck,
  UploadCloud,
  X,
} from 'lucide-react'
import { useRef, useState } from 'react'
import { useLocation, useNavigate, useOutletContext } from 'react-router-dom'

import type { AuthOutletContext } from '../components/RequireAuth'
import { ApiError } from '../lib/api'
import { useCategories } from '../lib/categories'
import { uploadDocument } from '../lib/documents'

function stripExtension(filename: string): string {
  const idx = filename.lastIndexOf('.')
  return idx > 0 ? filename.slice(0, idx) : filename
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const mb = bytes / (1024 * 1024)
  return mb >= 1 ? `${mb.toFixed(1)} MB` : `${(bytes / 1024).toFixed(0)} KB`
}

export default function UploadPage() {
  const { token } = useOutletContext<AuthOutletContext>()
  const navigate = useNavigate()
  const location = useLocation()

  // A file dropped on the "Need to share an updated policy?" banner over
  // on DocumentsPage arrives here via router state, pre-selected.
  const droppedFile = (location.state as { droppedFile?: File } | null)?.droppedFile ?? null

  const [file, setFile] = useState<File | null>(droppedFile)
  const [dragActive, setDragActive] = useState(false)
  const [title, setTitle] = useState(droppedFile ? stripExtension(droppedFile.name) : '')
  const [category, setCategory] = useState('')
  const [isPublic, setIsPublic] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const { categories } = useCategories(token)

  function selectFile(f: File) {
    setFile(f)
    setTitle(stripExtension(f.name))
    setError(null)
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragActive(false)
    const dropped = e.dataTransfer.files?.[0]
    if (dropped) selectFile(dropped)
  }

  async function handleSubmit() {
    if (!file || !title.trim()) return
    const effectiveCategory = category.trim() || null
    setLoading(true)
    setError(null)
    try {
      await uploadDocument(token, { file, title: title.trim(), category: effectiveCategory, isPublic })
      navigate('/documents')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Upload failed. Please try again.')
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-8 py-4">
        <div className="flex max-w-md flex-1 items-center gap-2 rounded-lg bg-slate-100 px-3 py-2">
          <Search className="h-4 w-4 text-slate-400" />
          <input
            disabled
            placeholder="Search policies, files, agreements…"
            className="w-full bg-transparent text-sm text-slate-500 placeholder:text-slate-400 outline-none"
          />
        </div>
      </header>

      <div className="mx-auto max-w-3xl px-6 py-8">
        <button
          type="button"
          onClick={() => navigate('/documents')}
          className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Documents
        </button>

        <h1 className="mt-3 text-3xl font-bold text-slate-900">Upload document</h1>
        <p className="mt-1 text-sm text-slate-500">
          Add policies, guides, or team forms to your organization's knowledge library.
        </p>

        <div className="mt-6 rounded-2xl bg-white p-6 shadow-sm">
          {!file ? (
            <div
              onDragOver={(e) => {
                e.preventDefault()
                setDragActive(true)
              }}
              onDragLeave={() => setDragActive(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-14 text-center transition ${
                dragActive ? 'border-blue-400 bg-blue-50' : 'border-slate-200'
              }`}
            >
              <UploadCloud className="h-10 w-10 text-blue-400" />
              <p className="mt-4 text-sm font-semibold text-slate-700">Drag a file here or click to upload</p>
              <p className="mt-1 text-xs text-slate-400">
                Supports PDF, Word (.docx), and Plain Text (.txt/.md/.csv) up to 25MB
              </p>
              <span className="mt-4 flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600">
                <Files className="h-3.5 w-3.5" />
                Browse files
              </span>
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.docx,.txt,.md,.csv"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0]
                  if (f) selectFile(f)
                }}
              />
            </div>
          ) : (
            <div className="rounded-xl bg-slate-50 px-4 py-3">
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-100 text-blue-600">
                  <Files className="h-4 w-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-slate-900">{file.name}</p>
                  <p className="text-xs text-slate-400">{formatBytes(file.size)}</p>
                </div>
                <span className="flex items-center gap-1 text-xs font-medium text-emerald-600">
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  Ready to organize
                </span>
                <button
                  type="button"
                  onClick={() => setFile(null)}
                  aria-label="Remove file"
                  className="text-slate-400 hover:text-slate-600"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="mt-3 h-1.5 rounded-full bg-emerald-500" />
            </div>
          )}

          {file && (
            <div className="mt-6 space-y-6">
              <div>
                <div className="mb-1.5 flex items-center justify-between">
                  <label htmlFor="title" className="text-sm font-medium text-slate-700">
                    Document Title
                  </label>
                  <span className="text-xs text-slate-400">Required</span>
                </div>
                <input
                  id="title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full rounded-lg bg-slate-100 px-3.5 py-2.5 text-sm text-slate-900 outline-none ring-blue-500 focus:ring-2"
                />
                <p className="mt-1.5 text-xs text-slate-400">
                  A clear, specific title helps your team find this policy instantly in chat and search
                  queries.
                </p>
              </div>

              <div>
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-sm font-medium text-slate-700">Category Tag</span>
                  <span className="text-xs text-slate-400 text-red-500">Required</span>
                </div>
                {categories.length > 0 && (
                  <div className="mb-3 flex flex-wrap items-center gap-2">
                    {categories.map((cat) => (
                      <button
                        key={cat}
                        type="button"
                        onClick={() => setCategory(cat)}
                        className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition ${
                          category === cat
                            ? 'bg-blue-700 text-white'
                            : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                        }`}
                      >
                        {category === cat && <CheckCircle2 className="mr-1 inline h-3.5 w-3.5" />}
                        {cat}
                      </button>
                    ))}
                  </div>
                )}
                <input
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  placeholder="e.g. Policies, Guides, Onboarding"
                  className="w-full rounded-lg bg-slate-100 px-3.5 py-2.5 text-sm text-slate-900 outline-none ring-blue-500 focus:ring-2"
                />
              </div>

              <div>
                <p className="mb-2 text-sm font-medium text-slate-700">Who can access this document?</p>
                <div className="grid grid-cols-2 gap-3">
                  <button
                    type="button"
                    onClick={() => setIsPublic(false)}
                    className={`rounded-xl border-2 p-4 text-left transition ${
                      !isPublic ? 'border-blue-600' : 'border-slate-200'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-100">
                        <Lock className="h-4 w-4 text-slate-600" />
                      </div>
                      {!isPublic && <CheckCircle2 className="h-4 w-4 text-blue-600" />}
                    </div>
                    <p className="mt-2 text-sm font-semibold text-slate-900">Just me</p>
                    <p className="text-xs text-slate-500">Only visible to you.</p>
                  </button>
                  <button
                    type="button"
                    onClick={() => setIsPublic(true)}
                    className={`rounded-xl border-2 p-4 text-left transition ${
                      isPublic ? 'border-blue-600' : 'border-slate-200'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-100">
                        <Globe2 className="h-4 w-4 text-slate-600" />
                      </div>
                      {isPublic && <CheckCircle2 className="h-4 w-4 text-blue-600" />}
                    </div>
                    <p className="mt-2 text-sm font-semibold text-slate-900">Everyone at the company</p>
                    <p className="text-xs text-slate-500">Visible to all employees.</p>
                  </button>
                </div>
              </div>

              {error && <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

              <div className="flex items-center justify-between border-t border-slate-100 pt-5">
                <p className="max-w-sm text-xs text-slate-400">
                  {isPublic
                    ? 'Once uploaded, everyone in your company can find and ask questions about this in Search and Chat.'
                    : 'Only visible to you until you share it.'}
                </p>
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => navigate('/documents')}
                    className="rounded-lg px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    disabled={loading || !title.trim() || !category.trim()}
                    onClick={handleSubmit}
                    className="flex items-center gap-2 rounded-lg bg-blue-700 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-800 disabled:opacity-60"
                  >
                    {loading ? 'Uploading…' : 'Done'}
                    {!loading && <ArrowRight className="h-4 w-4" />}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="flex items-start gap-3 rounded-xl bg-white p-4 shadow-sm">
            <UploadCloud className="mt-0.5 h-5 w-5 text-blue-500" />
            <div>
              <p className="text-sm font-semibold text-slate-900">Automatic Indexing</p>
              <p className="text-xs text-slate-500">Ready for instant search and Q&A within moments.</p>
            </div>
          </div>
          <div className="flex items-start gap-3 rounded-xl bg-white p-4 shadow-sm">
            <ShieldCheck className="mt-0.5 h-5 w-5 text-blue-500" />
            <div>
              <p className="text-sm font-semibold text-slate-900">Role-based Safety</p>
              <p className="text-xs text-slate-500">Access boundaries applied as soon as the file is saved.</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
