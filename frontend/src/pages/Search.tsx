import { useState, useRef, useCallback, useEffect, type DragEvent, type ChangeEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Image, Type, Layers, Copy, SlidersHorizontal, LayoutGrid,
  List, Upload, X, Search as SearchIcon, Loader2, AlertCircle,
  MapPin, Clock, Tag, ChevronDown, ChevronUp, Bot, Sparkles,
  History, RotateCcw, ExternalLink,
  type LucideIcon,
} from 'lucide-react'
import { searchByImage, searchByText, searchHybrid, searchSimilar, agentSearch, getSearchHistory, getTags } from '../api/client'
import type { SearchResponse, DetectionSearchResult, ImageSearchResult, SearchType, TagResponse, AgentSearchResponse, SearchHistoryItem } from '../types/api'
import ImageModal, { type ImageItem } from '../components/ImageModal'

type TabId = 'image' | 'text' | 'hybrid' | 'similar' | 'agent' | 'history'

const TABS: { id: TabId; label: string; icon: LucideIcon }[] = [
  { id: 'image',   label: 'Image',   icon: Image },
  { id: 'text',    label: 'Text',    icon: Type },
  { id: 'hybrid',  label: 'Hybrid',  icon: Layers },
  { id: 'similar', label: 'Similar', icon: Copy },
  { id: 'agent',   label: 'Agent',   icon: Bot },
  { id: 'history', label: 'History', icon: History },
]

function ScoreBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100)
  const color = pct >= 80 ? 'var(--success)' : pct >= 60 ? 'var(--amber)' : 'var(--danger)'
  return (
    <div style={{
      fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 700,
      color, letterSpacing: '-0.02em',
    }}>
      {pct}%
    </div>
  )
}

type AllResultItem = { type: 'detection'; item: DetectionSearchResult } | { type: 'image'; item: ImageSearchResult }

function buildAllResults(results: SearchResponse): AllResultItem[] {
  return [
    ...(results.detection_results ?? []).map((d) => ({ type: 'detection' as const, item: d })),
    ...(results.image_results ?? []).map((d) => ({ type: 'image' as const, item: d })),
  ].sort((a, b) => b.item.similarity_score - a.item.similarity_score)
}

function buildGallery(all: AllResultItem[]): ImageItem[] {
  return all.map(({ type, item }) => {
    const url = type === 'detection'
      ? (item as DetectionSearchResult).image_url
      : (item as ImageSearchResult).download_url
    const lbl = type === 'detection'
      ? (item as DetectionSearchResult).label
      : (item as ImageSearchResult).filename
    if (!url) return null
    const detailUrl = type === 'detection'
      ? `/media/detections/${item.id}`
      : `/media/images/${item.id}`
    return {
      url,
      filename: lbl,
      subtitle: `${Math.round(item.similarity_score * 100)}% match · ${item.plant_site}`,
      badge: type === 'detection' ? 'DETECTION' : 'IMAGE',
      badgeColor: type === 'detection' ? 'var(--danger)' : 'var(--cyan-400)',
      detailUrl,
    } as ImageItem
  }).filter((x): x is ImageItem => x !== null)
}

