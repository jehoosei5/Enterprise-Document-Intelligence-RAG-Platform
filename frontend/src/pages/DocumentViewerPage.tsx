import DOMPurify from 'dompurify'
import {
  AlertCircle,
  ArrowLeft,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Download,
  Loader2,
  Lock,
  MessageSquare,
  Minus,
  Pencil,
  Plus as PlusIcon,
  Send,
  Trash2,
  X,
} from 'lucide-react'
import mammoth from 'mammoth'
import MarkdownIt from 'markdown-it'
import * as pdfjsLib from 'pdfjs-dist'
import type { PDFDocumentProxy } from 'pdfjs-dist'
import pdfjsWorkerSrc from 'pdfjs-dist/build/pdf.worker.mjs?url'
import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useOutletContext, useParams } from 'react-router-dom'

import type { AuthOutletContext } from '../components/RequireAuth'
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
import { askAboutDocument, getDocumentQuestions, type QueryLogSummary, type SourceOut } from '../lib/query'

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorkerSrc

const md = new MarkdownIt()

function relativeDate(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const days = Math.floor(diffMs / 86_400_000)
  if (days <= 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days < 30) return `${days}d ago`
  return new Date(iso).toLocaleDateString()
}

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

function PdfViewer({ blob }: { blob: Blob }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null)
  const [pageNum, setPageNum] = useState(1)
  const [numPages, setNumPages] = useState(0)
  const [scale, setScale] = useState(1.0)

  useEffect(() => {
    let cancelled = false
    blob.arrayBuffer().then((buf) => {
      pdfjsLib.getDocument({ data: buf }).promise.then((doc) => {
        if (cancelled) return
        setPdfDoc(doc)
        setNumPages(doc.numPages)
        setPageNum(1)
      })
    })
    return () => {
      cancelled = true
    }
  }, [blob])

  useEffect(() => {
    if (!pdfDoc || !canvasRef.current) return
    let cancelled = false
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
    <div className="flex flex-col">
      <div className="flex items-center justify-center gap-3 border-b border-slate-100 px-4 py-2 text-sm text-slate-600">
        <button
          type="button"
          disabled={pageNum <= 1}
          onClick={() => setPageNum((p) => p - 1)}
          aria-label="Previous page"
          className="rounded p-1 hover:bg-slate-100 disabled:opacity-30"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        <span>
          Page {pageNum} of {numPages || '—'}
        </span>
        <button
          type="button"
          disabled={pageNum >= numPages}
          onClick={() => setPageNum((p) => p + 1)}
          aria-label="Next page"
          className="rounded p-1 hover:bg-slate-100 disabled:opacity-30"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
        <span className="mx-2 h-4 w-px bg-slate-200" />
        <button
          type="button"
          onClick={() => setScale((s) => Math.max(0.5, s - 0.1))}
          aria-label="Zoom out"
          className="rounded p-1 hover:bg-slate-100"
        >
          <Minus className="h-4 w-4" />
        </button>
        <span className="w-10 text-center">{Math.round(scale * 100)}%</span>
        <button
          type="button"
          onClick={() => setScale((s) => Math.min(2.5, s + 0.1))}
          aria-label="Zoom in"
          className="rounded p-1 hover:bg-slate-100"
        >
          <PlusIcon className="h-4 w-4" />
        </button>
      </div>
      <div className="flex max-h-[75vh] justify-center overflow-auto bg-slate-100 p-4">
        <canvas ref={canvasRef} className="shadow" />
      </div>
    </div>
  )
}

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
      const res = await askAboutDocument(token, documentId, trimmed)
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
    <div className="rounded-2xl bg-white p-4 shadow-sm">
      <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
        <MessageSquare className="h-4 w-4 text-blue-600" />
        Ask about this document
      </h2>

      {recentQuestions.length > 0 && (
        <div className="mt-3 space-y-2">
          <p className="text-xs font-medium text-slate-400">Recent Questions Asked</p>
          {recentQuestions.map((q) => (
            <button
              key={q.id}
              type="button"
              onClick={() => ask(q.question)}
              className="block w-full rounded-lg border border-slate-100 px-3 py-2 text-left text-xs text-slate-600 hover:bg-slate-50"
            >
              "{q.question}"
              <span className="mt-0.5 block text-[10px] text-slate-400">Asked {relativeDate(q.created_at)}</span>
            </button>
          ))}
        </div>
      )}

      {turns.length > 0 && (
        <div className="mt-3 max-h-80 space-y-4 overflow-y-auto border-t border-slate-100 pt-3">
          {turns.map((t, i) => (
            <div key={i}>
              <p className="text-xs font-semibold text-slate-700">{t.question}</p>
              <p className="mt-1 text-xs leading-relaxed text-slate-600">{t.answer}</p>
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

      {chatError && <p className="mt-2 text-xs text-red-600">{chatError}</p>}

      <form
        onSubmit={(e) => {
          e.preventDefault()
          ask(question)
        }}
        className="mt-3 flex items-center gap-2"
      >
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a new question about this file…"
          className="w-full rounded-lg bg-slate-100 px-3 py-2 text-xs text-slate-700 outline-none ring-blue-500 focus:ring-2"
        />
        <button
          type="submit"
          disabled={asking || !question.trim()}
          aria-label="Ask"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-blue-700 text-white hover:bg-blue-800 disabled:opacity-50"
        >
          {asking ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        </button>
      </form>
    </div>
  )
}

function DetailsPanel({
  doc,
  token,
  onUpdate,
}: {
  doc: DocumentOut
  token: string
  onUpdate: (d: DocumentOut) => void
}) {
  const [editingAccess, setEditingAccess] = useState(false)
  const [savingAccess, setSavingAccess] = useState(false)
  const [accessError, setAccessError] = useState<string | null>(null)

  async function setAccess(isPublic: boolean) {
    setSavingAccess(true)
    setAccessError(null)
    try {
      const updated = await updateDocument(token, doc.id, { is_public: isPublic })
      onUpdate(updated)
      setEditingAccess(false)
    } catch (err) {
      setAccessError(err instanceof Error ? err.message : 'Failed to update access.')
    } finally {
      setSavingAccess(false)
    }
  }

  return (
    <div className="rounded-2xl bg-white p-4 shadow-sm">
      <h2 className="text-sm font-semibold text-slate-900">Details & Permissions</h2>
      <dl className="mt-3 space-y-3 text-xs">
        <div className="flex items-center justify-between gap-2">
          <dt className="shrink-0 text-slate-400">Access level</dt>
          <dd>
            {editingAccess ? (
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  disabled={savingAccess}
                  onClick={() => setAccess(false)}
                  className={`rounded-full px-2 py-1 text-xs font-medium ${!doc.is_public ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-600'}`}
                >
                  Just me
                </button>
                <button
                  type="button"
                  disabled={savingAccess}
                  onClick={() => setAccess(true)}
                  className={`rounded-full px-2 py-1 text-xs font-medium ${doc.is_public ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-600'}`}
                >
                  Everyone
                </button>
              </div>
            ) : (
              <span className="flex items-center gap-1.5">
                <span className="font-medium text-slate-700">{doc.is_public ? 'Everyone' : 'Just me'}</span>
                <button
                  type="button"
                  onClick={() => setEditingAccess(true)}
                  className="text-blue-600 hover:underline"
                >
                  Edit
                </button>
              </span>
            )}
          </dd>
        </div>
        {accessError && <p className="text-red-600">{accessError}</p>}
        <div className="flex items-center justify-between gap-2">
          <dt className="shrink-0 text-slate-400">Category</dt>
          <dd className="truncate font-medium text-slate-700">{doc.category ?? '—'}</dd>
        </div>
        <div className="flex items-center justify-between gap-2">
          <dt className="shrink-0 text-slate-400">Original file name</dt>
          <dd className="truncate font-medium text-slate-700" title={doc.filename}>
            {doc.filename}
          </dd>
        </div>
        <div className="flex items-center justify-between gap-2">
          <dt className="shrink-0 text-slate-400">Date added</dt>
          <dd className="font-medium text-slate-700">{new Date(doc.created_at).toLocaleDateString()}</dd>
        </div>
        <div className="flex items-center justify-between gap-2">
          <dt className="shrink-0 text-slate-400">Vector indexing</dt>
          <dd className="flex items-center gap-1 font-medium text-emerald-600">
            {doc.status === 'ready' && <CheckCircle2 className="h-3.5 w-3.5" />}
            {doc.chunk_count ?? 0} chunks indexed
          </dd>
        </div>
      </dl>
    </div>
  )
}

export default function DocumentViewerPage() {
  const { token } = useOutletContext<AuthOutletContext>()
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const autoEdit = (location.state as { autoEdit?: boolean } | null)?.autoEdit ?? false
  const autoEditTriggered = useRef(false)

  const [doc, setDoc] = useState<DocumentOut | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [rawText, setRawText] = useState<string | null>(null) // editable source, text-backed formats only
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const [editingTitle, setEditingTitle] = useState(false)
  const [titleDraft, setTitleDraft] = useState('')
  const [savingTitle, setSavingTitle] = useState(false)

  const [editingContent, setEditingContent] = useState(false)
  const [contentDraft, setContentDraft] = useState('')
  const [savingContent, setSavingContent] = useState(false)

  const [deleting, setDeleting] = useState(false)

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
        setDoc(meta)

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

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="mx-auto max-w-7xl px-6 py-8">
        <button
          type="button"
          onClick={() => navigate('/documents')}
          className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Documents
        </button>

        {error && (
          <div className="mt-6 flex items-center gap-2 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
            <AlertCircle className="h-4 w-4 shrink-0" />
            {error}
          </div>
        )}

        {doc && !error && (
          <>
            <div className="mt-3 flex items-start justify-between gap-4">
              <div className="min-w-0 flex-1">
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
                      className="w-full max-w-md rounded-lg border border-slate-200 px-3 py-1.5 text-2xl font-bold text-slate-900 outline-none ring-blue-500 focus:ring-2"
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
                    <h1 className="truncate text-2xl font-bold text-slate-900">{doc.title}</h1>
                    <button
                      type="button"
                      onClick={startEditingTitle}
                      aria-label="Rename"
                      className="rounded-lg p-1.5 text-slate-300 opacity-0 group-hover:opacity-100 hover:bg-slate-100 hover:text-slate-600"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </button>
                  </div>
                )}
                <div className="mt-1 flex items-center gap-2 text-sm text-slate-500">
                  {doc.category && (
                    <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-600">
                      {doc.category}
                    </span>
                  )}
                  {!doc.is_public && (
                    <span className="flex items-center gap-1 text-xs text-slate-400">
                      <Lock className="h-3 w-3" />
                      Just me
                    </span>
                  )}
                  <span className="text-xs text-slate-400">{formatFileSize(doc.size_bytes)}</span>
                  <span className="text-xs text-slate-400">Updated {relativeDate(doc.updated_at)}</span>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {canEditContent && !editingContent && (
                  <button
                    type="button"
                    onClick={startEditingContent}
                    className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                  >
                    <Pencil className="h-4 w-4" />
                    Edit
                  </button>
                )}
                <button
                  type="button"
                  onClick={handleDownload}
                  className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  <Download className="h-4 w-4" />
                  Download
                </button>
                <button
                  type="button"
                  onClick={handleDelete}
                  disabled={deleting}
                  className="flex items-center gap-2 rounded-lg border border-red-200 bg-white px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
                >
                  <Trash2 className="h-4 w-4" />
                  Delete
                </button>
              </div>
            </div>

            <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[1fr_340px]">
              <div className="overflow-hidden rounded-2xl bg-white shadow-sm">
                {editingContent ? (
                  <div className="flex flex-col">
                    <textarea
                      value={contentDraft}
                      onChange={(e) => setContentDraft(e.target.value)}
                      className="h-[70vh] w-full resize-none border-0 px-6 py-6 font-mono text-sm text-slate-800 outline-none"
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
                        className="rounded-lg bg-blue-700 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
                      >
                        {savingContent ? 'Saving…' : 'Save'}
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    {preview?.kind === 'pdf' && <PdfViewer blob={preview.blob} />}

                    {preview?.kind === 'text' && (
                      <pre className="max-h-[80vh] overflow-auto whitespace-pre-wrap px-6 py-6 text-sm text-slate-700">
                        {preview.text}
                      </pre>
                    )}

                    {preview?.kind === 'csv' && (
                      <div className="max-h-[80vh] overflow-auto">
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
                        className="doc-preview max-h-[80vh] overflow-auto px-8 py-6"
                        dangerouslySetInnerHTML={{ __html: preview.html }}
                      />
                    )}

                    {!preview && !loading && (
                      <div className="px-6 py-20 text-center text-sm text-slate-400">No preview.</div>
                    )}
                  </>
                )}
              </div>

              <div className="space-y-6">
                <ChatPanel documentId={doc.id} token={token} />
                <DetailsPanel doc={doc} token={token} onUpdate={setDoc} />
              </div>
            </div>
          </>
        )}

        {loading && !doc && !error && (
          <div className="mt-6 rounded-2xl bg-white px-6 py-20 text-center text-sm text-slate-400 shadow-sm">
            Loading…
          </div>
        )}
      </div>
    </div>
  )
}
