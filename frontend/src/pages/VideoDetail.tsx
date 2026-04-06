import { useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import {
  ArrowLeft, Video, MapPin, Clock, Tag, Layers,
  Image as ImageIcon, Target, AlertCircle, Loader2,
  ChevronLeft, ChevronRight,
} from 'lucide-react'
import { getVideo, getImages } from '../api/client'
import type { VideoMedia, ImageMedia } from '../types/api'

function MetaRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between" style={{
      padding: '8px 12px', background: 'var(--bg-elevated)',
      border: '1px solid var(--border-dim)', borderRadius: 'var(--radius-md)',
    }}>
      <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-display)', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
        {label}
      </span>
      <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
        {children}
      </span>
    </div>
  )
}

export default function VideoDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [video, setVideo] = useState<VideoMedia | null>(null)
  const [frames, setFrames] = useState<ImageMedia[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [framePage, setFramePage] = useState(1)
  const FRAME_PAGE_SIZE = 12

  useEffect(() => {
    if (!id) return
    setLoading(true)
    getVideo(parseInt(id))
      .then(res => setVideo(res.data))
      .catch(() => setError('Failed to load video.'))
      .finally(() => setLoading(false))
  }, [id])

  useEffect(() => {
    if (!id) return
    // Fetch frames (images linked to this video)
    getImages({ page: framePage, page_size: FRAME_PAGE_SIZE })
      .then(res => {
        // Filter frames belonging to this video
        const videoFrames = res.data.items.filter(img => String(img.video_id) === id)
        setFrames(videoFrames)
      })
      .catch(() => {})
  }, [id, framePage])

  if (loading) {
    return (
      <div className="page-container">
        <div className="flex items-center justify-center" style={{ padding: '80px 0' }}>
          <Loader2 size={24} style={{ animation: 'spin 0.8s linear infinite', color: 'var(--amber)' }} />
        </div>
      </div>
    )
  }

  if (error || !video) {
    return (
      <div className="page-container">
        <div className="alert alert-error">
          <AlertCircle size={14} />
          <span>{error || 'Video not found.'}</span>
        </div>
        <button className="btn btn-ghost mt-4" onClick={() => navigate('/media')}>
          <ArrowLeft size={14} /> Back to Media
        </button>
      </div>
    )
  }

  const vidUrl = video.download_url || (video.storage_key ? `/api/v1/media/files/${video.storage_key}` : null)

  return (
    <div className="page-container">
      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <button className="btn btn-ghost btn-sm" onClick={() => navigate(-1)} style={{ marginBottom: 12 }}>
          <ArrowLeft size={14} /> Back
        </button>
        <h1 className="page-title" style={{ fontSize: 20 }}>{video.filename}</h1>
        <p className="page-subtitle">Video detail, extracted frames, and detections</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 24, alignItems: 'start' }}>
        {/* Left: Video + frames */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          {/* Video player */}
          <div className="card anim-1" style={{ padding: 0, overflow: 'hidden' }}>
            {vidUrl ? (
              <video
                src={vidUrl}
                controls
                style={{ width: '100%', maxHeight: 480, background: '#000' }}
              />
            ) : (
              <div style={{ height: 300, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg-muted)' }}>
                <Video size={48} style={{ color: 'var(--text-muted)' }} />
              </div>
            )}
          </div>

          {/* Extracted frames */}
          <div className="card anim-2">
            <div className="card-header">
              <span className="card-title flex items-center gap-2">
                <ImageIcon size={12} />
                Extracted Frames
                {video.frame_count != null && (
                  <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', background: 'var(--bg-muted)', color: 'var(--text-muted)', borderRadius: 3, padding: '1px 5px' }}>
                    {video.frame_count}
                  </span>
                )}
              </span>
            </div>

            {frames.length === 0 ? (
              <div className="empty-state" style={{ padding: '32px 20px' }}>
                <div className="empty-state-icon"><ImageIcon size={20} /></div>
                <p style={{ color: 'var(--text-muted)', fontSize: 12 }}>No frames extracted yet or frames loading.</p>
              </div>
            ) : (
              <>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 10 }}>
                  {frames.map(frame => {
                    const frameUrl = frame.download_url || (frame.storage_key ? `/api/v1/media/files/${frame.storage_key}` : null)
                    return (
                      <Link
                        key={frame.id}
                        to={`/media/images/${frame.id}`}
                        style={{
                          textDecoration: 'none', borderRadius: 'var(--radius-md)',
                          border: '1px solid var(--border-dim)', overflow: 'hidden',
                          background: 'var(--bg-elevated)',
                        }}
                      >
                        <div style={{ height: 90, background: 'var(--bg-muted)', overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                          {frameUrl ? (
                            <img src={frameUrl} alt={frame.filename} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                          ) : (
                            <ImageIcon size={18} style={{ color: 'var(--text-muted)' }} />
                          )}
                        </div>
                        <div style={{ padding: '6px 8px' }}>
                          <div style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                            {frame.frame_number != null ? `Frame #${frame.frame_number}` : frame.filename}
                          </div>
                          <span className={`badge ${frame.status === 'completed' ? 'badge-success' : 'badge-amber'}`} style={{ fontSize: 9, marginTop: 4 }}>
                            {frame.status}
                          </span>
                        </div>
                      </Link>
                    )
                  })}
                </div>
                <div className="flex items-center justify-center gap-2 mt-4">
                  <button className="btn btn-ghost btn-sm" disabled={framePage <= 1} onClick={() => setFramePage(p => p - 1)}>
                    <ChevronLeft size={12} />
                  </button>
                  <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>Page {framePage}</span>
                  <button className="btn btn-ghost btn-sm" disabled={frames.length < FRAME_PAGE_SIZE} onClick={() => setFramePage(p => p + 1)}>
                    <ChevronRight size={12} />
                  </button>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Right: Metadata sidebar */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="card anim-1">
            <div className="card-header">
              <span className="card-title flex items-center gap-2">
                <Video size={12} />
                Metadata
              </span>
              <span className={`badge ${video.status === 'completed' ? 'badge-success' : video.status === 'processing' ? 'badge-amber' : 'badge-muted'}`}>
                {video.status}
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {video.duration_seconds != null && <MetaRow label="Duration">{video.duration_seconds.toFixed(1)}s</MetaRow>}
              <MetaRow label="Size">{(video.file_size_bytes / 1024 / 1024).toFixed(2)} MB</MetaRow>
              <MetaRow label="Frames">{video.frame_count ?? 0}</MetaRow>
              <MetaRow label="Plant Site">{video.plant_site}</MetaRow>
              {video.shift && <MetaRow label="Shift">{video.shift}</MetaRow>}
              {video.inspection_line && <MetaRow label="Line">{video.inspection_line}</MetaRow>}
              <MetaRow label="Recorded">{new Date(video.recorded_at).toLocaleString()}</MetaRow>
              <MetaRow label="Uploaded">{new Date(video.created_at).toLocaleString()}</MetaRow>
            </div>
          </div>

          {/* Tags */}
          {video.tags && video.tags.length > 0 && (
            <div className="card anim-2">
              <div className="card-header">
                <span className="card-title flex items-center gap-2">
                  <Tag size={12} />
                  Tags
                </span>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {video.tags.map(tag => (
                  <span
                    key={tag.id}
                    style={{
                      fontSize: 11, fontFamily: 'var(--font-mono)', padding: '3px 8px', borderRadius: 4,
                      background: `${tag.color}18`, border: `1px solid ${tag.color}40`, color: tag.color,
                    }}
                  >
                    {tag.name}
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
