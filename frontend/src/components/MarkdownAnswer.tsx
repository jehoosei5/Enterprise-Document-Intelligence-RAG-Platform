import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
})

/** Render LLM answers as sanitized markdown (bold, lists, citations stay as [n]). */
export default function MarkdownAnswer({
  content,
  className = 'prose prose-sm prose-slate max-w-none text-xs leading-relaxed',
}: {
  content: string
  className?: string
}) {
  if (!content) return null
  const html = DOMPurify.sanitize(md.render(content))
  return <div className={className} dangerouslySetInnerHTML={{ __html: html }} />
}
