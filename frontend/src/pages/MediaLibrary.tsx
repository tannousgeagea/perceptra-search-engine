import { useEffect, useState, useCallback, useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Image, Video, Target, LayoutGrid, List, RefreshCw,
  MapPin, Clock, Tag, ChevronLeft, ChevronRight, Trash2,
  Film, FileImage, Play, X, Download, Layers, ExternalLink,
  CheckSquare, Square, Zap,
} from 'lucide-react'
import {
  getImages, getVideos, getDetections, deleteImage, deleteVideo,
  bulkDeleteImages, bulkDeleteVideos, bulkDeleteDetections,
  bulkTagImages, bulkTagVideos, bulkTagDetections,
  getTags, getHazardConfigs, runDetection, exportMedia, exportDetections,
} from '../api/client'
import type { ImageMedia, VideoMedia, DetectionMedia, TagResponse, HazardConfig } from '../types/api'
import ImageModal, { type ImageItem } from '../components/ImageModal'
import { useSelection } from '../hooks/useSelection'
import BulkActionBar from '../components/BulkActionBar'
import ConfirmModal from '../components/ConfirmModal'

type TabId = 'images' | 'videos' | 'detections'

/* Checkbox overlay for grid cards */
function SelectBox({ selected, onToggle }: { selected: boolean; onToggle: () => void }) {
  return (
    <div
      onClick={(e) => { e.stopPropagation(); e.preventDefault(); onToggle() }}
      style={{
        position: 'absolute', top: 6, left: 6, zIndex: 5,
        width: 22, height: 22, borderRadius: 4,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: selected ? 'var(--amber)' : 'rgba(0,0,0,0.5)',
        border: `1.5px solid ${selected ? 'var(--amber)' : 'rgba(255,255,255,0.3)'}`,
        cursor: 'pointer', transition: 'all 0.1s',
        backdropFilter: 'blur(4px)',
      }}
    >
      {selected ? <CheckSquare size={13} color="#000" /> : <Square size={13} color="rgba(255,255,255,0.7)" />}
    </div>
  )
}

const PAGE_SIZE = 20

