import DOMPurify from 'dompurify'
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Download,
  Edit3,
  FileSpreadsheet,
  FileText,
  Flame,
  Loader2,
  Lock,
  Maximize2,
  MessageSquare,
  Minus,
  MoreVertical,
  Pencil,
  Plus as PlusIcon,
  Search,
  Send,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react'
import mammoth from 'mammoth'
import Mark from 'mark.js'
import MarkdownIt from 'markdown-it'
import * as pdfjsLib from 'pdfjs-dist'
import type { PDFDocumentProxy } from 'pdfjs-dist'
import pdfjsWorkerSrc from 'pdfjs-dist/build/pdf.worker.mjs?url'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useOutletContext, useParams } from 'react-router-dom'

import type { AuthOutletContext } from '../components/RequireAuth'
import Sidebar from '../components/Sidebar'
import { parseCsv } from '../lib/csv'
import {
  deleteDocument,
  EDITABLE_FORMATS,
  formatFileSize,
  getDocument,
  getDocumentFile,
  updateDocument,
  updateDocumentContent,
  type DocumentOut,
  type SourceFormat,
} from '../lib/documents'
import { askQuery, getDocumentQuestions, type QueryLogSummary, type SourceOut } from '../lib/query'

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorkerSrc

const md = new MarkdownIt()

/* ── Shared metadata ───────────────────────────────────────────── */

const FORMAT_META: Record<SourceFormat, { label: string; icon: typeof FileText; badgeClass: string; iconClass: string }> = {
  pdf:      { label: 'PDF',      icon: FileText,        badgeClass: 'bg-red-50 text-red-600',     iconClass: 'text-red-500' },
  docx:     { label: 'Word',     icon: FileText,        badgeClass: 'bg-blue-50 text-blue-600',   iconClass: 'text-blue-500' },
  markdown: { label: 'Markdown', icon: FileText,        badgeClass: 'bg-purple-50 text-purple-600', iconClass: 'text-purple-500' },
  text:     { label: 'Text',     icon: FileText,        badgeClass: 'bg-slate-100 text-slate-600', iconClass: 'text-slate-500' },
  csv:      { label: 'CSV',      icon: FileSpreadsheet, badgeClass: 'bg-emerald-50 text-emerald-600', iconClass: 'text-emerald-500' },
}

const STATUS_LABELS: Record<DocumentOut['status'], { label: string; className: string }> = {
  ready:      { label: 'Indexed & Searchable', className: 'bg-emerald-50 text-emerald-700 border border-emerald-200' },
  processing: { label: 'Processing…',          className: 'bg-amber-50 text-amber-700 border border-amber-200' },
  failed:     { label: 'Failed',               className: 'bg-red-50 text-red-700 border border-red-200' },
}

const CATEGORY_STYLES: Record<string, string> = {
  'HR Policy':  'bg-rose-100 text-rose-700',
  Benefits:     'bg-blue-100 text-blue-700',
  Contracts:    'bg-amber-100 text-amber-700',
  Onboarding:   'bg-violet-100 text-violet-700',
}
const DEFAULT_CATEGORY_STYLE = 'bg-slate-100 text-slate-600'

/* ── Helpers ───────────────────────────────────────────────────── */

function relativeDate(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const days = Math.floor(diffMs / 86_400_000)
  if (days <= 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days < 30) return `${days}d ago`
  return new Date(iso).toLocaleDateString()
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })
}

/* ── Preview types ─────────────────────────────────────────────── */

type Preview =
  | { kind: 'pdf'; blob: Blob }
  | { kind: 'text'; text: string }
  | { kind: 'csv'; rows: string[][] }
  | { kind: 'html'; html: string }

function buildPreview(format: SourceFormat, text: string): Preview {
  if (format === 'csv') return { kind: 'csv', rows: parseCsv(text) }
  if (format === 'markdown') return { kind: 'html', html: DOMPurify.sanitize(md.render(text)) }
  return { kind: 'text', text }
}

/* ── Search Hook ───────────────────────────────────────────────── */

export interface DocumentSearch {
  query: string
  setQuery: (q: string) => void
  totalMatches: number
  currentIndex: number
  nextMatch: () => void
  prevMatch: () => void
}

