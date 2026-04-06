import { useState, useCallback } from 'react'

/**
 * Hook for managing multi-select state in list/grid views.
 * Selection is page-scoped — caller should call `deselectAll()` on tab/page change.
 */
export function useSelection() {
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())

  const toggle = useCallback((id: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const selectAll = useCallback((items: { id: number }[]) => {
    setSelectedIds(new Set(items.map(i => i.id)))
  }, [])

  const deselectAll = useCallback(() => {
    setSelectedIds(new Set())
  }, [])

  const isSelected = useCallback((id: number) => selectedIds.has(id), [selectedIds])

  const isAllSelected = useCallback(
    (items: { id: number }[]) => items.length > 0 && items.every(i => selectedIds.has(i.id)),
    [selectedIds],
  )

  return {
    selectedIds,
    count: selectedIds.size,
    toggle,
    selectAll,
    deselectAll,
    isSelected,
    isAllSelected,
  }
}
