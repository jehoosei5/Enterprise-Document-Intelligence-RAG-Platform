import DOMPurify from 'dompurify'
import { AlertCircle, ArrowLeft, Check, Download, Lock, Pencil, Trash2, X } from 'lucide-react'
import mammoth from 'mammoth'
import MarkdownIt from 'markdown-it'
import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useOutletContext, useParams } from 'react-router-dom'

import type { AuthOutletContext } from '../components/RequireAuth'
import { parseCsv } from '../lib/csv'
import {
  deleteDocument,
  EDITABLE_FORMATS,
  getDocument,
  getDocumentFile,
  updateDocument,
  updateDocumentContent,
  type DocumentOut,
  type SourceFormat,
} from '../lib/documents'

const md = new MarkdownIt()

type Preview =
  | { kind: 'pdf'; url: string }
  | { kind: 'text'; text: string }
  | { kind: 'csv'; rows: string[][] }
  | { kind: 'html'; html: string }

function buildPreview(format: SourceFormat, text: string): Preview {
  if (format === 'csv') return { kind: 'csv', rows: parseCsv(text) }
  if (format === 'markdown') return { kind: 'html', html: DOMPurify.sanitize(md.render(text)) }
  return { kind: 'text', text }
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
    let objectUrl: string | null = null

    setLoading(true)
    setError(null)
    setPreview(null)
    setRawText(null)

    Promise.all([getDocument(token, id), getDocumentFile(token, id)])
      .then(async ([meta, file]) => {
        if (cancelled) return
        setDoc(meta)

        if (meta.source_format === 'pdf') {
          objectUrl = URL.createObjectURL(file.blob)
          setPreview({ kind: 'pdf', url: objectUrl })
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
      if (objectUrl) URL.revokeObjectURL(objectUrl)
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
      <div className="mx-auto max-w-5xl px-6 py-8">
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

            <div className="mt-6 overflow-hidden rounded-2xl bg-white shadow-sm">
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
                  {preview?.kind === 'pdf' && (
                    <iframe title={doc.title} src={preview.url} className="h-[80vh] w-full" />
                  )}

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