function useDocumentSearch(containerId: string): DocumentSearch {
  const [query, setQuery] = useState('')
  const [totalMatches, setTotalMatches] = useState(0)
  const [currentIndex, setCurrentIndex] = useState(0)

  const markInstanceRef = useRef<Mark | null>(null)
  const queryRef = useRef(query)
  queryRef.current = query

  const scrollToMatch = useCallback(
    (index: number) => {
      const container = document.getElementById(containerId)
      if (!container) return
      const marks = container.querySelectorAll('mark.doc-search-match')

      marks.forEach((m) => {
        m.classList.remove('bg-orange-400', 'text-white')
        m.classList.add('bg-yellow-300', 'text-black')
      })

      if (marks.length > 0 && index < marks.length && index >= 0) {
        const activeMark = marks[index]
        activeMark.classList.remove('bg-yellow-300', 'text-black')
        activeMark.classList.add('bg-orange-400', 'text-white')
        activeMark.scrollIntoView({ behavior: 'smooth', block: 'center' })
        setCurrentIndex(index)
      }
    },
    [containerId]
  )

  const performSearch = useCallback(() => {
    if (!markInstanceRef.current) {
      const container = document.getElementById(containerId)
      if (container) {
        markInstanceRef.current = new Mark(container)
      }
    }

    if (markInstanceRef.current) {
      markInstanceRef.current.unmark({
        done: () => {
          if (!queryRef.current) {
            setTotalMatches(0)
            setCurrentIndex(0)
            return
          }
          markInstanceRef.current?.mark(queryRef.current, {
            acrossElements: true,
            className: 'doc-search-match bg-yellow-300 text-black',
            done: (count) => {
              setTotalMatches(count)
              setCurrentIndex((prev) => {
                const nextIdx = prev >= count ? 0 : prev
                setTimeout(() => scrollToMatch(nextIdx), 50)
                return nextIdx
              })
            }
          })
        }
      })
    }
  }, [containerId, scrollToMatch])

  useEffect(() => {
    performSearch()
  }, [query, performSearch])

  useEffect(() => {
    const handler = () => {
      if (queryRef.current) performSearch()
    }
    window.addEventListener('pdf-page-rendered', handler)
    return () => window.removeEventListener('pdf-page-rendered', handler)
  }, [performSearch])

  const nextMatch = () => {
    if (totalMatches > 0) {
      scrollToMatch((currentIndex + 1) % totalMatches)
    }
  }

  const prevMatch = () => {
    if (totalMatches > 0) {
      scrollToMatch((currentIndex - 1 + totalMatches) % totalMatches)
    }
  }

  return { query, setQuery, totalMatches, currentIndex, nextMatch, prevMatch }
}

/* ── PDF Viewer ────────────────────────────────────────────────── */

function PdfPageRenderer({
  pdfDoc,
  pageNum,
  scale,
  documentTitle,
}: {
  pdfDoc: PDFDocumentProxy
  pageNum: number
  scale: number
  documentTitle: string
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    let cancelled = false
    if (!canvasRef.current) return

    pdfDoc.getPage(pageNum).then((page) => {
      if (cancelled || !canvasRef.current) return
      const viewport = page.getViewport({ scale })
      const canvas = canvasRef.current
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      canvas.width = viewport.width
      canvas.height = viewport.height
      page.render({ canvasContext: ctx, viewport, canvas })
    })

    return () => {
      cancelled = true
    }
  }, [pdfDoc, pageNum, scale])

  return (
    <div id={`pdf-page-${pageNum}`} data-page={pageNum} className="pdf-page-container flex flex-col items-center w-full">
      {/* Page break marker if it's not the first page */}
      {pageNum > 1 && (
        <div className="mb-6 mt-4 flex w-full flex-col items-center gap-4">
          <div className="rounded-full bg-slate-200/50 px-3 py-1 text-[10px] font-medium text-slate-500">
            Page Break • End of Page {pageNum - 1}
          </div>
          <div className="w-full px-2 text-left text-[10px] font-semibold uppercase tracking-wider text-slate-400">
            {documentTitle} • PAGE {pageNum}
          </div>
        </div>
      )}
      <canvas ref={canvasRef} className="bg-white shadow-lg" />
    </div>
  )
}

/* ── Search UI ─────────────────────────────────────────────────── */

