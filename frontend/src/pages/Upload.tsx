import { useState, useRef, useCallback, type DragEvent, type ChangeEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Image, Video, Target, Upload as UploadIcon, Check,
  X, Loader2, AlertCircle, CheckCircle, Tag, Plus, type LucideIcon,
} from 'lucide-react'
import { uploadImage, uploadVideo } from '../api/client'

type MediaType = 'image' | 'video' | 'detection'
type Step = 1 | 2 | 3 | 4

const STEPS = [
  { num: 1, label: 'Media Type' },
  { num: 2, label: 'File Select' },
  { num: 3, label: 'Metadata' },
  { num: 4, label: 'Upload' },
]

const TYPE_OPTIONS: { id: MediaType; icon: LucideIcon; label: string; desc: string; accept: string }[] = [
  { id: 'image',     icon: Image,  label: 'Image',    desc: 'Single inspection frame or photo', accept: 'image/*' },
  { id: 'video',     icon: Video,  label: 'Video',    desc: 'Continuous conveyor belt footage',  accept: 'video/*' },
  { id: 'detection', icon: Target, label: 'Detection', desc: 'Annotated bounding box on image',  accept: 'image/*' },
]

export default function Upload() {
  const navigate = useNavigate()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [step, setStep]         = useState<Step>(1)
  const [mediaType, setMediaType] = useState<MediaType | null>(null)
  const [file, setFile]         = useState<File | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [progress, setProgress] = useState(0)
  const [uploadDone, setUploadDone] = useState(false)
  const [error, setError]       = useState('')
  const [uploadResult, setUploadResult] = useState<Record<string, unknown> | null>(null)

  // Metadata fields
  const [plantSite, setPlantSite]       = useState('')
  const [shift, setShift]               = useState('')
  const [inspectionLine, setInspectionLine] = useState('')
  const [dateTime, setDateTime]         = useState('')
  const [tags, setTags]                 = useState<string[]>([])
  const [tagInput, setTagInput]         = useState('')

  const onDrop = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault(); setDragOver(false)
    const f = e.dataTransfer.files[0]
    if (f) setFile(f)
  }, [])

  const addTag = () => {
    const t = tagInput.trim()
    if (t && !tags.includes(t)) setTags((prev) => [...prev, t])
    setTagInput('')
  }

  const canProceedStep1 = !!mediaType
  const canProceedStep2 = !!file
  const canProceedStep3 = !!plantSite.trim()

  const handleUpload = async () => {
    if (!file || !mediaType) return
    setStep(4)
    setProgress(0)
    setError('')

    const fd = new FormData()
    fd.append('file', file)
    fd.append('plant_site', plantSite)
    if (shift) fd.append('shift', shift)
    if (inspectionLine) fd.append('inspection_line', inspectionLine)
    if (dateTime) fd.append(mediaType === 'video' ? 'recorded_at' : 'captured_at', new Date(dateTime).toISOString())
    if (tags.length) {
      fd.append('tags', JSON.stringify(tags.map((name) => ({ name }))))
    }

    try {
      const fn = mediaType === 'video' ? uploadVideo : uploadImage
      const res = await fn(fd, (pct) => setProgress(pct))
      setProgress(100)
      setUploadDone(true)
      setUploadResult(res.data as unknown as Record<string, unknown>)
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? 'Upload failed. Check your connection and try again.')
    }
  }

  const reset = () => {
    setStep(1); setMediaType(null); setFile(null); setProgress(0)
    setUploadDone(false); setError(''); setUploadResult(null)
    setPlantSite(''); setShift(''); setInspectionLine('')
    setDateTime(''); setTags([])
  }

  const accept = mediaType ? (TYPE_OPTIONS.find((t) => t.id === mediaType)?.accept ?? '*/*') : '*/*'

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">Data Upload</h1>
        <p className="page-subtitle">Ingest inspection media into the search engine</p>
      </div>

      {/* Step indicator */}
      <div className="wizard-steps">
        {STEPS.map((s, i) => (
          <div key={s.num} style={{ display: 'flex', alignItems: 'center', flex: i < STEPS.length - 1 ? 1 : 'none' }}>
            <div className={`wizard-step${step === s.num ? ' active' : ''}${step > s.num ? ' done' : ''}`}>
              <div className="wizard-step-num">
                {step > s.num ? <Check size={13} /> : s.num}
              </div>
              <span style={{ display: window.innerWidth > 600 ? 'block' : 'none' }}>{s.label}</span>
            </div>
            {i < STEPS.length - 1 && (
              <div className={`wizard-connector${step > s.num ? ' done' : ''}`} />
            )}
          </div>
        ))}
      </div>

      {/* Content card */}
      <div className="card" style={{ maxWidth: 640, margin: '0 auto', animation: 'fadeUp 0.25s ease-out' }}>

        {/* Step 1: Select type */}
        {step === 1 && (
          <div>
            <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700, letterSpacing: '0.04em', marginBottom: 24, color: 'var(--text-primary)' }}>
              Select Media Type
            </h2>
            <div className="grid-3">
              {TYPE_OPTIONS.map(({ id, icon: Icon, label, desc }) => (
                <div
                  key={id}
                  className={`type-card${mediaType === id ? ' selected' : ''}`}
                  onClick={() => setMediaType(id)}
                >
                  <div className="type-card-icon"><Icon size={22} /></div>
                  <div style={{ fontFamily: 'var(--font-display)', fontSize: 15, fontWeight: 700, letterSpacing: '0.04em', color: 'var(--text-primary)' }}>
                    {label}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.4 }}>
                    {desc}
                  </div>
                </div>
              ))}
            </div>
            <div className="flex justify-end mt-6">
              <button
                className="btn btn-primary"
                onClick={() => setStep(2)}
                disabled={!canProceedStep1}
              >
                Continue →
              </button>
            </div>
          </div>
        )}

        {/* Step 2: File select */}
        {step === 2 && (
          <div>
            <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700, letterSpacing: '0.04em', marginBottom: 24, color: 'var(--text-primary)' }}>
              Select File
            </h2>
            <div
              className={`dropzone${dragOver ? ' drag-over' : ''}`}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onDrop={onDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept={accept}
                style={{ display: 'none' }}
                onChange={(e: ChangeEvent<HTMLInputElement>) => {
                  const f = e.target.files?.[0]
                  if (f) setFile(f)
                }}
              />
              {file ? (
                <div>
                  <div style={{
                    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                    width: 48, height: 48, borderRadius: 'var(--radius-lg)',
                    background: 'var(--success-dim)', border: '1px solid rgba(16,185,129,0.2)',
                    marginBottom: 12,
                  }}>
                    <Check size={22} style={{ color: 'var(--success)' }} />
                  </div>
                  <p style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>{file.name}</p>
                  <p style={{ fontSize: 12, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                    {(file.size / 1024 / 1024).toFixed(2)} MB
                  </p>
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={(e) => { e.stopPropagation(); setFile(null) }}
                    style={{ marginTop: 12 }}
                  >
                    <X size={12} /> Change file
                  </button>
                </div>
              ) : (
                <>
                  <div className="dropzone-icon"><UploadIcon size={22} /></div>
                  <p style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 4 }}>
                    Drag & drop or click to select
                  </p>
                  <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                    {mediaType === 'video' ? 'MP4, MOV, AVI — Max 2GB' : 'PNG, JPG, WEBP — Max 50MB'}
                  </p>
                </>
              )}
            </div>
            <div className="flex justify-between mt-6">
              <button className="btn btn-ghost" onClick={() => setStep(1)}>← Back</button>
              <button className="btn btn-primary" onClick={() => setStep(3)} disabled={!canProceedStep2}>
                Continue →
              </button>
            </div>
          </div>
        )}

        {/* Step 3: Metadata */}
        {step === 3 && (
          <div>
            <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700, letterSpacing: '0.04em', marginBottom: 24, color: 'var(--text-primary)' }}>
              Add Metadata
            </h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div className="form-group">
                <label className="form-label">Plant Site <span style={{ color: 'var(--danger)' }}>*</span></label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g. Unit A, Conveyor 3"
                  value={plantSite}
                  onChange={(e) => setPlantSite(e.target.value)}
                />
              </div>
              <div className="grid-2">
                <div className="form-group">
                  <label className="form-label">Shift</label>
                  <select className="form-input form-select" value={shift} onChange={(e) => setShift(e.target.value)}>
                    <option value="">Not specified</option>
                    <option value="morning">Morning</option>
                    <option value="afternoon">Afternoon</option>
                    <option value="night">Night</option>
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Inspection Line</label>
                  <input
                    type="text"
                    className="form-input"
                    placeholder="e.g. Line 2"
                    value={inspectionLine}
                    onChange={(e) => setInspectionLine(e.target.value)}
                  />
                </div>
              </div>
              <div className="form-group">
                <label className="form-label">{mediaType === 'video' ? 'Recorded At' : 'Captured At'}</label>
                <input
                  type="datetime-local"
                  className="form-input"
                  value={dateTime}
                  onChange={(e) => setDateTime(e.target.value)}
                />
              </div>
              {/* Tags */}
              <div className="form-group">
                <label className="form-label">Tags</label>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    className="form-input"
                    placeholder="Add a tag and press Enter"
                    value={tagInput}
                    onChange={(e) => setTagInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && addTag()}
                    style={{ flex: 1 }}
                  />
                  <button className="btn btn-secondary btn-icon" onClick={addTag} type="button">
                    <Plus size={14} />
                  </button>
                </div>
                {tags.length > 0 && (
                  <div className="flex items-center gap-2 mt-2" style={{ flexWrap: 'wrap' }}>
                    {tags.map((tag) => (
                      <span
                        key={tag}
                        className="badge badge-cyan"
                        style={{ cursor: 'pointer', gap: 5 }}
                        onClick={() => setTags((prev) => prev.filter((t) => t !== tag))}
                      >
                        <Tag size={9} />
                        {tag}
                        <X size={9} />
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
            <div className="flex justify-between mt-6">
              <button className="btn btn-ghost" onClick={() => setStep(2)}>← Back</button>
              <button className="btn btn-primary" onClick={handleUpload} disabled={!canProceedStep3}>
                <UploadIcon size={14} /> Upload
              </button>
            </div>
          </div>
        )}

        {/* Step 4: Progress / Result */}
        {step === 4 && (
          <div style={{ textAlign: 'center', padding: '12px 0' }}>
            {!uploadDone && !error && (
              <>
                <div style={{
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  width: 64, height: 64, borderRadius: '50%',
                  background: 'var(--amber-glow)', border: '2px solid var(--border-amber)',
                  marginBottom: 20,
                }}>
                  <Loader2 size={28} style={{ color: 'var(--amber)', animation: 'spin 1s linear infinite' }} />
                </div>
                <h3 style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700, letterSpacing: '0.04em', marginBottom: 8 }}>
                  Uploading...
                </h3>
                <p style={{ color: 'var(--text-muted)', fontSize: 13, marginBottom: 24 }}>
                  {file?.name}
                </p>
                <div style={{ maxWidth: 400, margin: '0 auto' }}>
                  <div className="progress-bar">
                    <div className="progress-fill" style={{ width: `${progress}%` }} />
                  </div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--amber)', marginTop: 8 }}>
                    {progress}%
                  </div>
                </div>
              </>
            )}

            {error && (
              <div>
                <div style={{
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  width: 64, height: 64, borderRadius: '50%',
                  background: 'var(--danger-dim)', border: '2px solid rgba(239,68,68,0.3)',
                  marginBottom: 20,
                }}>
                  <AlertCircle size={28} style={{ color: 'var(--danger)' }} />
                </div>
                <h3 style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700, color: 'var(--danger)', marginBottom: 12 }}>
                  Upload Failed
                </h3>
                <p style={{ color: 'var(--text-secondary)', fontSize: 14, marginBottom: 24, maxWidth: 360, margin: '0 auto 24px' }}>
                  {error}
                </p>
                <div className="flex justify-center gap-3">
                  <button className="btn btn-secondary" onClick={() => { setError(''); handleUpload() }}>
                    Retry
                  </button>
                  <button className="btn btn-ghost" onClick={reset}>Start Over</button>
                </div>
              </div>
            )}

            {uploadDone && (
              <div>
                <div style={{
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  width: 64, height: 64, borderRadius: '50%',
                  background: 'var(--success-dim)', border: '2px solid rgba(16,185,129,0.3)',
                  marginBottom: 20,
                  animation: 'glow-pulse 2s ease-in-out',
                }}>
                  <CheckCircle size={28} style={{ color: 'var(--success)' }} />
                </div>
                <h3 style={{ fontFamily: 'var(--font-display)', fontSize: 20, fontWeight: 700, color: 'var(--success)', marginBottom: 8 }}>
                  Upload Complete
                </h3>
                <p style={{ color: 'var(--text-muted)', fontSize: 13, marginBottom: 20 }}>
                  Your {mediaType} has been ingested. Embeddings are being generated in the background.
                </p>
                {uploadResult && (
                  <div style={{
                    background: 'var(--bg-elevated)', border: '1px solid var(--border-base)',
                    borderRadius: 'var(--radius-md)', padding: '12px 16px',
                    maxWidth: 360, margin: '0 auto 24px',
                    textAlign: 'left',
                  }}>
                    {uploadResult.plant_site != null && <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}><span style={{ color: 'var(--text-muted)' }}>Plant:</span> {String(uploadResult.plant_site)}</div>}
                    {uploadResult.status != null && <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}><span style={{ color: 'var(--text-muted)' }}>Status:</span> <span className="badge badge-amber">{String(uploadResult.status)}</span></div>}
                    {uploadResult.id != null && <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>ID: {String(uploadResult.id)}</div>}
                  </div>
                )}
                <div className="flex justify-center gap-3">
                  <button className="btn btn-primary" onClick={reset}>Upload Another</button>
                  <button className="btn btn-secondary" onClick={() => navigate('/media')}>View in Library</button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
