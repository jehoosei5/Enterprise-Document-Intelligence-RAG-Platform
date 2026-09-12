import {
  ArrowUp,
  Clock,
  Copy,
  FileText,
  MessageSquare,
  Plus,
  RotateCw,
  ShieldCheck,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  User as UserIcon,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useOutletContext } from 'react-router-dom'

import type { AuthOutletContext } from '../components/RequireAuth'
import Sidebar from '../components/Sidebar'
import { getConversation, listConversations, type ConversationSummary } from '../lib/conversations'
import { askQueryStream, submitFeedback, type QueryResponse } from '../lib/query'

function relativeDate(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const days = Math.floor(diffMs / 86_400_000)
  if (days <= 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days < 30) return `${days}d ago`
  return new Date(iso).toLocaleDateString()
}

// We represent a conversation turn locally.
interface ChatTurn {
  id: string
  query_id?: string
  question: string
  answer: string
  sources: QueryResponse['sources']
  timestamp: string
  status: 'loading' | 'streaming' | 'success' | 'error'
  feedback?: 'up' | 'down'
}

export default function ChatPage() {
  const { user, token } = useOutletContext<AuthOutletContext>()
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [input, setInput] = useState('')
  const [asking, setAsking] = useState(false)
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [loadingConversation, setLoadingConversation] = useState(false)

  const bottomRef = useRef<HTMLDivElement>(null)

  const refreshConversations = async () => {
    try {
      setConversations(await listConversations(token))
    } catch (err) {
      console.error('Failed to load conversation history', err)
    }
  }

  useEffect(() => {
    refreshConversations()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleNewThread = () => {
    setTurns([])
    setConversationId(null)
  }

  const handleSelectConversation = async (id: string) => {
    if (id === conversationId || loadingConversation) return
    setLoadingConversation(true)
    try {
      const detail = await getConversation(token, id)
      setTurns(
        detail.turns.map((t) => ({
          id: t.query_id,
          query_id: t.query_id,
          question: t.question,
          answer: t.answer,
          sources: t.sources,
          timestamp: new Date(t.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          status: 'success' as const,
        })),
      )
      setConversationId(id)
    } catch (err) {
      console.error('Failed to load conversation', err)
    } finally {
      setLoadingConversation(false)
    }
  }

  const handleSend = async () => {
    const trimmed = input.trim()
    if (!trimmed || asking) return

    const newTurn: ChatTurn = {
      id: Date.now().toString(),
      question: trimmed,
      answer: '',
      sources: [],
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      status: 'loading'
    }

    setTurns((prev) => [...prev, newTurn])
    setInput('')
    setAsking(true)

    // Scroll to bottom
    setTimeout(() => {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }, 100)

    try {
      const done = await askQueryStream(
        token,
        { question: trimmed, conversation_id: conversationId || undefined },
        (delta) => {
          setTurns((prev) =>
            prev.map((t) => (t.id === newTurn.id ? { ...t, answer: t.answer + delta, status: 'streaming' } : t))
          )
        },
      )
      if (!conversationId && done.conversation_id) {
        setConversationId(done.conversation_id)
      }
      setTurns((prev) =>
        prev.map((t) =>
          t.id === newTurn.id
            ? { ...t, sources: done.sources, status: 'success', query_id: done.query_id }
            : t
        )
      )
      refreshConversations()
    } catch (err) {
      setTurns((prev) =>
        prev.map((t) =>
          t.id === newTurn.id
            ? { ...t, answer: 'Sorry, I encountered an error answering your question.', status: 'error' }
            : t
        )
      )
    } finally {
      setAsking(false)
      setTimeout(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
      }, 100)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleFeedback = async (turnId: string, queryId: string, rating: 'up' | 'down') => {
    try {
      await submitFeedback(token, queryId, rating)
      setTurns((prev) =>
        prev.map((t) =>
          t.id === turnId ? { ...t, feedback: rating } : t
        )
      )
    } catch (err) {
      console.error('Failed to submit feedback', err)
    }
  }

  return (
    <div className="flex h-screen bg-slate-50">
      <Sidebar userEmail={user.email} token={token} />

      <div className="flex w-64 shrink-0 flex-col border-r border-slate-200 bg-white">
        <div className="flex items-center justify-between border-b border-slate-100 px-4 py-4">
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">History</span>
          <button
            onClick={handleNewThread}
            aria-label="New thread"
            className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          >
            <Plus className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {conversations.length === 0 ? (
            <p className="px-2 py-4 text-center text-xs text-slate-400">No conversations yet.</p>
          ) : (
            <div className="space-y-1">
              {conversations.map((conv) => (
                <button
                  key={conv.id}
                  onClick={() => handleSelectConversation(conv.id)}
                  className={`block w-full rounded-lg px-3 py-2 text-left transition ${
                    conv.id === conversationId ? 'bg-blue-50' : 'hover:bg-slate-50'
                  }`}
                >
                  <p
                    className={`truncate text-sm font-medium ${
                      conv.id === conversationId ? 'text-blue-700' : 'text-slate-700'
                    }`}
                  >
                    {conv.title}
                  </p>
                  <p className="mt-0.5 text-xs text-slate-400">
                    {conv.message_count} {conv.message_count === 1 ? 'message' : 'messages'} ·{' '}
                    {relativeDate(conv.created_at)}
                  </p>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top Header */}
        <header className="flex h-16 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-8">
          <div></div>
          <div className="flex items-center gap-4 text-slate-500">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-600 text-white">
              <UserIcon className="h-4 w-4" />
            </div>
          </div>
        </header>

        {/* Main Content Scroll Area */}
        <div className="flex-1 overflow-y-auto px-8 py-8">
          <div className="mx-auto max-w-4xl">
            {/* Title Area */}
            <div className="mb-6 flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2 text-xs font-semibold tracking-wide text-slate-500">
                  <div className="h-2 w-2 rounded-full bg-blue-600" />
                  ENTERPRISE KNOWLEDGE ENGINE
                </div>
                <h1 className="mt-1 text-3xl font-bold text-slate-900">Document Intelligence Assistant</h1>
                <p className="mt-1 text-sm text-slate-500">
                  Instant answers verified against company policies, compliance filings, and employee manuals.
                </p>
              </div>
            </div>

            {/* Chat Thread Container */}
            <div className="flex flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
              {/* Thread Header */}
              <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50/50 px-6 py-4">
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-1.5 text-sm font-semibold text-slate-900">
                    <ShieldCheck className="h-4 w-4 text-blue-600" />
                    Active Session: Knowledge Base
                  </div>
                  <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">
                    Verified Sources
                  </span>
                </div>
                <div className="flex items-center gap-4 text-xs text-slate-500">
                  <div className="flex items-center gap-1">
                    <Clock className="h-3.5 w-3.5" />
                    Updated just now
                  </div>
                  <button
                    onClick={handleNewThread}
                    className="flex items-center gap-1 font-medium hover:text-slate-700"
                  >
                    <RotateCw className="h-3.5 w-3.5" />
                    New Thread
                  </button>
                </div>
              </div>

              {/* Thread Messages */}
              <div className="flex flex-col p-6">
                {turns.length === 0 ? (
                  <div className="flex h-40 flex-col items-center justify-center text-slate-400">
                    <Sparkles className="mb-2 h-8 w-8 text-slate-300" />
                    <p className="text-sm">Start a conversation to get verified answers.</p>
                  </div>
                ) : (
                  <div className="space-y-8">
                    {turns.map((turn) => (
                      <div key={turn.id} className="flex flex-col space-y-6">
                        {/* User Message */}
                        <div className="flex items-start gap-4 self-end">
                          <div className="flex flex-col items-end">
                            <span className="mb-1 text-xs text-slate-500">
                              {user.email.split('@')[0]}
                            </span>
                            <div className="rounded-2xl rounded-tr-none bg-blue-700 px-5 py-3 text-sm text-white shadow-sm">
                              {turn.question}
                            </div>
                            <span className="mt-1 text-xs text-slate-400">{turn.timestamp}</span>
                          </div>
                          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-blue-100 text-blue-700">
                            <UserIcon className="h-5 w-5" />
                          </div>
                        </div>

                        {/* Assistant Message */}
                        <div className="flex items-start gap-4">
                          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-600">
                            <Sparkles className="h-5 w-5" />
                          </div>
                          <div className="flex flex-1 flex-col">
                            <div className="mb-1 flex items-center gap-2">
                              <span className="text-sm font-semibold text-slate-900">DocIntel Assistant</span>
                              {turn.sources.length > 0 && (
                                <span className="flex items-center gap-1 rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-medium text-blue-600">
                                  <ShieldCheck className="h-3 w-3" />
                                  Direct Policy Citation
                                </span>
                              )}
                            </div>

                            <div className="rounded-2xl rounded-tl-none bg-slate-50 px-6 py-5 text-sm text-slate-800 shadow-sm">
                              {turn.status === 'loading' && !turn.answer ? (
                                <div className="flex items-center gap-2 text-slate-500">
                                  <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" style={{ animationDelay: '0ms' }} />
                                  <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" style={{ animationDelay: '150ms' }} />
                                  <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" style={{ animationDelay: '300ms' }} />
                                </div>
                              ) : (
                                <div className="space-y-4">
                                  <div className="prose prose-sm prose-slate max-w-none leading-relaxed">
                                    {turn.answer}
                                  </div>

                                  {turn.sources && turn.sources.length > 0 && (
                                    <div className="mt-6 border-t border-slate-200 pt-5">
                                      <div className="mb-3 flex items-center justify-between">
                                        <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
                                          Cited Sources & Exact References
                                        </span>
                                        <span className="text-xs text-slate-400">Click to view source excerpt</span>
                                      </div>
                                      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                                        {turn.sources.map((src, i) => (
                                          <div key={i} className="flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-3 hover:border-slate-300">
                                            <div className="mb-2 flex items-start justify-between">
                                              <div className="flex h-7 w-7 items-center justify-center rounded bg-slate-100">
                                                <FileText className="h-4 w-4 text-slate-600" />
                                              </div>
                                              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs font-medium text-slate-600">
                                                {src.locator || `Source ${i + 1}`}
                                              </span>
                                            </div>
                                            <div>
                                              <p className="line-clamp-1 text-sm font-semibold text-slate-900">
                                                {src.filename}
                                              </p>
                                            </div>
                                          </div>
                                        ))}
                                      </div>
                                    </div>
                                  )}

                                  {turn.status === 'success' && (
                                    <div className="mt-4 flex items-center justify-between border-t border-slate-200 pt-4">
                                      <div className="flex items-center gap-3">
                                        <span className="text-xs font-medium text-slate-500">Was this accurate?</span>
                                        <div className="flex items-center gap-1">
                                          <button
                                            onClick={() => turn.query_id && handleFeedback(turn.id, turn.query_id, 'up')}
                                            className={`flex items-center gap-1 rounded px-2 py-1 text-xs font-medium transition ${
                                              turn.feedback === 'up'
                                                ? 'bg-blue-100 text-blue-700'
                                                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                                            }`}
                                          >
                                            <ThumbsUp className="h-3 w-3" />
                                            Yes
                                          </button>
                                          <button
                                            onClick={() => turn.query_id && handleFeedback(turn.id, turn.query_id, 'down')}
                                            className={`flex items-center gap-1 rounded px-2 py-1 text-xs font-medium transition ${
                                              turn.feedback === 'down'
                                                ? 'bg-red-100 text-red-700'
                                                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                                            }`}
                                          >
                                            <ThumbsDown className="h-3 w-3" />
                                            No
                                          </button>
                                        </div>
                                        <button className="ml-2 flex items-center gap-1 rounded bg-slate-100 px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-200">
                                          <Copy className="h-3 w-3" />
                                          Copy Answer
                                        </button>
                                      </div>
                                      {turn.sources.length > 0 && (
                                        <div className="flex items-center gap-1 text-xs font-medium text-slate-500">
                                          <ShieldCheck className="h-3.5 w-3.5 text-blue-600" />
                                          All citations verified against company-approved policies
                                        </div>
                                      )}
                                    </div>
                                  )}
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                    <div ref={bottomRef} />
                  </div>
                )}
              </div>
            </div>

            {/* Input Area */}
            <div className="mt-6">
              <div className="mb-2 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="h-2 w-2 rounded-full bg-blue-600" />
                  <span className="text-xs font-medium text-slate-500">Focused Scope:</span>
                  <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-700">
                    Global Knowledge Base
                  </span>
                </div>
                <span className="flex items-center gap-1 text-xs text-slate-400">
                  <MessageSquare className="h-3 w-3" />
                  Press Enter to send
                </span>
              </div>
              <div className="relative">
                <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-4">
                  <MessageSquare className="h-5 w-5 text-slate-400" />
                </div>
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Ask a question..."
                  disabled={asking}
                  className="w-full rounded-xl border border-slate-200 bg-white py-4 pl-11 pr-14 text-sm text-slate-900 shadow-sm outline-none ring-blue-600 focus:border-blue-600 focus:ring-1 disabled:bg-slate-50 disabled:text-slate-500"
                />
                <button
                  onClick={handleSend}
                  disabled={asking || !input.trim()}
                  className="absolute inset-y-2 right-2 flex items-center justify-center rounded-lg bg-blue-600 px-3 text-white transition hover:bg-blue-700 disabled:bg-slate-300"
                >
                  <ArrowUp className="h-5 w-5" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