function ToolbarSearch({ search }: { search: DocumentSearch }) {
  const { query, setQuery, totalMatches, currentIndex, nextMatch, prevMatch } = search

  return (
    <div className="flex items-center gap-2">
      <div className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2 py-1 focus-within:border-blue-500 focus-within:ring-1 focus-within:ring-blue-500">
        <Search className="h-3.5 w-3.5 text-slate-400" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              nextMatch()
            }
          }}
          placeholder="Find in document..."
          className="w-36 bg-transparent text-xs text-slate-700 outline-none placeholder:text-slate-400"
        />
        {query && totalMatches > 0 && (
          <span className="text-[10px] text-slate-400 whitespace-nowrap px-1">
            {currentIndex + 1} of {totalMatches}
          </span>
        )}
        {query && totalMatches === 0 && (
          <span className="text-[10px] text-slate-400 whitespace-nowrap px-1">0 of 0</span>
        )}
      </div>

      <div className="flex items-center rounded-lg border border-slate-200 bg-white">
        <button
          type="button"
          onClick={prevMatch}
          disabled={!query || totalMatches === 0}
          className="p-1 text-slate-400 hover:bg-slate-100 disabled:opacity-50"
        >
          <ChevronUp className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={nextMatch}
          disabled={!query || totalMatches === 0}
          className="border-l border-slate-200 p-1 text-slate-400 hover:bg-slate-100 disabled:opacity-50"
        >
          <ChevronDown className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}

