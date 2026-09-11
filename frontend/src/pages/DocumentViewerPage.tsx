import DOMPurify from 'dompurify'
import { AlertCircle, ArrowLeft, Download, Lock } from 'lucide-react'
import mammoth from 'mammoth'
import MarkdownIt from 'markdown-it'
import { useEffect, useState } from 'react'
import { useNavigate, useOutletContext, useParams } from 'react-router-dom'

import type { AuthOutletContext } from '../components/RequireAuth'
import { parseCsv } from '../lib/csv'
import { getDocument, getDocumentFile, type DocumentOut } from '../lib/documents'

const md = new MarkdownIt()

type Preview =
  | { kind: 'pdf'; url: string }
  | { kind: 'text'; text: string }
  | { kind: 'csv'; rows: string[][] }
  | { kind: 'html'; html: string }

export default function DocumentViewerPage() {
  const { token } = useOutletContext<AuthOutletContext>()
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [doc, setDoc] = useState<DocumentOut | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!id) return
    let cancelled = false
    let objectUrl: string | null = null

    setLoading(true)
    setError(null)
    setPreview(null)

    Promise.all([getDocument(token, id), getDocumentFile(token, id)])
      .then(async ([meta, file]) => {
        if (cancelled) return
        setDoc(meta)

        switch (meta.source_format) {
          case 'pdf': {
            objectUrl = URL.createObjectURL(file.blob)
            setPreview({ kind: 'pdf', url: objectUrl })
            break
          }
          case 'csv': {
            const text = await file.blob.text()
            setPreview({ kind: 'csv', rows: parseCsv(text) })
            break
          }
          case 'text': {
            const text = await file.blob.text()
            setPreview({ kind: 'text', text })
            break
          }
          case 'markdown': {
            const text = await file.blob.text()
            setPreview({ kind: 'html', html: DOMPurify.sanitize(md.render(text)) })
            break
          }
          case 'docx': {
            const arrayBuffer = await file.blob.arrayBuffer()
            const { value: html } = await mammoth.convertToHtml({ arrayBuffer })
            setPreview({ kind: 'html', html: DOMPurify.sanitize(html) })
            break
          }
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
              <div className="min-w-0">
                <h1 className="truncate text-2xl font-bold text-slate-900">{doc.title}</h1>
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
              <button
                type="button"
                onClick={handleDownload}
                className="flex shrink-0 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                <Download className="h-4 w-4" />
                Download
              </button>
            </div>

            <div className="mt-6 overflow-hidden rounded-2xl bg-white shadow-sm">
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