function ResultGrid({
  results,
  onOpenModal,
  onDetail,
}: {
  results: SearchResponse
  onOpenModal: (url: string, all: AllResultItem[]) => void
  onDetail: (type: string, id: number) => void
}) {
  const all = buildAllResults(results)

  if (all.length === 0) return (
    <div className="empty-state">
      <div className="empty-state-icon"><SearchIcon size={24} /></div>
      <p style={{ color: 'var(--text-secondary)', fontSize: 14 }}>No results found.</p>
      <p style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 4 }}>Try adjusting your filters or search parameters.</p>
    </div>
  )

  return (
    <div className="media-grid">
      {all.map(({ type, item }) => {
        const imgUrl = type === 'detection'
          ? (item as DetectionSearchResult).crop_url ?? (item as DetectionSearchResult).image_url
          : (item as ImageSearchResult).download_url
        const modalUrl = type === 'detection'
          ? (item as DetectionSearchResult).image_url
          : (item as ImageSearchResult).download_url
        const label = type === 'detection' ? (item as DetectionSearchResult).label : (item as ImageSearchResult).filename
        const plant = item.plant_site
        const ts    = new Date(item.captured_at).toLocaleString()
        const conf  = type === 'detection' ? (item as DetectionSearchResult).confidence : undefined

        return (
          <div
            key={`${type}-${item.id}`}
            className="result-card"
            onClick={() => { if (modalUrl) onOpenModal(modalUrl, all) }}
            style={{ cursor: modalUrl ? 'pointer' : 'default' }}
          >
            {/* Thumbnail */}
            <div className="media-thumbnail">
              {imgUrl
                ? <img src={imgUrl} alt={label} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                : <Image size={28} />
              }
            </div>
            {/* Info */}
            <div style={{ padding: '10px 12px' }}>
              <div className="flex items-center justify-between mb-2">
                <ScoreBadge score={item.similarity_score} />
                <div className="flex items-center gap-2">
                  <button
                    className="btn btn-ghost btn-icon"
                    style={{ padding: 3 }}
                    onClick={(e) => { e.stopPropagation(); onDetail(type, item.id) }}
                    title="View details"
                  >
                    <ExternalLink size={11} style={{ color: 'var(--amber)' }} />
                  </button>
                  <span className={`badge ${type === 'detection' ? 'badge-danger' : 'badge-cyan'}`}>
                    {type === 'detection' ? (label ?? 'DETECT') : 'IMAGE'}
                  </span>
                </div>
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-primary)', fontWeight: 500, marginBottom: 6, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {label}
              </div>
              {conf !== undefined && (
                <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)', marginBottom: 4 }}>
                  Conf: <span style={{ color: 'var(--amber)' }}>{Math.round(conf * 100)}%</span>
                </div>
              )}
              <div className="flex items-center gap-1" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                <MapPin size={10} />
                <span className="truncate">{plant}</span>
              </div>
              <div className="flex items-center gap-1 mt-2" style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                <Clock size={9} />
                <span>{ts}</span>
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function ResultList({
  results,
  onOpenModal,
  onDetail,
}: {
  results: SearchResponse
  onOpenModal: (url: string, all: AllResultItem[]) => void
  onDetail: (type: string, id: number) => void
}) {
  const all = buildAllResults(results)

  if (all.length === 0) return (
    <div className="empty-state">
      <div className="empty-state-icon"><SearchIcon size={24} /></div>
      <p style={{ color: 'var(--text-secondary)' }}>No results found.</p>
    </div>
  )

  return (
    <div className="table-wrapper">
      <div style={{ background: 'var(--bg-surface)' }}>
        {all.map(({ type, item }) => {
          const label = type === 'detection' ? (item as DetectionSearchResult).label : (item as ImageSearchResult).filename
          const plant = item.plant_site
          const ts = new Date(item.captured_at).toLocaleDateString()
          const rowUrl = type === 'detection'
            ? (item as DetectionSearchResult).image_url
            : (item as ImageSearchResult).download_url

          return (
            <div
              key={`${type}-${item.id}`}
              className="result-list-row"
              style={{ gridTemplateColumns: '60px 1fr 80px auto auto auto auto', cursor: rowUrl ? 'pointer' : 'default' }}
              onClick={() => { if (rowUrl) onOpenModal(rowUrl, all) }}
            >
              <div style={{ width: 60, height: 44, background: 'var(--bg-muted)', borderRadius: 'var(--radius-md)', overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                {(() => {
                  const url = type === 'detection'
                    ? (item as DetectionSearchResult).image_url
                    : (item as ImageSearchResult).download_url
                  return url
                    ? <img src={url} alt={label} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    : <Image size={18} style={{ color: 'var(--text-muted)' }} />
                })()}
              </div>
              <div>
                <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 2 }}>{label}</div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{ts}</div>
              </div>
              <ScoreBadge score={item.similarity_score} />
              <span className={`badge ${type === 'detection' ? 'badge-danger' : 'badge-cyan'}`}>
                {type.toUpperCase()}
              </span>
              <div className="flex items-center gap-1" style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                <MapPin size={11} />
                <span>{plant}</span>
              </div>
              <button
                className="btn btn-ghost btn-icon"
                style={{ padding: 3 }}
                onClick={(e) => { e.stopPropagation(); onDetail(type, item.id) }}
                title="View details"
              >
                <ExternalLink size={12} style={{ color: 'var(--amber)' }} />
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function Search() {
  const navigate = useNavigate()
  const [tab, setTab]               = useState<TabId>('image')
  const [viewMode, setViewMode]     = useState<'grid' | 'list'>('grid')
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [loading, setLoading]       = useState(false)
  const [error, setError]           = useState('')
  const [results, setResults]       = useState<SearchResponse | null>(null)
  const [agentResults, setAgentResults] = useState<AgentSearchResponse | null>(null)
  const [dragOver, setDragOver]     = useState(false)
  const [imageModal, setImageModal] = useState<{ images: ImageItem[]; index: number } | null>(null)

  // History
  const [history, setHistory]           = useState<SearchHistoryItem[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)

  // Image upload
  const [imageFile, setImageFile]   = useState<File | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Text / hybrid
  const [query, setQuery]           = useState('')
  const [textWeight, setTextWeight] = useState(0.5)

  // Similar
  const [itemId, setItemId]         = useState('')
  const [itemType, setItemType]     = useState<'image' | 'detection'>('detection')

  // Filters
  const [topK, setTopK]             = useState(10)
  const [searchType, setSearchType] = useState<SearchType>('detections')
  const [plantSite, setPlantSite]   = useState('')
  const [shift, setShift]           = useState('')
  const [minConf, setMinConf]       = useState('')
  const [dateFrom, setDateFrom]     = useState('')
  const [dateTo, setDateTo]         = useState('')
  const [selectedTags, setSelectedTags] = useState<string[]>([])
  const [availableTags, setAvailableTags] = useState<TagResponse[]>([])

  useEffect(() => {
    getTags().then(r => setAvailableTags(r.data)).catch(() => {})
  }, [])

  useEffect(() => {
    if (tab === 'history') {
      setHistoryLoading(true)
      getSearchHistory({ page: 1, page_size: 30 })
        .then(r => setHistory(r.data.items))
        .catch(() => {})
        .finally(() => setHistoryLoading(false))
    }
  }, [tab])

  const toggleTag = (name: string) => {
    setSelectedTags(prev =>
      prev.includes(name) ? prev.filter(t => t !== name) : [...prev, name]
    )
  }

  const buildFilters = () => ({
    ...(plantSite ? { plant_site: plantSite } : {}),
    ...(shift ? { shift } : {}),
    ...(minConf ? { min_confidence: parseFloat(minConf) } : {}),
    ...(dateFrom ? { date_from: dateFrom } : {}),
    ...(dateTo ? { date_to: dateTo } : {}),
    ...(selectedTags.length > 0 ? { tags: selectedTags } : {}),
  })

  const onDrop = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault(); setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file?.type.startsWith('image/')) setImageFile(file)
  }, [])

  const handleSearch = async () => {
    setError(''); setLoading(true); setResults(null); setAgentResults(null)
    try {
      if (tab === 'agent') {
        if (!query.trim()) { setError('Please enter a natural language query.'); setLoading(false); return }
        const res = await agentSearch({ query: query.trim(), top_k: topK, search_type: searchType })
        setAgentResults(res.data)
        // Also set results for the shared result grid
        setResults({
          query_id: res.data.query_id,
          search_type: res.data.search_plan.search_method,
          results_type: 'agent',
          image_results: res.data.image_results,
          detection_results: res.data.detection_results,
          total_results: res.data.total_results,
          execution_time_ms: res.data.execution_time_ms,
          filters_applied: {},
          model_version: res.data.model_version,
        })
        setLoading(false)
        return
      }

      let res
      const filters = buildFilters()

      if (tab === 'image') {
        if (!imageFile) { setError('Please select an image file.'); setLoading(false); return }
        const fd = new FormData()
        fd.append('file', imageFile)
        const params: Record<string, string | number> = { top_k: topK, search_type: searchType }
        const f = buildFilters()
        if (f.plant_site) params.plant_site = f.plant_site
        if (f.shift) params.shift = f.shift
        if (f.min_confidence) params.min_confidence = f.min_confidence
        res = await searchByImage(fd, params)

      } else if (tab === 'text') {
        if (!query.trim()) { setError('Please enter a search query.'); setLoading(false); return }
        res = await searchByText({ query, top_k: topK, search_type: searchType, filters: buildFilters() })

      } else if (tab === 'hybrid') {
        if (!query.trim() || !imageFile) { setError('Hybrid search requires both an image and text query.'); setLoading(false); return }
        const fd = new FormData()
        fd.append('file', imageFile)
        const params: Record<string, string | number> = { query, text_weight: textWeight, top_k: topK, search_type: searchType }
        const f = buildFilters()
        if (f.plant_site) params.plant_site = f.plant_site
        if (f.shift) params.shift = f.shift
        res = await searchHybrid(fd, params)

      } else {
        if (!itemId) { setError('Please enter an item ID.'); setLoading(false); return }
        res = await searchSimilar({ item_id: parseInt(itemId), item_type: itemType, top_k: topK, filters })
      }

      setResults(res.data)
    } catch {
      setError('Search failed. Check your connection and try again.')
    } finally {
      setLoading(false)
    }
  }

  const handleRerunSearch = (item: SearchHistoryItem) => {
    if (item.query_text) {
      setQuery(item.query_text)
    }
    // Map query_type to our tab ID
    const typeMap: Record<string, TabId> = {
      text: 'text', image: 'image', hybrid: 'hybrid', similar: 'similar', agent: 'agent',
    }
    setTab(typeMap[item.query_type] ?? 'text')
  }

  const handleOpenModal = (clickedUrl: string, all: AllResultItem[]) => {
    const gallery = buildGallery(all)
    const idx = gallery.findIndex(it => it.url === clickedUrl)
    setImageModal({ images: gallery, index: idx >= 0 ? idx : 0 })
  }

  return (
    <div className="page-container">
      {/* Image lightbox modal */}
      {imageModal && (
        <ImageModal
          images={imageModal.images}
          initialIndex={imageModal.index}
          onClose={() => setImageModal(null)}
        />
      )}

      <div className="page-header">
        <h1 className="page-title">Visual Search</h1>
        <p className="page-subtitle">Multi-modal search — CLIP / DINOv2 / SAM3</p>
      </div>

      {/* Tabs bar */}
      <div className="card mb-4" style={{ marginBottom: 20 }}>
        <div className="tab-bar" style={{ marginBottom: 20 }}>
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => { setTab(id); setResults(null); setAgentResults(null); setError('') }}
              className={`tab-btn${tab === id ? ' active' : ''}`}
            >
              <Icon size={14} />
              {label}
            </button>
          ))}
        </div>

        {/* History panel — replaces search form when active */}
        {tab === 'history' ? (
          <div style={{ animation: 'fadeUp 0.2s ease-out' }}>
            {historyLoading ? (
              <div className="flex items-center justify-center" style={{ padding: '40px 0' }}>
                <div className="spinner" />
              </div>
            ) : history.length === 0 ? (
              <div className="empty-state" style={{ padding: '40px 20px' }}>
                <div className="empty-state-icon"><History size={22} /></div>
                <p style={{ color: 'var(--text-secondary)', fontSize: 14, fontFamily: 'var(--font-display)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  No Search History
                </p>
                <p style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 4 }}>
                  Your past searches will appear here.
                </p>
              </div>
            ) : (
              <div className="table-wrapper">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Query</th>
                      <th>Type</th>
                      <th>Results</th>
                      <th>Time</th>
                      <th>Date</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((item) => (
                      <tr key={item.id}>
                        <td style={{ maxWidth: 260 }}>
                          <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {item.query_text || `[${item.query_type} search]`}
                          </span>
                        </td>
                        <td>
                          <span className={`badge ${item.query_type === 'text' ? 'badge-cyan' : item.query_type === 'image' ? 'badge-amber' : item.query_type === 'agent' ? 'badge-success' : 'badge-dim'}`}>
                            {item.query_type}
                          </span>
                        </td>
                        <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-primary)' }}>
                          {item.results_count}
                        </td>
                        <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>
                          {item.execution_time_ms}ms
                        </td>
                        <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>
                          {new Date(item.created_at).toLocaleDateString()}
                          <br />
                          {new Date(item.created_at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}
                        </td>
                        <td>
                          {item.query_text && (
                            <button
                              className="btn btn-ghost btn-sm"
                              onClick={() => handleRerunSearch(item)}
                              title="Re-run this search"
                            >
                              <RotateCcw size={12} />
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ) : (
        /* Search form content */
        <>

        {/* Search content */}
        {(tab === 'image' || tab === 'hybrid') && (
          <div
            className={`dropzone${dragOver ? ' drag-over' : ''}`}
            style={{ marginBottom: 16 }}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              style={{ display: 'none' }}
              onChange={(e: ChangeEvent<HTMLInputElement>) => {
                const f = e.target.files?.[0]
                if (f) setImageFile(f)
              }}
            />
            {imageFile ? (
              <div className="flex items-center justify-center gap-3">
                <div style={{
                  width: 64, height: 64, borderRadius: 'var(--radius-md)', overflow: 'hidden',
                  border: '2px solid var(--border-amber)',
                }}>
                  <img
                    src={URL.createObjectURL(imageFile)}
                    alt="preview"
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  />
                </div>
                <div style={{ textAlign: 'left' }}>
                  <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-primary)' }}>{imageFile.name}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                    {(imageFile.size / 1024).toFixed(1)} KB
                  </div>
                </div>
                <button
                  className="btn btn-ghost btn-icon btn-sm"
                  onClick={(e) => { e.stopPropagation(); setImageFile(null) }}
                  style={{ marginLeft: 8 }}
                >
                  <X size={14} />
                </button>
              </div>
            ) : (
              <>
                <div className="dropzone-icon"><Upload size={22} /></div>
                <p style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 4 }}>
                  Drop an image or click to browse
                </p>
                <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>PNG, JPG, WEBP — Max 50MB</p>
              </>
            )}
          </div>
        )}

        {(tab === 'text' || tab === 'hybrid') && (
          <div className="form-group" style={{ marginBottom: 16 }}>
            <label className="form-label">
              {tab === 'hybrid' ? 'Text Query' : 'Search Query'}
            </label>
            <div style={{ position: 'relative' }}>
              <SearchIcon size={15} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
              <input
                type="text"
                className="form-input"
                placeholder='e.g. "metal fragments in incineration hopper", "glass contamination"'
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                style={{ paddingLeft: 38 }}
              />
            </div>
          </div>
        )}

        {tab === 'hybrid' && (
          <div className="form-group" style={{ marginBottom: 16 }}>
            <label className="form-label">
              Text Weight: <span style={{ color: 'var(--amber)', fontFamily: 'var(--font-mono)' }}>{textWeight.toFixed(1)}</span>
            </label>
            <input
              type="range" min="0" max="1" step="0.1"
              value={textWeight}
              onChange={(e) => setTextWeight(parseFloat(e.target.value))}
              style={{ width: '100%', accentColor: 'var(--amber)' }}
            />
            <div className="flex justify-between" style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
              <span>← Image heavy</span>
              <span>Text heavy →</span>
            </div>
          </div>
        )}

        {tab === 'agent' && (
          <div style={{ marginBottom: 16 }}>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12,
              padding: '8px 12px',
              background: 'linear-gradient(135deg, rgba(245,166,35,0.06), rgba(34,211,238,0.04))',
              border: '1px solid var(--border-amber)',
              borderRadius: 'var(--radius-md)',
            }}>
              <Sparkles size={14} style={{ color: 'var(--amber)', flexShrink: 0 }} />
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                Describe what you're looking for in plain language. The AI agent will parse filters, select the best search mode, and find results.
              </span>
            </div>
            <div className="form-group">
              <label className="form-label">Natural Language Query</label>
              <div style={{ position: 'relative' }}>
                <Bot size={15} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--amber)' }} />
                <input
                  type="text"
                  className="form-input"
                  placeholder='e.g. "show me rust detections from Plant A last week" or "find metal fragments with high confidence"'
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                  style={{ paddingLeft: 38, borderColor: 'var(--border-amber)' }}
                />
              </div>
            </div>
          </div>
        )}

        {tab === 'similar' && (
          <div className="grid-2" style={{ marginBottom: 16 }}>
            <div className="form-group">
              <label className="form-label">Item ID</label>
              <input
                type="number"
                className="form-input"
                placeholder="e.g. 1042"
                value={itemId}
                onChange={(e) => setItemId(e.target.value)}
                style={{ fontFamily: 'var(--font-mono)' }}
              />
            </div>
            <div className="form-group">
              <label className="form-label">Item Type</label>
              <select
                className="form-input form-select"
                value={itemType}
                onChange={(e) => setItemType(e.target.value as 'image' | 'detection')}
              >
                <option value="detection">Detection</option>
                <option value="image">Image</option>
              </select>
            </div>
          </div>
        )}

        {error && (
          <div className="alert alert-error mb-4" style={{ marginBottom: 16 }}>
            <AlertCircle size={15} />
            <span>{error}</span>
          </div>
        )}

        <div className="flex items-center gap-3">
          <button
            className="btn btn-primary"
            onClick={handleSearch}
            disabled={loading}
            style={{ minWidth: 140, justifyContent: 'center' }}
          >
            {loading
              ? <><Loader2 size={15} style={{ animation: 'spin 0.8s linear infinite' }} /> Searching...</>
              : <><SearchIcon size={15} /> Search</>
            }
          </button>

          <button
            className={`btn btn-secondary`}
            onClick={() => setFiltersOpen((o) => !o)}
            style={{ gap: 6 }}
          >
            <SlidersHorizontal size={14} />
            Filters
            {filtersOpen ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
          </button>

          {results && (
            <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)' }}>
              <span style={{ color: 'var(--amber)' }}>{results.total_results}</span> results
              &nbsp;·&nbsp;
              {results.execution_time_ms}ms
              &nbsp;·&nbsp;
              {results.model_version}
            </span>
          )}
        </div>

        {/* Filters panel */}
        {filtersOpen && (
          <div style={{
            marginTop: 16,
            padding: 16,
            background: 'var(--bg-elevated)',
            border: '1px solid var(--border-base)',
            borderRadius: 'var(--radius-lg)',
            animation: 'fadeUp 0.2s ease-out',
          }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
              <div className="form-group">
                <label className="form-label">Plant Site</label>
                <input type="text" className="form-input" placeholder="Unit A, Unit B..." value={plantSite} onChange={(e) => setPlantSite(e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Shift</label>
                <select className="form-input form-select" value={shift} onChange={(e) => setShift(e.target.value)}>
                  <option value="">Any</option>
                  <option value="morning">Morning</option>
                  <option value="afternoon">Afternoon</option>
                  <option value="night">Night</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Search Type</label>
                <select className="form-input form-select" value={searchType} onChange={(e) => setSearchType(e.target.value as SearchType)}>
                  <option value="detections">Detections</option>
                  <option value="images">Images</option>
                  <option value="both">Both</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Min Confidence</label>
                <input type="number" className="form-input" placeholder="0.0–1.0" min="0" max="1" step="0.1" value={minConf} onChange={(e) => setMinConf(e.target.value)} style={{ fontFamily: 'var(--font-mono)' }} />
              </div>
              <div className="form-group">
                <label className="form-label">Date From</label>
                <input type="date" className="form-input" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Date To</label>
                <input type="date" className="form-input" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
              </div>
            </div>
            {availableTags.length > 0 && (
              <div style={{ marginTop: 12 }}>
                <label className="form-label" style={{ marginBottom: 8, display: 'flex', alignItems: 'center', gap: 4 }}>
                  <Tag size={11} />
                  Tags
                  {selectedTags.length > 0 && (
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--amber)', marginLeft: 4 }}>
                      ({selectedTags.length})
                    </span>
                  )}
                </label>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {availableTags.map(tag => {
                    const active = selectedTags.includes(tag.name)
                    return (
                      <button
                        key={tag.id}
                        type="button"
                        onClick={() => toggleTag(tag.name)}
                        style={{
                          padding: '4px 10px',
                          borderRadius: 'var(--radius-full)',
                          fontSize: 11,
                          fontFamily: 'var(--font-mono)',
                          fontWeight: 500,
                          cursor: 'pointer',
                          transition: 'all var(--transition-fast)',
                          border: active
                            ? `1.5px solid ${tag.color}`
                            : '1.5px solid var(--border-dim)',
                          background: active
                            ? `${tag.color}18`
                            : 'transparent',
                          color: active
                            ? tag.color
                            : 'var(--text-muted)',
                        }}
                      >
                        {tag.name}
                      </button>
                    )
                  })}
                </div>
              </div>
            )}
            <div className="flex items-center gap-3 mt-4">
              <label className="form-label" style={{ margin: 0 }}>Top K:</label>
              <input
                type="range" min="1" max="50" value={topK}
                onChange={(e) => setTopK(parseInt(e.target.value))}
                style={{ flex: 1, accentColor: 'var(--amber)' }}
              />
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--amber)', minWidth: 28, textAlign: 'right' }}>
                {topK}
              </span>
            </div>
          </div>
        )}
        </>
        )}
      </div>

      {/* Agent reasoning panel */}
      {agentResults && tab !== 'history' && (
        <div className="card mb-4" style={{ marginBottom: 16, animation: 'fadeUp 0.3s ease-out' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div className="flex items-center gap-2">
              <Bot size={14} style={{ color: 'var(--amber)' }} />
              <span style={{ fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>
                Agent Reasoning
              </span>
              {agentResults.fallback_used && (
                <span className="badge badge-amber" style={{ fontSize: 10 }}>Fallback</span>
              )}
            </div>

            <div style={{
              padding: '10px 14px',
              background: 'var(--bg-elevated)',
              border: '1px solid var(--border-dim)',
              borderRadius: 'var(--radius-md)',
              fontSize: 13,
              color: 'var(--text-secondary)',
              lineHeight: 1.6,
            }}>
              {agentResults.search_plan.reasoning}
            </div>

            <div className="flex items-center gap-4" style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
              <span>Method: <span style={{ color: 'var(--amber)' }}>{agentResults.search_plan.search_method}</span></span>
              {agentResults.search_plan.query_text && (
                <span>Query: <span style={{ color: 'var(--cyan-400)' }}>"{agentResults.search_plan.query_text}"</span></span>
              )}
              <span>LLM: {agentResults.llm_time_ms}ms</span>
              <span>Search: {agentResults.execution_time_ms}ms</span>
              <span>{agentResults.llm_provider}</span>
            </div>

            {agentResults.search_plan.filters && Object.keys(agentResults.search_plan.filters).length > 0 && (
              <div className="flex items-center gap-2 flex-wrap">
                <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-display)', fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase' }}>
                  Extracted Filters:
                </span>
                {Object.entries(agentResults.search_plan.filters).map(([key, val]) => (
                  val != null && (
                    <span
                      key={key}
                      style={{
                        fontSize: 10, fontFamily: 'var(--font-mono)',
                        padding: '2px 8px', borderRadius: 4,
                        background: 'var(--amber-glow)',
                        border: '1px solid var(--border-amber)',
                        color: 'var(--amber)',
                      }}
                    >
                      {key}: {Array.isArray(val) ? val.join(', ') : String(val)}
                    </span>
                  )
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Results */}
      {results && tab !== 'history' && (
        <div style={{ animation: 'fadeUp 0.3s ease-out' }}>
          <div className="flex items-center justify-between mb-4">
            <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 14, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>
              Results
            </h2>
            <div className="flex items-center gap-2">
              <button
                className={`btn btn-icon btn-sm ${viewMode === 'grid' ? 'btn-secondary' : 'btn-ghost'}`}
                onClick={() => setViewMode('grid')}
                title="Grid view"
              >
                <LayoutGrid size={14} />
              </button>
              <button
                className={`btn btn-icon btn-sm ${viewMode === 'list' ? 'btn-secondary' : 'btn-ghost'}`}
                onClick={() => setViewMode('list')}
                title="List view"
              >
                <List size={14} />
              </button>
            </div>
          </div>
          {viewMode === 'grid'
            ? <ResultGrid results={results} onOpenModal={handleOpenModal} onDetail={(type, id) => navigate(type === 'detection' ? `/media/detections/${id}` : `/media/images/${id}`)} />
            : <ResultList results={results} onOpenModal={handleOpenModal} onDetail={(type, id) => navigate(type === 'detection' ? `/media/detections/${id}` : `/media/images/${id}`)} />
          }
        </div>
      )}

      {/* Empty state (no search yet) */}
      {!results && !loading && tab !== 'history' && (
        <div className="empty-state" style={{ padding: '48px 32px' }}>
          <div className="empty-state-icon"><SearchIcon size={28} /></div>
          <p style={{ fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 600, color: 'var(--text-secondary)', letterSpacing: '0.04em', textTransform: 'uppercase' }}>
            Ready to Search
          </p>
          <p style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 6 }}>
            Select a search mode above and run a query.
          </p>
        </div>
      )}
    </div>
  )
}