function PdfViewer({
  blob,
  documentTitle,
  onFullscreen,
}: {
  blob: Blob
  documentTitle: string
  onFullscreen: () => void
}) {
  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null)
  const [numPages, setNumPages] = useState(0)
  const [scale, setScale] = useState(1.0)
  const [currentPage, setCurrentPage] = useState(1)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let cancelled = false
    blob.arrayBuffer().then((buf) => {
      pdfjsLib.getDocument({ data: buf }).promise.then((doc) => {
        if (cancelled) return
        setPdfDoc(doc)
        setNumPages(doc.numPages)
        setCurrentPage(1)
      })
    })
    return () => {
      cancelled = true
    }
  }, [blob])

  // Track visible page
  useEffect(() => {
    const container = containerRef.current
    if (!container || numPages === 0) return

    const observer = new IntersectionObserver(
      (entries) => {
        let maxRatio = 0
        let bestPage = currentPage
        entries.forEach((entry) => {
          if (entry.isIntersecting && entry.intersectionRatio > maxRatio) {
            maxRatio = entry.intersectionRatio
            const pageId = entry.target.getAttribute('data-page')
            if (pageId) bestPage = parseInt(pageId, 10)
          }
        })
        if (maxRatio > 0 && bestPage !== currentPage) {
          setCurrentPage(bestPage)
        }
      },
      { root: container, threshold: [0.1, 0.5, 0.9] }
    )

    const elements = container.querySelectorAll('.pdf-page-container')
    elements.forEach((el) => observer.observe(el))

    return () => observer.disconnect()
  }, [numPages, currentPage])

  const scrollToPage = (p: number) => {
    if (p < 1 || p > numPages) return
    setCurrentPage(p)
    const el = document.getElementById(`pdf-page-${p}`)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* PDF toolbar */}
      <div className="flex items-center gap-3 border-b border-slate-200 bg-slate-50 px-4 py-2 text-sm text-slate-600">
        <button
          type="button"
          disabled={currentPage <= 1}
          onClick={() => scrollToPage(currentPage - 1)}
          aria-label="Previous page"
          className="rounded p-1 hover:bg-slate-200 disabled:opacity-30"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        <span className="font-medium">
          Page {currentPage} of {numPages || '—'}
        </span>
        <button
          type="button"
          disabled={currentPage >= numPages}
          onClick={() => scrollToPage(currentPage + 1)}
          aria-label="Next page"
          className="rounded p-1 hover:bg-slate-200 disabled:opacity-30"
        >
          <ChevronRight className="h-4 w-4" />
        </button>

        <span className="mx-1 h-4 w-px bg-slate-300" />

        <button
          type="button"
          onClick={() => setScale((s) => Math.max(0.5, s - 0.1))}
          aria-label="Zoom out"
          className="rounded p-1 hover:bg-slate-200"
        >
          <Minus className="h-4 w-4" />
        </button>
        <span className="w-12 text-center font-medium">{Math.round(scale * 100)}%</span>
        <button
          type="button"
          onClick={() => setScale((s) => Math.min(2.5, s + 0.1))}
          aria-label="Zoom in"
          className="rounded p-1 hover:bg-slate-200"
        >
          <PlusIcon className="h-4 w-4" />
        </button>

        <div className="flex-1" />

        <button
          type="button"
          onClick={onFullscreen}
          aria-label="Fullscreen"
          className="rounded p-1 text-slate-400 hover:bg-slate-200 hover:text-slate-600"
        >
          <Maximize2 className="h-4 w-4" />
        </button>
      </div>
      {/* Scrollable pages */}
      <div id="document-content-area" ref={containerRef} className="flex-1 overflow-auto bg-slate-100 p-6">
        <div className="mx-auto flex max-w-4xl flex-col items-center gap-6 pb-20">
          {pdfDoc && Array.from({ length: numPages }, (_, i) => i + 1).map((pageNum) => (
            <PdfPageRenderer
              key={pageNum}
              pdfDoc={pdfDoc}
              pageNum={pageNum}
              scale={scale}
              documentTitle={documentTitle}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

/* ── Text / HTML / CSV Toolbar ─────────────────────────────────── */

function PreviewToolbar({
  format,
  rowCount,
  canEdit,
  onEdit,
  onFullscreen,
  search,
}: {
  format: SourceFormat
  rowCount?: number
  canEdit: boolean
  onEdit: () => void
  onFullscreen: () => void
  search: DocumentSearch
}) {
  return (
    <div className="flex items-center gap-3 border-b border-slate-200 bg-slate-50 px-4 py-2 text-sm text-slate-600">
      {format === 'csv' && rowCount !== undefined && (
        <span className="font-medium text-slate-500">{rowCount} rows</span>
      )}
      {format === 'markdown' && (
        <span className="font-medium text-slate-500">Rendered preview</span>
      )}
      {format === 'docx' && (
        <span className="font-medium text-slate-500">Rendered preview</span>
      )}
      {format === 'text' && (
        <span className="font-medium text-slate-500">Plain text</span>
      )}

      <div className="flex-1" />

      <ToolbarSearch search={search} />

      <span className="mx-1 h-4 w-px bg-slate-300" />

      {canEdit && (
        <button
          type="button"
          onClick={onEdit}
          className="flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-200"
        >
          <Edit3 className="h-3.5 w-3.5" />
          Edit
        </button>
      )}
      <button
        type="button"
        onClick={onFullscreen}
        aria-label="Fullscreen"
        className="rounded p-1 text-slate-400 hover:bg-slate-200 hover:text-slate-600"
      >
        <Maximize2 className="h-4 w-4" />
      </button>
    </div>
  )
}

/* ── Chat Panel (Recent Questions Asked) ───────────────────────── */

interface ChatTurn {
  question: string
  answer: string
  sources: SourceOut[]
}

function ChatPanel({ documentId, token }: { documentId: string; token: string }) {
  const [recentQuestions, setRecentQuestions] = useState<QueryLogSummary[]>([])
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [question, setQuestion] = useState('')
  const [asking, setAsking] = useState(false)
  const [chatError, setChatError] = useState<string | null>(null)
  const chatInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    getDocumentQuestions(token, documentId)
      .then(setRecentQuestions)
      .catch(() => {})
  }, [token, documentId])

  async function ask(q: string) {
    const trimmed = q.trim()
    if (!trimmed || asking) return
    setAsking(true)
    setChatError(null)
    setQuestion('')
    try {
      const res = await askQuery(token, { question: trimmed, document_id: documentId })
      setTurns((t) => [...t, { question: trimmed, answer: res.answer, sources: res.sources }])
      getDocumentQuestions(token, documentId)
        .then(setRecentQuestions)
        .catch(() => {})
    } catch (err) {
      setChatError(err instanceof Error ? err.message : 'Failed to get an answer.')
    } finally {
      setAsking(false)
    }
  }


  return (
    <div className="flex flex-col rounded-2xl border border-slate-200 bg-white shadow-sm">
      {/* Header */}
      <div className="border-b border-slate-100 px-4 pt-4 pb-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
          <MessageSquare className="h-4 w-4 text-blue-600" />
          Recent Questions Asked
        </h2>
        <p className="mt-1 text-xs text-slate-400">
          Jump straight into a Q&A thread referencing this document:
        </p>
      </div>

      {/* Recent questions list */}
      {recentQuestions.length > 0 && (
        <div className="space-y-1 px-3 py-3">
          {recentQuestions.slice(0, 5).map((q) => (
            <button
              key={q.id}
              type="button"
              onClick={() => ask(q.question)}
              className="group flex w-full items-start gap-3 rounded-xl px-3 py-2.5 text-left transition hover:bg-slate-50"
            >
              <div className="min-w-0 flex-1">
                <p className="text-xs font-medium leading-snug text-slate-700">
                  "{q.question}"
                </p>
                <div className="mt-1 flex items-center gap-2">
                  <span className="flex items-center gap-0.5 text-[10px] font-medium text-orange-500">
                    <Flame className="h-3 w-3" />
                    {q.faithfulness_score !== null ? `${Math.round(q.faithfulness_score * 100)}% match` : 'Asked'}
                  </span>
                  <span className="text-[10px] text-slate-400">
                    Asked {relativeDate(q.created_at)}
                  </span>
                </div>
              </div>
              <ArrowRight className="mt-1 h-3.5 w-3.5 shrink-0 text-slate-300 transition group-hover:text-slate-500" />
            </button>
          ))}
        </div>
      )}

      {/* Conversation turns */}
      {turns.length > 0 && (
        <div className="max-h-80 space-y-4 overflow-y-auto border-t border-slate-100 px-4 py-3">
          {turns.map((t, i) => (
            <div key={i}>
              <p className="text-xs font-semibold text-slate-700">{t.question}</p>
              <p className="mt-1.5 text-xs leading-relaxed text-slate-600">{t.answer}</p>
              {t.sources.length > 0 && (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {t.sources.map((s) => (
                    <span
                      key={s.index}
                      className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500"
                      title={s.text}
                    >
                      [{s.index}] {s.locator}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {chatError && <p className="px-4 text-xs text-red-600">{chatError}</p>}

      {/* Input */}
      <div className="border-t border-slate-100 px-3 py-3">
        <form
          onSubmit={(e) => {
            e.preventDefault()
            ask(question)
          }}
          className="flex items-center gap-2"
        >
          <input
            id="chat-input"
            ref={chatInputRef}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask a new question about this file…"
            className="w-full rounded-lg bg-slate-100 px-3 py-2.5 text-xs text-slate-700 outline-none ring-blue-500 focus:ring-2"
          />
          <button
            type="submit"
            disabled={asking || !question.trim()}
            aria-label="Ask"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-blue-600 text-white transition hover:bg-blue-700 disabled:opacity-50"
          >
            {asking ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </button>
        </form>
      </div>
    </div>
  )
}

/* ── Overflow Menu ──────────────────────────────────────────────── */

function OverflowMenu({
  canEdit,
  deleting,
  onRename,
  onEditContent,
  onDelete,
}: {
  canEdit: boolean
  deleting: boolean
  onRename: () => void
  onEditContent: () => void
  onDelete: () => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [open])

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label="More actions"
        className="rounded-lg p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
      >
        <MoreVertical className="h-4 w-4" />
      </button>
      {open && (
        <div className="absolute right-0 top-full z-20 mt-1 w-40 overflow-hidden rounded-xl border border-slate-200 bg-white py-1 text-sm shadow-lg">
          <button
            type="button"
            onClick={() => {
              setOpen(false)
              onRename()
            }}
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-slate-700 hover:bg-slate-50"
          >
            <Pencil className="h-3.5 w-3.5" />
            Rename
          </button>
          {canEdit && (
            <button
              type="button"
              onClick={() => {
                setOpen(false)
                onEditContent()
              }}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-slate-700 hover:bg-slate-50"
            >
              <Edit3 className="h-3.5 w-3.5" />
              Edit content
            </button>
          )}
          <button
            type="button"
            disabled={deleting}
            onClick={() => {
              setOpen(false)
              onDelete()
            }}
            className="flex w-full items-center gap-2 border-t border-slate-100 px-3 py-2 text-left text-red-600 hover:bg-red-50 disabled:opacity-50"
          >
            <Trash2 className="h-3.5 w-3.5" />
            Delete
          </button>
        </div>
      )}
    </div>
  )
}

/* ── Main Page ─────────────────────────────────────────────────── */

export default function DocumentViewerPage() {
  const { token, user } = useOutletContext<AuthOutletContext>()
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const autoEdit = (location.state as { autoEdit?: boolean } | null)?.autoEdit ?? false
  const autoEditTriggered = useRef(false)

  const search = useDocumentSearch('document-content-area')

  const [doc, setDoc] = useState<DocumentOut | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [rawText, setRawText] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const [editingTitle, setEditingTitle] = useState(false)
  const [titleDraft, setTitleDraft] = useState('')
  const [savingTitle, setSavingTitle] = useState(false)

  const [editingContent, setEditingContent] = useState(false)
  const [contentDraft, setContentDraft] = useState('')
  const [savingContent, setSavingContent] = useState(false)

  const [deleting, setDeleting] = useState(false)

  /* ── Data loading ───────────────────────────────────────────── */

  useEffect(() => {
    if (!id) return
    let cancelled = false

    setLoading(true)
    setError(null)
    setPreview(null)
    setRawText(null)

    Promise.all([getDocument(token, id), getDocumentFile(token, id)])
      .then(async ([meta, file]) => {
        if (cancelled) return
        setDoc({ ...meta, size_bytes: meta.size_bytes ?? file.blob.size })

        if (meta.source_format === 'pdf') {
          setPreview({ kind: 'pdf', blob: file.blob })
        } else if (meta.source_format === 'docx') {
          const arrayBuffer = await file.blob.arrayBuffer()
          const { value: html } = await mammoth.convertToHtml({ arrayBuffer })
          setPreview({ kind: 'html', html: DOMPurify.sanitize(html) })
        } else {
          const text = await file.blob.text()
          if (cancelled) return
          setRawText(text)
          setPreview(buildPreview(meta.source_format, text))
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load this document.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [id, token])

  /* ── Actions ────────────────────────────────────────────────── */

  async function handleDownload() {
    if (!id || !doc) return
    const { blob } = await getDocumentFile(token, id)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = doc.filename
    a.click()
    URL.revokeObjectURL(url)
  }

  function startEditingTitle() {
    if (!doc) return
    setTitleDraft(doc.title)
    setEditingTitle(true)
  }

  async function saveTitle() {
    if (!id) return
    const stripped = titleDraft.trim()
    if (!stripped) return
    setSavingTitle(true)
    try {
      const updated = await updateDocument(token, id, { title: stripped })
      setDoc(updated)
      setEditingTitle(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to rename this document.')
    } finally {
      setSavingTitle(false)
    }
  }

  async function handleDelete() {
    if (!id || !doc) return
    if (!window.confirm(`Delete "${doc.title}"? This can't be undone.`)) return
    setDeleting(true)
    try {
      await deleteDocument(token, id)
      navigate('/documents')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete this document.')
      setDeleting(false)
    }
  }

  function startEditingContent() {
    if (rawText === null) return
    setContentDraft(rawText)
    setEditingContent(true)
  }

  async function saveContent() {
    if (!id || !doc) return
    setSavingContent(true)
    try {
      const updated = await updateDocumentContent(token, id, contentDraft)
      setDoc(updated)
      setRawText(contentDraft)
      setPreview(buildPreview(doc.source_format, contentDraft))
      setEditingContent(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save changes.')
    } finally {
      setSavingContent(false)
    }
  }

  const canEditContent = doc && EDITABLE_FORMATS.includes(doc.source_format) && rawText !== null

  useEffect(() => {
    if (autoEdit && canEditContent && !autoEditTriggered.current) {
      autoEditTriggered.current = true
      startEditingContent()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoEdit, canEditContent])

  /* ── Render ─────────────────────────────────────────────────── */

  const fmtMeta = doc ? FORMAT_META[doc.source_format] : null
  const statusMeta = doc ? STATUS_LABELS[doc.status] : null
  const FmtIcon = fmtMeta?.icon ?? FileText

  const toggleFullscreen = () => {
    const el = document.getElementById('preview-container')
    if (!document.fullscreenElement) {
      el?.requestFullscreen().catch(() => {})
    } else {
      document.exitFullscreen().catch(() => {})
    }
  }

  return (
    <div className="flex h-screen bg-slate-50">
      <Sidebar userEmail={user.email} token={token} />

      <div className="flex flex-1 flex-col overflow-hidden">
        {/* ── Header ──────────────────────────────────────────── */}
        <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3">
          <div className="flex max-w-md flex-1 items-center gap-2 rounded-lg bg-slate-100 px-3 py-2">
            <Search className="h-4 w-4 text-slate-400" />
            <input
              disabled
              placeholder="Search policies, files, agreements…"
              className="w-full bg-transparent text-sm text-slate-500 placeholder:text-slate-400 outline-none"
            />
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleDownload}
              disabled={!doc}
              className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-50"
            >
              <Download className="h-4 w-4" />
              Download
            </button>
            <button
              type="button"
              onClick={() => {
                const el = document.getElementById('chat-input')
                el?.focus()
                el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
              }}
              disabled={!doc}
              className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:opacity-50"
            >
              <Sparkles className="h-4 w-4" />
              Ask about this document
            </button>
            {doc && (
              <OverflowMenu
                canEdit={!!canEditContent}
                deleting={deleting}
                onRename={startEditingTitle}
                onEditContent={startEditingContent}
                onDelete={handleDelete}
              />
            )}
          </div>
        </header>

        {/* ── Content area ────────────────────────────────────── */}
        <div className="flex flex-1 flex-col overflow-hidden">
          <div className="shrink-0 px-6 pt-4">
            {/* Back link */}
            <button
              type="button"
              onClick={() => navigate('/documents')}
              className="flex items-center gap-1.5 text-sm text-slate-500 transition hover:text-slate-700"
            >
              <ArrowLeft className="h-4 w-4" />
              Back to Documents
            </button>

            {/* Error */}
            {error && (
              <div className="mt-4 flex items-center gap-2 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
                <AlertCircle className="h-4 w-4 shrink-0" />
                {error}
              </div>
            )}

            {/* Loading */}
            {loading && !doc && !error && (
              <div className="mt-8 flex items-center justify-center gap-2 text-sm text-slate-400">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading document…
              </div>
            )}

            {/* Document header */}
            {doc && !error && (
              <>
                {/* Title */}
                <div className="mt-3">
                  {editingTitle ? (
                    <div className="flex items-center gap-2">
                      <input
                        autoFocus
                        value={titleDraft}
                        onChange={(e) => setTitleDraft(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') saveTitle()
                          if (e.key === 'Escape') setEditingTitle(false)
                        }}
                        className="w-full max-w-lg rounded-lg border border-slate-200 px-3 py-1.5 text-xl font-bold text-slate-900 outline-none ring-blue-500 focus:ring-2"
                      />
                      <button
                        type="button"
                        onClick={saveTitle}
                        disabled={savingTitle}
                        aria-label="Save title"
                        className="rounded-lg p-1.5 text-emerald-600 hover:bg-emerald-50 disabled:opacity-50"
                      >
                        <Check className="h-4 w-4" />
                      </button>
                      <button
                        type="button"
                        onClick={() => setEditingTitle(false)}
                        aria-label="Cancel"
                        className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </div>
                  ) : (
                    <div className="group flex items-center gap-2">
                      <h1 className="text-xl font-bold text-slate-900">{doc.title}</h1>
                      <button
                        type="button"
                        onClick={startEditingTitle}
                        aria-label="Rename"
                        className="rounded-lg p-1.5 text-slate-300 opacity-0 transition group-hover:opacity-100 hover:bg-slate-100 hover:text-slate-600"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  )}

                  {/* Metadata badges */}
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    {/* Category badge */}
                    {doc.category && (
                      <span
                        className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${CATEGORY_STYLES[doc.category] ?? DEFAULT_CATEGORY_STYLE}`}
                      >
                        {doc.category}
                      </span>
                    )}

                    {/* Format badge */}
                    <span className={`flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold ${fmtMeta?.badgeClass}`}>
                      <FmtIcon className={`h-3 w-3 ${fmtMeta?.iconClass}`} />
                      {fmtMeta?.label}
                    </span>

                    {/* File size */}
                    <span className="text-xs text-slate-500">{formatFileSize(doc.size_bytes)}</span>

                    {/* Separator dot */}
                    <span className="text-slate-300">·</span>

                    {/* Status badge */}
                    {statusMeta && (
                      <span className={`flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${statusMeta.className}`}>
                        {doc.status === 'ready' && <CheckCircle2 className="h-3 w-3" />}
                        {statusMeta.label}
                      </span>
                    )}

                    <span className="text-slate-300">·</span>

                    {/* Updated date */}
                    <span className="text-xs text-slate-500">Updated {formatDate(doc.updated_at)}</span>

                    {/* Private badge */}
                    {!doc.is_public && (
                      <>
                        <span className="text-slate-300">·</span>
                        <span className="flex items-center gap-1 text-xs text-slate-400">
                          <Lock className="h-3 w-3" />
                          Private
                        </span>
                      </>
                    )}
                  </div>
                </div>
              </>
            )}
          </div>

          {/* ── Two-column layout ──────────────────────────────── */}
          {doc && !error && (
            <div className="mt-4 flex flex-1 min-h-0 gap-5 px-6 pb-6">
              {/* Left: Document preview */}
              <div id="preview-container" className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
                {editingContent ? (
                  <div className="flex flex-1 flex-col">
                    <textarea
                      value={contentDraft}
                      onChange={(e) => setContentDraft(e.target.value)}
                      className="flex-1 resize-none border-0 px-6 py-6 font-mono text-sm text-slate-800 outline-none"
                    />
                    <div className="flex items-center justify-end gap-2 border-t border-slate-100 px-6 py-3">
                      <button
                        type="button"
                        onClick={() => setEditingContent(false)}
                        disabled={savingContent}
                        className="rounded-lg px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 disabled:opacity-50"
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        onClick={saveContent}
                        disabled={savingContent}
                        className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
                      >
                        {savingContent ? 'Saving…' : 'Save'}
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    {preview?.kind === 'pdf' && <PdfViewer blob={preview.blob} documentTitle={doc.title} onFullscreen={toggleFullscreen} />}

                    {preview?.kind !== 'pdf' && doc && (
                      <PreviewToolbar
                        format={doc.source_format}
                        rowCount={preview?.kind === 'csv' ? preview.rows.length - 1 : undefined}
                        canEdit={!!canEditContent && !editingContent}
                        onEdit={startEditingContent}
                        onFullscreen={toggleFullscreen}
                        search={search}
                      />
                    )}

                    {preview?.kind === 'text' && (
                      <pre id="document-content-area" className="flex-1 overflow-auto whitespace-pre-wrap px-6 py-6 text-sm leading-relaxed text-slate-700">
                        {preview.text}
                      </pre>
                    )}

                    {preview?.kind === 'csv' && (
                      <div id="document-content-area" className="flex-1 overflow-auto">
                        <table className="w-full border-collapse text-sm">
                          <thead className="sticky top-0 bg-slate-50">
                            <tr>
                              {preview.rows[0]?.map((header, i) => (
                                <th
                                  key={i}
                                  className="border border-slate-200 px-3 py-2 text-left font-semibold text-slate-700"
                                >
                                  {header}
                                </th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {preview.rows.slice(1).map((row, i) => (
                              <tr key={i} className="odd:bg-white even:bg-slate-50/50">
                                {row.map((cell, j) => (
                                  <td key={j} className="border border-slate-200 px-3 py-2 text-slate-600">
                                    {cell}
                                  </td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}

                    {preview?.kind === 'html' && (
                      <div
                        id="document-content-area"
                        className="prose prose-slate max-w-none flex-1 overflow-auto px-8 py-6"
                        dangerouslySetInnerHTML={{ __html: preview.html }}
                      />
                    )}

                    {!preview && !loading && (
                      <div className="flex flex-1 items-center justify-center py-20 text-sm text-slate-400">
                        No preview available.
                      </div>
                    )}
                  </>
                )}
              </div>

              {/* Right: Q&A sidebar */}
              <div className="sticky top-6 w-[340px] shrink-0 self-start">
                <ChatPanel documentId={doc.id} token={token} />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
