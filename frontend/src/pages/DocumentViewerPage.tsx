import { AlertCircle, ArrowLeft, Download, Lock } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate, useOutletContext, useParams } from 'react-router-dom'

import type { AuthOutletContext } from '../components/RequireAuth'
import { getDocument, getDocumentFile, type DocumentOut } from '../lib/documents'

export default function DocumentViewerPage() {
  const { token } = useOutletContext<AuthOutletContext>()
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [doc, setDoc] = useState<DocumentOut | null>(null)
  const [objectUrl, setObjectUrl] = useState<string | null>(null)
  const [textContent, setTextContent] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!id) return
    let cancelled = false
    let url: string | null = null

    setLoading(true)
    setError(null)

    Promise.all([getDocument(token, id), getDocumentFile(token, id)])
      .then(([meta, file]) => {
        if (cancelled) return
        setDoc(meta)

        if (meta.source_format === 'docx') {
          // No inline preview — Download only.
          return
        }
        if (meta.source_format === 'pdf') {
          url = URL.createObjectURL(file.blob)
          setObjectUrl(url)
        } else {
          file.blob.text().then((text) => {
            if (!cancelled) setTextContent(text)
          })
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
      if (url) URL.revokeObjectURL(url)
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
              {doc.source_format === 'docx' && (
                <div className="flex flex-col items-center justify-center gap-2 px-6 py-20 text-center">
                  <p className="text-sm font-medium text-slate-700">
                    Preview isn't available for Word documents
                  </p>
                  <p className="text-xs text-slate-400">Use Download to open it in your own editor.</p>
                </div>
              )}

              {doc.source_format === 'pdf' &&
                (objectUrl ? (
                  <iframe title={doc.title} src={objectUrl} className="h-[80vh] w-full" />
                ) : (
                  !loading && <div className="px-6 py-20 text-center text-sm text-slate-400">No preview.</div>
                ))}

              {(doc.source_format === 'text' ||
                doc.source_format === 'markdown' ||
                doc.source_format === 'csv') &&
                (textContent !== null ? (
                  <pre className="max-h-[80vh] overflow-auto whitespace-pre-wrap px-6 py-6 text-sm text-slate-700">
                    {textContent}
                  </pre>
                ) : (
                  !loading && <div className="px-6 py-20 text-center text-sm text-slate-400">No preview.</div>
                ))}
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