function formatBytes(b: number) {
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / 1024 / 1024).toFixed(1)} MB`
}

function formatDuration(s?: number) {
  if (!s) return '—'
  const m = Math.floor(s / 60)
  const sec = Math.round(s % 60)
  return `${m}m ${sec.toString().padStart(2, '0')}s`
}

// ── Video Player Modal ────────────────────────────────────────────────────────
function VideoPlayerModal({ video, onClose }: { video: VideoMedia; onClose: () => void }) {
  const videoRef = useRef<HTMLVideoElement>(null)

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  // Prevent body scroll while modal is open
  useEffect(() => {
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = '' }
  }, [])

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        background: 'rgba(0,0,0,0.85)',
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        padding: 24,
        backdropFilter: 'blur(4px)',
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      {/* Modal panel */}
      <div style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border-base)',
        borderRadius: 'var(--radius-xl)',
        width: '100%',
        maxWidth: 960,
        maxHeight: '90vh',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        boxShadow: '0 32px 80px rgba(0,0,0,0.6)',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '14px 20px',
          borderBottom: '1px solid var(--border-base)',
          flexShrink: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
            <Film size={16} style={{ color: 'var(--amber)', flexShrink: 0 }} />
            <span style={{
              fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 14,
              color: 'var(--text-primary)', letterSpacing: '0.03em',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {video.filename}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
            {video.download_url && (
              <a
                href={video.download_url}
                download={video.filename}
                className="btn btn-ghost btn-icon btn-sm"
                title="Download"
              >
                <Download size={15} />
              </a>
            )}
            <button className="btn btn-ghost btn-icon btn-sm" onClick={onClose} title="Close (Esc)">
              <X size={15} />
            </button>
          </div>
        </div>

        {/* Video player */}
        <div style={{ background: '#000', flexShrink: 0 }}>
          {video.download_url ? (
            <video
              ref={videoRef}
              controls
              autoPlay
              style={{ width: '100%', maxHeight: '60vh', display: 'block' }}
              src={video.download_url}
            >
              Your browser does not support the video tag.
            </video>
          ) : (
            <div style={{
              height: 320, display: 'flex', alignItems: 'center', justifyContent: 'center',
              flexDirection: 'column', gap: 12, color: 'var(--text-muted)',
            }}>
              <Film size={40} style={{ opacity: 0.3 }} />
              <span style={{ fontSize: 13 }}>No playback URL available</span>
            </div>
          )}
        </div>

        {/* Metadata strip */}
        <div style={{
          padding: '14px 20px',
          display: 'flex', flexWrap: 'wrap', gap: 20,
          borderTop: '1px solid var(--border-base)',
          flexShrink: 0,
        }}>
          {[
            { label: 'Duration',   value: formatDuration(video.duration_seconds) },
            { label: 'Plant',      value: video.plant_site },
            { label: 'Shift',      value: video.shift ?? '—' },
            { label: 'Frames',     value: video.frame_count != null ? video.frame_count.toLocaleString() : '—' },
            { label: 'Size',       value: formatBytes(video.file_size_bytes) },
            { label: 'Recorded',   value: new Date(video.recorded_at).toLocaleString() },
            { label: 'Status',     value: video.status },
          ].map(({ label, value }) => (
            <div key={label}>
              <div style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 2 }}>
                {label}
              </div>
              <div style={{ fontSize: 13, color: 'var(--text-primary)', fontWeight: 500 }}>
                {value}
              </div>
            </div>
          ))}
          {video.tags.length > 0 && (
            <div>
              <div style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>
                Tags
              </div>
              <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                {video.tags.map((t) => (
                  <span key={t.id} className="badge" style={{ background: t.color + '22', color: t.color, borderColor: t.color + '55' }}>
                    {t.name}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Video Card ────────────────────────────────────────────────────────────────
function VideoCard({ vid, onPlay, onDelete, onDetail, selected, onToggleSelect }: {
  vid: VideoMedia
  onPlay: () => void
  onDelete: () => void
  onDetail: () => void
  selected: boolean
  onToggleSelect: () => void
}) {
  return (
    <div className="media-card" style={{ cursor: 'pointer', outline: selected ? '2px solid var(--amber)' : 'none', outlineOffset: -2 }} onClick={onPlay}>
      {/* Thumbnail / preview */}
      <div className="media-thumbnail" style={{ position: 'relative', overflow: 'hidden' }}>
        <SelectBox selected={selected} onToggle={onToggleSelect} />
        {vid.download_url ? (
          <video
            src={vid.download_url + '#t=0.5'}   /* seek to 0.5s for thumbnail */
            preload="metadata"
            muted
            style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
          />
        ) : (
          <Film size={28} style={{ color: 'var(--text-muted)' }} />
        )}
        {/* Play overlay */}
        <div style={{
          position: 'absolute', inset: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: 'rgba(0,0,0,0.35)',
          transition: 'background 0.15s',
        }}
          onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'rgba(0,0,0,0.55)' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'rgba(0,0,0,0.35)' }}
        >
          <div style={{
            width: 36, height: 36, borderRadius: '50%',
            background: 'rgba(255,255,255,0.9)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 2px 12px rgba(0,0,0,0.4)',
          }}>
            <Play size={16} style={{ color: '#111', marginLeft: 2 }} />
          </div>
        </div>
        {/* Duration badge */}
        {vid.duration_seconds && (
          <div style={{
            position: 'absolute', bottom: 6, right: 8,
            fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 700,
            color: '#fff', background: 'rgba(0,0,0,0.65)',
            padding: '2px 5px', borderRadius: 3,
          }}>
            {formatDuration(vid.duration_seconds)}
          </div>
        )}
      </div>

      <div className="media-info">
        <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {vid.filename}
        </div>
        <div className="flex items-center gap-1" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
          <MapPin size={9} />
          <span className="truncate">{vid.plant_site}</span>
        </div>
        {vid.frame_count != null && (
          <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', marginTop: 2 }}>
            <Layers size={9} style={{ display: 'inline', marginRight: 3 }} />
            {vid.frame_count.toLocaleString()} frames
          </div>
        )}
        <div className="flex items-center justify-between mt-2">
          <span className={`badge ${vid.status === 'completed' ? 'badge-success' : 'badge-amber'}`}>
            {vid.status}
          </span>
          <div className="flex items-center gap-1">
            <button
              className="btn btn-ghost btn-icon"
              style={{ padding: 4 }}
              onClick={(e) => { e.stopPropagation(); onDetail() }}
              title="View details"
            >
              <ExternalLink size={12} style={{ color: 'var(--amber)' }} />
            </button>
            <button
              className="btn btn-ghost btn-icon"
              style={{ padding: 4 }}
              onClick={(e) => { e.stopPropagation(); onDelete() }}
              title="Delete video"
            >
              <Trash2 size={12} style={{ color: 'var(--danger)' }} />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Empty state ───────────────────────────────────────────────────────────────
function EmptyState({ tab }: { tab: TabId }) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon">
        {tab === 'images' ? <FileImage size={28} /> : tab === 'videos' ? <Film size={28} /> : <Target size={28} />}
      </div>
      <p style={{ fontFamily: 'var(--font-display)', fontSize: 15, fontWeight: 600, color: 'var(--text-secondary)', letterSpacing: '0.04em', textTransform: 'uppercase' }}>
        No {tab} yet
      </p>
      <p style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 6 }}>
        Upload media to see it here.
      </p>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function MediaLibrary() {
  const navigate = useNavigate()
  const [tab, setTab]               = useState<TabId>('images')
  const [viewMode, setViewMode]     = useState<'grid' | 'list'>('grid')
  const [page, setPage]             = useState(1)
  const [loading, setLoading]       = useState(false)

  const [images, setImages]               = useState<ImageMedia[]>([])
  const [videos, setVideos]               = useState<VideoMedia[]>([])
  const [detections, setDetections]       = useState<DetectionMedia[]>([])
  const [totalImages, setTotalImages]     = useState(0)
  const [totalVideos, setTotalVideos]     = useState(0)
  const [totalDetections, setTotalDetections] = useState(0)

  const [playingVideo, setPlayingVideo]   = useState<VideoMedia | null>(null)
  const [imageModal, setImageModal]       = useState<{ images: ImageItem[]; index: number } | null>(null)

  // Selection & bulk
  const selection = useSelection()
  const [bulkAction, setBulkAction]     = useState<'delete' | 'tag' | 'detect' | null>(null)
  const [bulkLoading, setBulkLoading]   = useState(false)
  const [tagInput, setTagInput]         = useState('')
  const [tagAction, setTagAction]       = useState<'add' | 'remove'>('add')
  const [availableTags, setAvailableTags] = useState<TagResponse[]>([])
  const [selectedTagNames, setSelectedTagNames] = useState<string[]>([])
  const [hazardConfigs, setHazardConfigs] = useState<HazardConfig[]>([])
  const [selectedConfigId, setSelectedConfigId] = useState<number | null>(null)

  // Filters
  const [plantFilter, setPlantFilter] = useState('')
  const [shiftFilter, setShiftFilter] = useState('')

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const params = {
        page,
        page_size: PAGE_SIZE,
        ...(plantFilter ? { plant_site: plantFilter } : {}),
        ...(shiftFilter ? { shift: shiftFilter } : {}),
      }
      if (tab === 'images') {
        const r = await getImages(params)
        setImages(r.data.items)
        setTotalImages(r.data.pagination.total_items)
      } else if (tab === 'videos') {
        const r = await getVideos(params)
        setVideos(r.data.items)
        setTotalVideos(r.data.pagination.total_items)
      } else {
        const r = await getDetections({ page, page_size: PAGE_SIZE })
        setDetections(r.data.items)
        setTotalDetections(r.data.pagination.total_items)
      }
    } catch { /* silent */ }
    finally { setLoading(false) }
  }, [tab, page, plantFilter, shiftFilter])

  useEffect(() => { fetchData() }, [fetchData])

  const total = tab === 'images' ? totalImages : tab === 'videos' ? totalVideos : totalDetections
  const totalPages = Math.ceil(total / PAGE_SIZE)

  const handleDeleteImage = async (id: number) => {
    if (!confirm('Delete this image and all associated data?')) return
    try { await deleteImage(id); fetchData() } catch { /* ignore */ }
  }

  const handleDeleteVideo = async (id: number) => {
    if (!confirm('Delete this video and all associated data?')) return
    try { await deleteVideo(id); fetchData() } catch { /* ignore */ }
  }

  // ── Bulk action handlers ──
  const openBulkAction = async (action: 'delete' | 'tag' | 'detect') => {
    setBulkAction(action)
    if (action === 'tag') {
      try { const r = await getTags(); setAvailableTags(r.data) } catch { /* */ }
      setSelectedTagNames([])
      setTagInput('')
      setTagAction('add')
    }
    if (action === 'detect') {
      try { const r = await getHazardConfigs({ page: 1, page_size: 50, is_active: true }); setHazardConfigs(r.data.items) } catch { /* */ }
      setSelectedConfigId(null)
    }
  }

  const handleBulkDelete = async () => {
    setBulkLoading(true)
    try {
      const ids = Array.from(selection.selectedIds)
      if (tab === 'images') await bulkDeleteImages(ids)
      else if (tab === 'videos') await bulkDeleteVideos(ids)
      else await bulkDeleteDetections(ids)
      selection.deselectAll()
      setBulkAction(null)
      fetchData()
    } catch { /* */ }
    finally { setBulkLoading(false) }
  }

  const handleBulkTag = async () => {
    const names = [...selectedTagNames]
    if (tagInput.trim() && !names.includes(tagInput.trim())) names.push(tagInput.trim())
    if (names.length === 0) return
    setBulkLoading(true)
    try {
      const ids = Array.from(selection.selectedIds)
      if (tab === 'images') await bulkTagImages(ids, names, tagAction)
      else if (tab === 'videos') await bulkTagVideos(ids, names, tagAction)
      else await bulkTagDetections(ids, names, tagAction)
      selection.deselectAll()
      setBulkAction(null)
      fetchData()
    } catch { /* */ }
    finally { setBulkLoading(false) }
  }

  const handleBulkDetect = async () => {
    if (!selectedConfigId) return
    setBulkLoading(true)
    try {
      const ids = Array.from(selection.selectedIds)
      await runDetection(selectedConfigId, { image_ids: ids })
      selection.deselectAll()
      setBulkAction(null)
    } catch { /* */ }
    finally { setBulkLoading(false) }
  }

  const toggleTagName = (name: string) => {
    setSelectedTagNames(prev =>
      prev.includes(name) ? prev.filter(n => n !== name) : [...prev, name]
    )
  }

  const buildImageItems = (imgs: ImageMedia[]): ImageItem[] =>
    imgs.filter(img => img.download_url).map(img => ({
      url: img.download_url!,
      filename: img.filename,
      subtitle: `${img.width}×${img.height} · ${img.plant_site}`,
      badge: 'IMAGE',
      badgeColor: 'var(--cyan-400)',
      detailUrl: `/media/images/${img.id}`,
      meta: [
        { label: 'Plant Site', value: img.plant_site },
        { label: 'Shift', value: img.shift ?? '—' },
        { label: 'Dimensions', value: `${img.width}×${img.height}` },
        { label: 'Size', value: formatBytes(img.file_size_bytes) },
        { label: 'Status', value: img.status },
        { label: 'Captured', value: new Date(img.captured_at).toLocaleString() },
      ],
    }))

  const openImageModal = (img: ImageMedia) => {
    if (!img.download_url) return
    const items = buildImageItems(images)
    const idx = items.findIndex(it => it.url === img.download_url)
    setImageModal({ images: items, index: idx >= 0 ? idx : 0 })
  }

  const getDetCropUrl = (det: DetectionMedia): string | null =>
    det.crop_url || (det.storage_key ? `/api/v1/media/files/${det.storage_key}` : null)

  const buildDetectionItems = (dets: DetectionMedia[]): ImageItem[] =>
    dets.map(det => {
      const url = getDetCropUrl(det)
      if (!url) return null
      return {
        url,
        filename: det.label,
        subtitle: `${Math.round(det.confidence * 100)}% confidence · Image #${det.image_id}`,
        badge: 'DETECTION',
        badgeColor: 'var(--danger)',
        detailUrl: `/media/detections/${det.id}`,
        meta: [
          { label: 'Label', value: det.label },
          { label: 'Confidence', value: `${Math.round(det.confidence * 100)}%` },
          { label: 'BBox', value: `${det.bbox_x.toFixed(2)},${det.bbox_y.toFixed(2)} ${det.bbox_width.toFixed(2)}×${det.bbox_height.toFixed(2)}` },
          { label: 'Format', value: det.bbox_format },
          { label: 'Image', value: `#${det.image_id}` },
          { label: 'Created', value: new Date(det.created_at).toLocaleString() },
        ],
      } as ImageItem
    }).filter((x): x is ImageItem => x !== null)

  const openDetectionModal = (det: DetectionMedia) => {
    const url = getDetCropUrl(det)
    if (!url) return
    const items = buildDetectionItems(detections)
    const idx = items.findIndex(it => it.url === url)
    if (items.length === 0) return
    setImageModal({ images: items, index: idx >= 0 ? idx : 0 })
  }

  const items = tab === 'images' ? images : tab === 'videos' ? videos : detections

  return (
    <div className="page-container">
      {/* Video player modal */}
      {playingVideo && (
        <VideoPlayerModal video={playingVideo} onClose={() => setPlayingVideo(null)} />
      )}

      {/* Image lightbox modal */}
      {imageModal && (
        <ImageModal
          images={imageModal.images}
          initialIndex={imageModal.index}
          onClose={() => setImageModal(null)}
        />
      )}

      {/* Header */}
      <div className="page-header flex items-center justify-between">
        <div>
          <h1 className="page-title">Media Vault</h1>
          <p className="page-subtitle">
            {(totalImages || 0).toLocaleString()} images · {(totalVideos || 0).toLocaleString()} videos · {(totalDetections || 0).toLocaleString()} detections
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            className="btn btn-secondary btn-sm"
            onClick={async () => {
              try {
                const r = await (tab === 'detections' ? exportDetections({ format: 'csv' }) : exportMedia({ format: 'csv' }))
                const blob = new Blob([r.data])
                const url = URL.createObjectURL(blob)
                const a = document.createElement('a')
                a.href = url
                a.download = `${tab}_export.csv`
                a.click()
                URL.revokeObjectURL(url)
              } catch { /* ignore */ }
            }}
            title="Export as CSV"
          >
            <Download size={13} /> Export
          </button>
          <button className="btn btn-ghost btn-icon btn-sm" onClick={fetchData} title="Refresh">
            <RefreshCw size={15} style={loading ? { animation: 'spin 1s linear infinite' } : {}} />
          </button>
        </div>
      </div>

      {/* Toolbar */}
      <div className="flex items-center justify-between mb-4" style={{ marginBottom: 16 }}>
        <div className="tab-bar" style={{ marginBottom: 0, borderBottom: 'none' }}>
          {([
            { id: 'images' as TabId, icon: Image, label: 'Images', count: totalImages },
            { id: 'videos' as TabId, icon: Video, label: 'Videos', count: totalVideos },
            { id: 'detections' as TabId, icon: Target, label: 'Detections', count: totalDetections },
          ]).map(({ id, icon: Icon, label, count }) => (
            <button
              key={id}
              className={`tab-btn${tab === id ? ' active' : ''}`}
              onClick={() => { setTab(id); setPage(1); selection.deselectAll() }}
            >
              <Icon size={13} />
              {label}
              {count > 0 && (
                <span style={{
                  fontSize: 10, fontFamily: 'var(--font-mono)',
                  background: tab === id ? 'var(--amber-glow)' : 'var(--bg-muted)',
                  color: tab === id ? 'var(--amber)' : 'var(--text-muted)',
                  borderRadius: 3, padding: '1px 5px',
                }}>
                  {count}
                </span>
              )}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <input
            type="text"
            className="form-input"
            placeholder="Filter by plant..."
            value={plantFilter}
            onChange={(e) => { setPlantFilter(e.target.value); setPage(1) }}
            style={{ width: 160, height: 34, padding: '0 12px', fontSize: 13 }}
          />
          <select
            className="form-input form-select"
            value={shiftFilter}
            onChange={(e) => { setShiftFilter(e.target.value); setPage(1) }}
            style={{ width: 130, height: 34, padding: '0 32px 0 10px', fontSize: 13 }}
          >
            <option value="">Any shift</option>
            <option value="morning">Morning</option>
            <option value="afternoon">Afternoon</option>
            <option value="night">Night</option>
          </select>
          <div className="flex items-center" style={{ gap: 2 }}>
            <button
              className={`btn btn-icon btn-sm ${viewMode === 'grid' ? 'btn-secondary' : 'btn-ghost'}`}
              onClick={() => setViewMode('grid')}
            >
              <LayoutGrid size={14} />
            </button>
            <button
              className={`btn btn-icon btn-sm ${viewMode === 'list' ? 'btn-secondary' : 'btn-ghost'}`}
              onClick={() => setViewMode('list')}
            >
              <List size={14} />
            </button>
          </div>
        </div>
      </div>

      {/* Select all bar */}
      {items.length > 0 && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8,
          padding: '6px 12px',
          background: selection.count > 0 ? 'var(--amber-glow)' : 'transparent',
          border: selection.count > 0 ? '1px solid var(--border-amber)' : '1px solid transparent',
          borderRadius: 'var(--radius-md)',
          transition: 'all 0.15s',
        }}>
          <div
            onClick={() => {
              if (selection.isAllSelected(items as { id: number }[])) selection.deselectAll()
              else selection.selectAll(items as { id: number }[])
            }}
            style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}
          >
            {selection.isAllSelected(items as { id: number }[])
              ? <CheckSquare size={15} style={{ color: 'var(--amber)' }} />
              : selection.count > 0
                ? <CheckSquare size={15} style={{ color: 'var(--amber)', opacity: 0.5 }} />
                : <Square size={15} style={{ color: 'var(--text-muted)' }} />
            }
            <span style={{ fontSize: 12, fontFamily: 'var(--font-display)', fontWeight: 600, color: selection.count > 0 ? 'var(--amber)' : 'var(--text-muted)', letterSpacing: '0.04em' }}>
              {selection.count > 0 ? `${selection.count} selected` : 'Select all'}
            </span>
          </div>
        </div>
      )}

      {/* Content */}
      {loading ? (
        <div className="flex items-center justify-center" style={{ padding: '60px 0' }}>
          <div className="spinner spinner-lg" />
        </div>
      ) : items.length === 0 ? (
        <EmptyState tab={tab} />
      ) : viewMode === 'grid' ? (
        <div className="media-grid">
          {tab === 'images' && (images as ImageMedia[]).map((img) => (
            <div
              key={img.id}
              className="media-card"
              onClick={() => openImageModal(img)}
              style={{ cursor: img.download_url ? 'pointer' : 'default', outline: selection.isSelected(img.id) ? '2px solid var(--amber)' : 'none', outlineOffset: -2 }}
            >
              <div className="media-thumbnail" style={{ position: 'relative' }}>
                <SelectBox selected={selection.isSelected(img.id)} onToggle={() => selection.toggle(img.id)} />
                {img.download_url
                  ? <img src={img.download_url} alt={img.filename} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                  : <Image size={28} />
                }
              </div>
              <div className="media-info">
                <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {img.filename}
                </div>
                <div className="flex items-center gap-1" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  <MapPin size={9} />
                  <span className="truncate">{img.plant_site}</span>
                </div>
                <div className="flex items-center justify-between mt-2">
                  <span className={`badge ${img.status === 'completed' ? 'badge-success' : 'badge-amber'}`}>
                    {img.status}
                  </span>
                  <div className="flex items-center gap-1">
                    <button
                      className="btn btn-ghost btn-icon"
                      style={{ padding: 4 }}
                      onClick={(e) => { e.stopPropagation(); navigate(`/media/images/${img.id}`) }}
                      title="View details"
                    >
                      <ExternalLink size={12} style={{ color: 'var(--amber)' }} />
                    </button>
                    <button
                      className="btn btn-ghost btn-icon"
                      style={{ padding: 4 }}
                      onClick={(e) => { e.stopPropagation(); handleDeleteImage(img.id) }}
                    >
                      <Trash2 size={12} style={{ color: 'var(--danger)' }} />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ))}

          {tab === 'videos' && (videos as VideoMedia[]).map((vid) => (
            <VideoCard
              key={vid.id}
              vid={vid}
              onPlay={() => setPlayingVideo(vid)}
              onDelete={() => handleDeleteVideo(vid.id)}
              onDetail={() => navigate(`/media/videos/${vid.id}`)}
              selected={selection.isSelected(vid.id)}
              onToggleSelect={() => selection.toggle(vid.id)}
            />
          ))}

          {tab === 'detections' && (detections as DetectionMedia[]).map((det) => {
            const cropUrl = getDetCropUrl(det)
            return (
              <div
                key={det.id}
                className="media-card"
                onClick={() => openDetectionModal(det)}
                style={{ cursor: cropUrl ? 'pointer' : 'default', outline: selection.isSelected(det.id) ? '2px solid var(--amber)' : 'none', outlineOffset: -2 }}
              >
                <div className="media-thumbnail" style={{ position: 'relative' }}>
                  <SelectBox selected={selection.isSelected(det.id)} onToggle={() => selection.toggle(det.id)} />
                  {cropUrl ? (
                    <img
                      src={cropUrl}
                      alt={det.label}
                      style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                      onError={(e) => {
                        const img = e.target as HTMLImageElement
                        img.style.display = 'none'
                        const fallback = img.nextElementSibling as HTMLElement | null
                        if (fallback) fallback.style.display = 'flex'
                      }}
                    />
                  ) : null}
                  <div style={{
                    display: cropUrl ? 'none' : 'flex',
                    width: '100%', height: '100%',
                    alignItems: 'center', justifyContent: 'center',
                    background: 'var(--bg-muted)',
                  }}>
                    <Target size={28} style={{ color: 'var(--text-muted)' }} />
                  </div>
                  {/* Confidence overlay */}
                  <div style={{
                    position: 'absolute', top: 6, right: 6,
                    padding: '2px 6px', borderRadius: 4,
                    background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)',
                    fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700,
                    color: det.confidence >= 0.8 ? 'var(--success)' : det.confidence >= 0.5 ? 'var(--amber)' : 'var(--danger)',
                  }}>
                    {Math.round(det.confidence * 100)}%
                  </div>
                </div>
                <div className="media-info">
                  <div className="flex items-center justify-between" style={{ marginBottom: 4 }}>
                    <span className="badge badge-danger">{det.label}</span>
                    <span className={`badge ${det.embedding_generated ? 'badge-success' : 'badge-muted'}`} style={{ fontSize: 9 }}>
                      {det.embedding_generated ? 'Embedded' : 'Pending'}
                    </span>
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                    Image #{det.image_id}
                  </div>
                  <div className="flex items-center justify-between mt-2">
                    <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                      {det.bbox_width.toFixed(2)} × {det.bbox_height.toFixed(2)}
                    </div>
                    <button
                      className="btn btn-ghost btn-icon"
                      style={{ padding: 4 }}
                      onClick={(e) => { e.stopPropagation(); navigate(`/media/detections/${det.id}`) }}
                      title="View details"
                    >
                      <ExternalLink size={12} style={{ color: 'var(--amber)' }} />
                    </button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        /* List view */
        <div className="table-wrapper">
          {tab === 'images' && (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Filename</th>
                  <th>Plant Site</th>
                  <th>Shift</th>
                  <th>Dimensions</th>
                  <th>Size</th>
                  <th>Status</th>
                  <th>Captured</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {(images as ImageMedia[]).map((img) => (
                  <tr
                    key={img.id}
                    style={{ cursor: img.download_url ? 'pointer' : 'default' }}
                    onClick={() => openImageModal(img)}
                  >
                    <td style={{ fontWeight: 500, color: 'var(--text-primary)', maxWidth: 200 }}>
                      <span className="truncate" style={{ display: 'block' }}>{img.filename}</span>
                    </td>
                    <td>{img.plant_site}</td>
                    <td>{img.shift ?? '—'}</td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{img.width}×{img.height}</td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{formatBytes(img.file_size_bytes)}</td>
                    <td><span className={`badge ${img.status === 'completed' ? 'badge-success' : 'badge-amber'}`}>{img.status}</span></td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>{new Date(img.captured_at).toLocaleDateString()}</td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <button className="btn btn-ghost btn-icon btn-sm" onClick={() => handleDeleteImage(img.id)}>
                        <Trash2 size={13} style={{ color: 'var(--danger)' }} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {tab === 'videos' && (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Preview</th>
                  <th>Filename</th>
                  <th>Plant Site</th>
                  <th>Shift</th>
                  <th>Duration</th>
                  <th>Frames</th>
                  <th>Size</th>
                  <th>Status</th>
                  <th>Recorded</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {(videos as VideoMedia[]).map((vid) => (
                  <tr
                    key={vid.id}
                    style={{ cursor: 'pointer' }}
                    onClick={() => setPlayingVideo(vid)}
                  >
                    <td style={{ width: 72, padding: '6px 8px' }}>
                      <div style={{
                        width: 60, height: 40, borderRadius: 'var(--radius-md)',
                        overflow: 'hidden', position: 'relative',
                        background: 'var(--bg-muted)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        flexShrink: 0,
                      }}>
                        {vid.download_url ? (
                          <>
                            <video
                              src={vid.download_url + '#t=0.5'}
                              preload="metadata"
                              muted
                              style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                            />
                            <div style={{
                              position: 'absolute', inset: 0,
                              display: 'flex', alignItems: 'center', justifyContent: 'center',
                              background: 'rgba(0,0,0,0.3)',
                            }}>
                              <Play size={12} style={{ color: '#fff', marginLeft: 1 }} />
                            </div>
                          </>
                        ) : (
                          <Film size={16} style={{ color: 'var(--text-muted)' }} />
                        )}
                      </div>
                    </td>
                    <td style={{ fontWeight: 500, color: 'var(--text-primary)', maxWidth: 200 }}>
                      <span className="truncate" style={{ display: 'block' }}>{vid.filename}</span>
                    </td>
                    <td>{vid.plant_site}</td>
                    <td>{vid.shift ?? '—'}</td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                      {formatDuration(vid.duration_seconds)}
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                      {vid.frame_count != null ? vid.frame_count.toLocaleString() : '—'}
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{formatBytes(vid.file_size_bytes)}</td>
                    <td>
                      <span className={`badge ${vid.status === 'completed' ? 'badge-success' : 'badge-amber'}`}>
                        {vid.status}
                      </span>
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>{new Date(vid.recorded_at).toLocaleDateString()}</td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <button className="btn btn-ghost btn-icon btn-sm" onClick={() => handleDeleteVideo(vid.id)}>
                        <Trash2 size={13} style={{ color: 'var(--danger)' }} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {tab === 'detections' && (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Crop</th>
                  <th>Label</th>
                  <th>Confidence</th>
                  <th>Image ID</th>
                  <th>BBox</th>
                  <th>Embedded</th>
                  <th>Created</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {(detections as DetectionMedia[]).map((det) => {
                  const cropUrl = getDetCropUrl(det)
                  return (
                    <tr key={det.id} onClick={() => openDetectionModal(det)} style={{ cursor: cropUrl ? 'pointer' : 'default' }}>
                      <td>
                        <div style={{
                          width: 48, height: 36, borderRadius: 'var(--radius-sm)',
                          overflow: 'hidden', background: 'var(--bg-muted)',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          border: '1px solid var(--border-dim)',
                        }}>
                          {cropUrl ? (
                            <img src={cropUrl} alt={det.label} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                          ) : (
                            <Target size={14} style={{ color: 'var(--text-muted)' }} />
                          )}
                        </div>
                      </td>
                      <td><span className="badge badge-danger">{det.label}</span></td>
                      <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--amber)' }}>
                        {Math.round(det.confidence * 100)}%
                      </td>
                      <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>#{det.image_id}</td>
                      <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>
                        {det.bbox_x.toFixed(2)},{det.bbox_y.toFixed(2)} {det.bbox_width.toFixed(2)}×{det.bbox_height.toFixed(2)}
                      </td>
                      <td>
                        <span className={`badge ${det.embedding_generated ? 'badge-success' : 'badge-muted'}`}>
                          {det.embedding_generated ? 'Yes' : 'Pending'}
                        </span>
                      </td>
                      <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>{new Date(det.created_at).toLocaleDateString()}</td>
                      <td onClick={(e) => e.stopPropagation()}>
                        <button
                          className="btn btn-ghost btn-icon"
                          style={{ padding: 4 }}
                          onClick={() => navigate(`/media/detections/${det.id}`)}
                          title="View details"
                        >
                          <ExternalLink size={12} style={{ color: 'var(--amber)' }} />
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="pagination">
          <button
            className="page-btn"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
          >
            <ChevronLeft size={14} />
          </button>
          {Array.from({ length: Math.min(7, totalPages) }, (_, i) => {
            const p = i + 1
            return (
              <button
                key={p}
                className={`page-btn${page === p ? ' active' : ''}`}
                onClick={() => setPage(p)}
              >
                {p}
              </button>
            )
          })}
          {totalPages > 7 && (
            <>
              <span style={{ color: 'var(--text-muted)', padding: '0 4px' }}>...</span>
              <button
                className={`page-btn${page === totalPages ? ' active' : ''}`}
                onClick={() => setPage(totalPages)}
              >
                {totalPages}
              </button>
            </>
          )}
          <button
            className="page-btn"
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
          >
            <ChevronRight size={14} />
          </button>
        </div>
      )}

      {/* ── Bulk Action Bar ── */}
      {selection.count > 0 && (
        <BulkActionBar
          count={selection.count}
          tab={tab}
          onDelete={() => openBulkAction('delete')}
          onTag={() => openBulkAction('tag')}
          onRunDetection={tab === 'images' ? () => openBulkAction('detect') : undefined}
          onDeselectAll={selection.deselectAll}
        />
      )}

      {/* ── Bulk Delete Confirm ── */}
      <ConfirmModal
        open={bulkAction === 'delete'}
        title={`Delete ${selection.count} ${tab}?`}
        description={`This will permanently delete ${selection.count} ${tab} and all associated data. This action cannot be undone.`}
        confirmLabel={`Delete ${selection.count} ${tab}`}
        confirmVariant="danger"
        loading={bulkLoading}
        onConfirm={handleBulkDelete}
        onCancel={() => setBulkAction(null)}
      />

      {/* ── Bulk Tag Modal ── */}
      {bulkAction === 'tag' && (
        <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) setBulkAction(null) }}>
          <div className="modal" style={{ maxWidth: 440 }}>
            <div className="modal-title">
              {tagAction === 'add' ? 'Add' : 'Remove'} Tags — {selection.count} {tab}
            </div>

            <div className="flex items-center gap-2 mb-4">
              {(['add', 'remove'] as const).map(a => (
                <button
                  key={a}
                  className={`btn btn-sm ${tagAction === a ? 'btn-primary' : 'btn-ghost'}`}
                  onClick={() => setTagAction(a)}
                >
                  {a === 'add' ? 'Add Tags' : 'Remove Tags'}
                </button>
              ))}
            </div>

            {availableTags.length > 0 && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 12 }}>
                {availableTags.map(tag => {
                  const active = selectedTagNames.includes(tag.name)
                  return (
                    <button
                      key={tag.id}
                      type="button"
                      onClick={() => toggleTagName(tag.name)}
                      style={{
                        padding: '4px 10px', borderRadius: 'var(--radius-full)',
                        fontSize: 11, fontFamily: 'var(--font-mono)', fontWeight: 500, cursor: 'pointer',
                        border: active ? `1.5px solid ${tag.color}` : '1.5px solid var(--border-dim)',
                        background: active ? `${tag.color}18` : 'transparent',
                        color: active ? tag.color : 'var(--text-muted)',
                        transition: 'all 0.1s',
                      }}
                    >
                      {tag.name}
                    </button>
                  )
                })}
              </div>
            )}

            <div className="form-group" style={{ marginBottom: 16 }}>
              <label className="form-label">Or type a new tag</label>
              <input
                type="text"
                className="form-input"
                placeholder="Tag name"
                value={tagInput}
                onChange={(e) => setTagInput(e.target.value)}
              />
            </div>

            <div className="flex justify-end gap-3">
              <button className="btn btn-ghost" onClick={() => setBulkAction(null)} disabled={bulkLoading}>Cancel</button>
              <button
                className="btn btn-primary"
                onClick={handleBulkTag}
                disabled={bulkLoading || (selectedTagNames.length === 0 && !tagInput.trim())}
              >
                {bulkLoading ? 'Applying...' : `${tagAction === 'add' ? 'Add' : 'Remove'} Tags`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Bulk Detect Modal ── */}
      {bulkAction === 'detect' && (
        <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) setBulkAction(null) }}>
          <div className="modal" style={{ maxWidth: 440 }}>
            <div className="modal-title">
              Run Hazard Detection — {selection.count} images
            </div>
            <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 16 }}>
              Select a detection profile to run on the selected images.
            </p>

            {hazardConfigs.length === 0 ? (
              <div style={{ padding: '20px 0', textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
                No active detection profiles found.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
                {hazardConfigs.map(cfg => (
                  <div
                    key={cfg.id}
                    onClick={() => setSelectedConfigId(cfg.id)}
                    style={{
                      padding: '10px 14px',
                      borderRadius: 'var(--radius-md)',
                      border: selectedConfigId === cfg.id ? '2px solid var(--amber)' : '1px solid var(--border-dim)',
                      background: selectedConfigId === cfg.id ? 'var(--amber-glow)' : 'var(--bg-elevated)',
                      cursor: 'pointer', transition: 'all 0.1s',
                    }}
                  >
                    <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-primary)', marginBottom: 4 }}>
                      {cfg.name}
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                      {cfg.prompts.slice(0, 5).map((p, i) => (
                        <span key={i} style={{
                          fontSize: 10, fontFamily: 'var(--font-mono)', padding: '2px 6px', borderRadius: 3,
                          background: 'var(--bg-muted)', border: '1px solid var(--border-dim)', color: 'var(--text-muted)',
                        }}>
                          {p}
                        </span>
                      ))}
                      {cfg.prompts.length > 5 && (
                        <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                          +{cfg.prompts.length - 5}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}

            <div className="flex justify-end gap-3">
              <button className="btn btn-ghost" onClick={() => setBulkAction(null)} disabled={bulkLoading}>Cancel</button>
              <button
                className="btn btn-primary"
                onClick={handleBulkDetect}
                disabled={bulkLoading || !selectedConfigId}
              >
                {bulkLoading ? 'Queuing...' : `Run Detection on ${selection.count} Images`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Bottom spacer when bulk bar is visible */}
      {selection.count > 0 && <div style={{ height: 72 }} />}
    </div>
  )
}
