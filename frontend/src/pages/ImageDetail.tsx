import { useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import {
  ArrowLeft, Image as ImageIcon, MapPin, Clock, Tag, Layers,
  Target, Video, AlertCircle, Search, Loader2, Plus, PenTool, Columns2,
} from 'lucide-react'
import { getImage, getDetections } from '../api/client'
import type { ImageMedia, DetectionMedia } from '../types/api'
import { useCompare } from '../context/CompareContext'
import AnnotationCanvas from '../components/AnnotationCanvas'
import CommentThread from '../components/CommentThread'

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

function CompareButton({ image, imgUrl }: { image: ImageMedia | null; imgUrl: string | null }) {
  const { addItem, isInTray } = useCompare()
  if (!image) return null
  const inTray = isInTray(image.id)
  return (
    <button
      className={`btn ${inTray ? 'btn-primary' : 'btn-secondary'} btn-sm`}
      style={{ justifyContent: 'center', width: '100%' }}
      disabled={inTray}
      onClick={() => addItem({
        id: image.id, type: 'image', url: imgUrl ?? '',
        label: image.filename, plant_site: image.plant_site ?? '',
        captured_at: image.captured_at ?? '',
      })}
    >
      <Columns2 size={12} /> {inTray ? 'In Compare Tray' : 'Add to Compare'}
    </button>
  )
}

export default function ImageDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [image, setImage] = useState<ImageMedia | null>(null)
  const [detections, setDetections] = useState<DetectionMedia[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [annotating, setAnnotating] = useState(false)

  const fetchData = (showLoader = true) => {
    if (!id) return
    if (showLoader) setLoading(true)
    Promise.all([
      getImage(parseInt(id)),
      getDetections({ page: 1, page_size: 100 }),
    ])
      .then(([imgRes, detRes]) => {
        setImage(imgRes.data)
        const imgDetections = detRes.data.items.filter(d => d.image_id === parseInt(id!))
        setDetections(imgDetections)
      })
      .catch(() => setError('Failed to load image.'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchData() }, [id])

  if (loading) {
    return (
      <div className="page-container">
        <div className="flex items-center justify-center" style={{ padding: '80px 0' }}>
          <Loader2 size={24} style={{ animation: 'spin 0.8s linear infinite', color: 'var(--amber)' }} />
        </div>
      </div>
    )
  }

  if (error || !image) {
    return (
      <div className="page-container">
        <div className="alert alert-error">
          <AlertCircle size={14} />
          <span>{error || 'Image not found.'}</span>
        </div>
        <button className="btn btn-ghost mt-4" onClick={() => navigate('/media')}>
          <ArrowLeft size={14} /> Back to Media
        </button>
      </div>
    )
  }

  const imgUrl = image.download_url || (image.storage_key ? `/api/v1/media/files/${image.storage_key}` : null)

  return (
    <div className="page-container">
      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => navigate(-1)}
          style={{ marginBottom: 12 }}
        >
          <ArrowLeft size={14} /> Back
        </button>
        <h1 className="page-title" style={{ fontSize: 20 }}>{image.filename}</h1>
        <p className="page-subtitle">Image detail and associated detections</p>
      </div>

      {/* Annotation mode — full width */}
      {annotating && imgUrl && (
        <div style={{ animation: 'fadeUp 0.25s ease-out' }}>
          <AnnotationCanvas
            imageUrl={imgUrl}
            imageId={image.id}
            imageWidth={image.width}
            imageHeight={image.height}
            onDone={() => {
              setAnnotating(false)
              fetchData(false)
            }}
            onCancel={() => setAnnotating(false)}
          />
        </div>
      )}

      {/* Normal mode — grid layout */}
      {!annotating && (
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 24, alignItems: 'start' }}>
        {/* Left: Image viewer + detections */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          {/* Image */}
          <div className="card anim-1" style={{ padding: 0, overflow: 'hidden' }}>
            {imgUrl ? (
              <img
                src={imgUrl}
                alt={image.filename}
                style={{ width: '100%', height: 'auto', display: 'block', maxHeight: 600, objectFit: 'contain', background: '#000' }}
              />
            ) : (
              <div style={{ height: 300, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg-muted)' }}>
                <ImageIcon size={48} style={{ color: 'var(--text-muted)' }} />
              </div>
            )}
          </div>

          {/* Detections on this image */}
          <div className="card anim-2">
            <div className="card-header">
              <span className="card-title flex items-center gap-2">
                <Target size={12} />
                Detections
                <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', background: 'var(--bg-muted)', color: 'var(--text-muted)', borderRadius: 3, padding: '1px 5px' }}>
                  {detections.length}
                </span>
              </span>
              <div className="flex items-center gap-2">
                <button
                  className="btn btn-primary btn-sm"
                  onClick={() => setAnnotating(true)}
                >
                  <PenTool size={12} /> Annotate
                </button>
                <Link to={`/search`} className="btn btn-ghost btn-sm" style={{ textDecoration: 'none' }}>
                  <Search size={12} /> Find Similar
                </Link>
              </div>
            </div>

            {detections.length === 0 ? (
              <div className="empty-state" style={{ padding: '32px 20px' }}>
                <div className="empty-state-icon"><Target size={20} /></div>
                <p style={{ color: 'var(--text-muted)', fontSize: 12, marginBottom: 8 }}>No detections found for this image.</p>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={() => setAnnotating(true)}
                >
                  <PenTool size={12} /> Add Detections
                </button>
              </div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 10 }}>
                {detections.map(det => {
                  const cropUrl = det.storage_key ? `/api/v1/media/files/${det.storage_key}` : null
                  return (
                    <Link
                      key={det.id}
                      to={`/media/detections/${det.id}`}
                      style={{
                        textDecoration: 'none', borderRadius: 'var(--radius-md)',
                        border: '1px solid var(--border-dim)', overflow: 'hidden',
                        background: 'var(--bg-elevated)', transition: 'all var(--transition-fast)',
                      }}
                    >
                      <div style={{ height: 90, background: 'var(--bg-muted)', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
                        {cropUrl ? (
                          <img src={cropUrl} alt={det.label} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                        ) : (
                          <Target size={20} style={{ color: 'var(--text-muted)' }} />
                        )}
                      </div>
                      <div style={{ padding: '8px 10px' }}>
                        <div className="flex items-center justify-between">
                          <span className="badge badge-danger" style={{ fontSize: 10 }}>{det.label}</span>
                          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700, color: det.confidence >= 0.8 ? 'var(--success)' : 'var(--amber)' }}>
                            {Math.round(det.confidence * 100)}%
                          </span>
                        </div>
                      </div>
                    </Link>
                  )
                })}
              </div>
            )}
          </div>
        </div>

        {/* Right: Metadata sidebar */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="card anim-1">
            <div className="card-header">
              <span className="card-title flex items-center gap-2">
                <ImageIcon size={12} />
                Metadata
              </span>
              <span className={`badge ${image.status === 'completed' ? 'badge-success' : image.status === 'processing' ? 'badge-amber' : 'badge-muted'}`}>
                {image.status}
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <MetaRow label="Dimensions">{image.width} x {image.height}</MetaRow>
              <MetaRow label="Size">{(image.file_size_bytes / 1024 / 1024).toFixed(2)} MB</MetaRow>
              <MetaRow label="Plant Site">{image.plant_site}</MetaRow>
              {image.shift && <MetaRow label="Shift">{image.shift}</MetaRow>}
              {image.inspection_line && <MetaRow label="Line">{image.inspection_line}</MetaRow>}
              <MetaRow label="Captured">{new Date(image.captured_at).toLocaleString()}</MetaRow>
              <MetaRow label="Uploaded">{new Date(image.created_at).toLocaleString()}</MetaRow>
              {image.checksum && (
                <MetaRow label="Checksum">
                  <span title={image.checksum}>{image.checksum.slice(0, 12)}...</span>
                </MetaRow>
              )}
            </div>
          </div>

          {/* Video context */}
          {image.video_id && (
            <div className="card anim-2">
              <div className="card-header">
                <span className="card-title flex items-center gap-2">
                  <Video size={12} />
                  Video Frame
                </span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <MetaRow label="Video ID">#{image.video_id}</MetaRow>
                {image.frame_number != null && <MetaRow label="Frame">{image.frame_number}</MetaRow>}
              </div>
              <Link
                to={`/media/videos/${image.video_id}`}
                className="btn btn-secondary btn-sm mt-4"
                style={{ textDecoration: 'none', justifyContent: 'center', width: '100%' }}
              >
                <Video size={12} /> View Video
              </Link>
            </div>
          )}

          {/* Tags */}
          {image.tags && image.tags.length > 0 && (
            <div className="card anim-3">
              <div className="card-header">
                <span className="card-title flex items-center gap-2">
                  <Tag size={12} />
                  Tags
                </span>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {image.tags.map(tag => (
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

          {/* Quick actions */}
          <div className="card anim-3">
            <div className="card-header">
              <span className="card-title flex items-center gap-2">
                <Layers size={12} />
                Actions
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {imgUrl && (
                <a
                  href={imgUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn btn-secondary btn-sm"
                  style={{ textDecoration: 'none', justifyContent: 'center', width: '100%' }}
                >
                  <ImageIcon size={12} /> Open Full Image
                </a>
              )}
              <CompareButton image={image} imgUrl={imgUrl} />
            </div>
          </div>
        </div>
      </div>
      )}

      {/* Comments */}
      <div style={{ marginTop: 20 }}>
        <CommentThread contentType="image" objectId={image.id} />
      </div>
    </div>
  )
}
