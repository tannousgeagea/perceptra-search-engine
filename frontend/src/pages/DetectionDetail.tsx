import { useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import {
  ArrowLeft, Target, Image as ImageIcon, MapPin, Clock, Tag,
  AlertCircle, Loader2, Search, Video, Layers, Columns2, UserPlus,
} from 'lucide-react'
import { getDetection } from '../api/client'
import type { DetectionMedia } from '../types/api'
import { useCompare } from '../context/CompareContext'
import CommentThread from '../components/CommentThread'
import AssignModal from '../components/AssignModal'

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

function CompareDetectionButton({ detection }: { detection: DetectionMedia }) {
  const { addItem, isInTray } = useCompare()
  const inTray = isInTray(detection.id)
  const cropUrl = detection.crop_url || (detection.storage_key ? `/api/v1/media/files/${detection.storage_key}` : '')
  return (
    <div className="card anim-3" style={{ padding: 12 }}>
      <button
        className={`btn ${inTray ? 'btn-primary' : 'btn-secondary'} btn-sm`}
        style={{ justifyContent: 'center', width: '100%' }}
        disabled={inTray}
        onClick={() => addItem({
          id: detection.id, type: 'detection', url: cropUrl,
          label: detection.label, plant_site: detection.plant_site ?? '',
          captured_at: detection.captured_at ?? '',
        })}
      >
        <Columns2 size={12} /> {inTray ? 'In Compare Tray' : 'Add to Compare'}
      </button>
    </div>
  )
}

export default function DetectionDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [detection, setDetection] = useState<DetectionMedia | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showAssign, setShowAssign] = useState(false)

  useEffect(() => {
    if (!id) return
    setLoading(true)
    getDetection(parseInt(id))
      .then(res => setDetection(res.data))
      .catch(() => setError('Failed to load detection.'))
      .finally(() => setLoading(false))
  }, [id])

  if (loading) {
    return (
      <div className="page-container">
        <div className="flex items-center justify-center" style={{ padding: '80px 0' }}>
          <Loader2 size={24} style={{ animation: 'spin 0.8s linear infinite', color: 'var(--amber)' }} />
        </div>
      </div>
    )
  }

  if (error || !detection) {
    return (
      <div className="page-container">
        <div className="alert alert-error">
          <AlertCircle size={14} />
          <span>{error || 'Detection not found.'}</span>
        </div>
        <button className="btn btn-ghost mt-4" onClick={() => navigate('/media')}>
          <ArrowLeft size={14} /> Back to Media
        </button>
      </div>
    )
  }

  const cropUrl = detection.crop_url || (detection.storage_key ? `/api/v1/media/files/${detection.storage_key}` : null)
  const parentImgUrl = detection.image_url

  return (
    <div className="page-container">
      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <button className="btn btn-ghost btn-sm" onClick={() => navigate(-1)} style={{ marginBottom: 12 }}>
          <ArrowLeft size={14} /> Back
        </button>
        <div className="flex items-center gap-3">
          <h1 className="page-title" style={{ fontSize: 20 }}>{detection.label}</h1>
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 700,
            color: detection.confidence >= 0.8 ? 'var(--success)' : detection.confidence >= 0.5 ? 'var(--amber)' : 'var(--danger)',
          }}>
            {Math.round(detection.confidence * 100)}%
          </span>
        </div>
        <p className="page-subtitle">Detection detail with crop and parent image context</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 24, alignItems: 'start' }}>
        {/* Left: Crop + parent image */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          {/* Detection crop */}
          <div className="card anim-1">
            <div className="card-header">
              <span className="card-title flex items-center gap-2">
                <Target size={12} />
                Detection Crop
              </span>
              <span className="badge badge-danger">{detection.label}</span>
            </div>
            <div style={{ borderRadius: 'var(--radius-md)', overflow: 'hidden', background: '#000' }}>
              {cropUrl ? (
                <img
                  src={cropUrl}
                  alt={detection.label}
                  style={{ width: '100%', height: 'auto', maxHeight: 400, objectFit: 'contain', display: 'block' }}
                />
              ) : (
                <div style={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg-muted)' }}>
                  <Target size={48} style={{ color: 'var(--text-muted)' }} />
                </div>
              )}
            </div>
          </div>

          {/* Parent image context */}
          <div className="card anim-2">
            <div className="card-header">
              <span className="card-title flex items-center gap-2">
                <ImageIcon size={12} />
                Parent Image
              </span>
              <Link
                to={`/media/images/${detection.image_id}`}
                className="btn btn-ghost btn-sm"
                style={{ textDecoration: 'none' }}
              >
                <ImageIcon size={12} /> View Image
              </Link>
            </div>
            <div style={{ borderRadius: 'var(--radius-md)', overflow: 'hidden', background: '#000', display: 'flex', justifyContent: 'center' }}>
              {parentImgUrl ? (
                <div style={{ position: 'relative', display: 'inline-block', maxWidth: '100%' }}>
                  <img
                    src={parentImgUrl}
                    alt="Parent image"
                    style={{ display: 'block', maxWidth: '100%', height: 'auto' }}
                  />
                  {/* BBox overlay — positioned relative to the image element itself */}
                  {detection.bbox_format === 'normalized' && (
                    <div style={{
                      position: 'absolute',
                      left: `${detection.bbox_x * 100}%`,
                      top: `${detection.bbox_y * 100}%`,
                      width: `${detection.bbox_width * 100}%`,
                      height: `${detection.bbox_height * 100}%`,
                      border: '2px solid var(--danger)',
                      borderRadius: 2,
                      pointerEvents: 'none',
                      boxShadow: '0 0 8px rgba(239,68,68,0.5)',
                    }} />
                  )}
                </div>
              ) : (
                <div style={{ height: 200, width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg-muted)' }}>
                  <ImageIcon size={48} style={{ color: 'var(--text-muted)' }} />
                </div>
              )}
            </div>
            {detection.image_filename && (
              <div style={{ marginTop: 8, fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                {detection.image_filename}
                {detection.image_width && detection.image_height && ` (${detection.image_width}x${detection.image_height})`}
              </div>
            )}
          </div>
        </div>

        {/* Right: Metadata sidebar */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Detection info */}
          <div className="card anim-1">
            <div className="card-header">
              <span className="card-title flex items-center gap-2">
                <Target size={12} />
                Detection Info
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <MetaRow label="Label">{detection.label}</MetaRow>
              <MetaRow label="Confidence">
                <span style={{ color: detection.confidence >= 0.8 ? 'var(--success)' : 'var(--amber)' }}>
                  {(detection.confidence * 100).toFixed(1)}%
                </span>
              </MetaRow>
              <MetaRow label="BBox">
                {detection.bbox_x.toFixed(3)}, {detection.bbox_y.toFixed(3)}
              </MetaRow>
              <MetaRow label="BBox Size">
                {detection.bbox_width.toFixed(3)} x {detection.bbox_height.toFixed(3)}
              </MetaRow>
              <MetaRow label="Format">{detection.bbox_format}</MetaRow>
            </div>
          </div>

          {/* Embedding info */}
          <div className="card anim-2">
            <div className="card-header">
              <span className="card-title flex items-center gap-2">
                <Layers size={12} />
                Embedding
              </span>
              <span className={`badge ${detection.embedding_generated ? 'badge-success' : 'badge-muted'}`}>
                {detection.embedding_generated ? 'Generated' : 'Pending'}
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {detection.embedding_model_version && (
                <MetaRow label="Model">{detection.embedding_model_version}</MetaRow>
              )}
              <MetaRow label="Searchable">{detection.embedding_generated ? 'Yes' : 'Not yet'}</MetaRow>
            </div>
          </div>

          {/* Context */}
          <div className="card anim-2">
            <div className="card-header">
              <span className="card-title flex items-center gap-2">
                <MapPin size={12} />
                Context
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {detection.plant_site && <MetaRow label="Plant">{detection.plant_site}</MetaRow>}
              {detection.shift && <MetaRow label="Shift">{detection.shift}</MetaRow>}
              {detection.inspection_line && <MetaRow label="Line">{detection.inspection_line}</MetaRow>}
              {detection.captured_at && <MetaRow label="Captured">{new Date(detection.captured_at).toLocaleString()}</MetaRow>}
              <MetaRow label="Created">{new Date(detection.created_at).toLocaleString()}</MetaRow>
            </div>
          </div>

          {/* Video context */}
          {detection.video_id && (
            <div className="card anim-3">
              <div className="card-header">
                <span className="card-title flex items-center gap-2">
                  <Video size={12} />
                  Video Source
                </span>
              </div>
              <Link
                to={`/media/videos/${detection.video_id}`}
                className="btn btn-secondary btn-sm"
                style={{ textDecoration: 'none', justifyContent: 'center', width: '100%' }}
              >
                <Video size={12} /> View Source Video
              </Link>
            </div>
          )}

          {/* Compare action */}
          <CompareDetectionButton detection={detection} />

          {/* Assign */}
          <div className="card anim-3" style={{ padding: 12 }}>
            <button
              className="btn btn-secondary btn-sm"
              style={{ justifyContent: 'center', width: '100%' }}
              onClick={() => setShowAssign(true)}
            >
              <UserPlus size={12} /> Assign to Team Member
            </button>
          </div>

          {/* Tags */}
          {detection.tags && detection.tags.length > 0 && (
            <div className="card anim-3">
              <div className="card-header">
                <span className="card-title flex items-center gap-2">
                  <Tag size={12} />
                  Tags
                </span>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {detection.tags.map(tag => (
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

      {/* Comments */}
      <div style={{ marginTop: 20 }}>
        <CommentThread contentType="detection" objectId={detection.id} />
      </div>

      {/* Assign Modal */}
      {showAssign && (
        <AssignModal
          detectionId={detection.id}
          onClose={() => setShowAssign(false)}
          onAssigned={() => setShowAssign(false)}
        />
      )}
    </div>
  )
}
