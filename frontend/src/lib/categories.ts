import { useEffect, useState } from 'react'
import { listDocuments } from './documents'

export function useCategories(token: string) {
  const [categories, setCategories] = useState<string[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    listDocuments(token)
      .then((docs) => {
        if (!active) return
        const cats = Array.from(new Set(docs.map((d) => d.category).filter(Boolean))) as string[]
        cats.sort((a, b) => a.localeCompare(b))
        setCategories(cats)
      })
      .catch((err) => {
        console.error('Failed to fetch categories:', err)
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    
    return () => { active = false }
  }, [token])

  return { categories, loading }
}
