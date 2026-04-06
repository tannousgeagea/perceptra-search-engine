import {
  createContext, useContext, useState, useCallback,
  type ReactNode,
} from 'react'

export interface CompareItem {
  id: number
  type: 'image' | 'detection'
  url: string
  label: string
  plant_site: string
  captured_at: string
}

interface CompareContextValue {
  items: CompareItem[]
  addItem: (item: CompareItem) => void
  removeItem: (id: number) => void
  clearAll: () => void
  isInTray: (id: number) => boolean
}

const CompareContext = createContext<CompareContextValue | null>(null)

const STORAGE_KEY = 'compare_tray'
const MAX_ITEMS = 4

function loadFromStorage(): CompareItem[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function saveToStorage(items: CompareItem[]) {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(items))
}

export function CompareProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<CompareItem[]>(loadFromStorage)

  const addItem = useCallback((item: CompareItem) => {
    setItems((prev) => {
      if (prev.some((p) => p.id === item.id && p.type === item.type)) return prev
      if (prev.length >= MAX_ITEMS) return prev
      const next = [...prev, item]
      saveToStorage(next)
      return next
    })
  }, [])

  const removeItem = useCallback((id: number) => {
    setItems((prev) => {
      const next = prev.filter((p) => p.id !== id)
      saveToStorage(next)
      return next
    })
  }, [])

  const clearAll = useCallback(() => {
    setItems([])
    sessionStorage.removeItem(STORAGE_KEY)
  }, [])

  const isInTray = useCallback((id: number) => items.some((p) => p.id === id), [items])

  return (
    <CompareContext.Provider value={{ items, addItem, removeItem, clearAll, isInTray }}>
      {children}
    </CompareContext.Provider>
  )
}

export function useCompare(): CompareContextValue {
  const ctx = useContext(CompareContext)
  if (!ctx) throw new Error('useCompare must be used within CompareProvider')
  return ctx
}
