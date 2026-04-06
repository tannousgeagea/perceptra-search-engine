import { useEffect, useState } from 'react'
import {
  AlertTriangle, Plus, Trash2, Pencil, X,
  AlertCircle, Shield, Clock, Zap, ChevronLeft, ChevronRight,
  Eye,
} from 'lucide-react'
import {
  getHazardConfigs, createHazardConfig, updateHazardConfig,
  deleteHazardConfig, getDetectionJobs,
} from '../api/client'
import type {
  HazardConfig as HazardConfigType, CreateHazardConfigRequest,
  UpdateHazardConfigRequest, DetectionJob, PaginationMeta,
} from '../types/api'

/* ─── Helpers ─────────────────────────────────────────────── */

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    completed: 'badge-success',
    running:   'badge-amber',
    pending:   'badge-dim',
    failed:    'badge-danger',
    skipped:   'badge-muted',
  }
  return <span className={`badge ${map[status] ?? 'badge-dim'}`}>{status}</span>
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function fmtTime(iso: string) {
  return new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

function extractError(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
  return detail ?? 'An unexpected error occurred.'
}

/* ─── Create / Edit Modal ─────────────────────────────────── */

interface ConfigModalProps {
  initial?: HazardConfigType | null
  onClose: () => void
  onSaved: () => void
}

function ConfigModal({ initial, onClose, onSaved }: ConfigModalProps) {
  const isEdit = !!initial
  const [name, setName]                       = useState(initial?.name ?? '')
  const [promptsText, setPromptsText]         = useState(initial?.prompts.join('\n') ?? '')
  const [backend, setBackend]                 = useState(initial?.detection_backend ?? 'sam3_perceptra')
  const [threshold, setThreshold]             = useState(String(initial?.confidence_threshold ?? '0.3'))
  const [isActive, setIsActive]               = useState(initial?.is_active ?? true)
  const [isDefault, setIsDefault]             = useState(initial?.is_default ?? false)
  const [loading, setLoading]                 = useState(false)
  const [error, setError]                     = useState('')

  const handleSave = async () => {
    const prompts = promptsText.split('\n').map(s => s.trim()).filter(Boolean)
    if (!name.trim()) { setError('Name is required.'); return }
    if (prompts.length === 0) { setError('At least one prompt is required.'); return }

    const thr = parseFloat(threshold)
    if (isNaN(thr) || thr < 0 || thr > 1) { setError('Threshold must be between 0 and 1.'); return }

    setLoading(true); setError('')
    try {
      if (isEdit) {
        const data: UpdateHazardConfigRequest = {
          name: name.trim(),
          prompts,
          detection_backend: backend,
          confidence_threshold: thr,
          is_active: isActive,
          is_default: isDefault,
        }
        await updateHazardConfig(initial!.id, data)
      } else {
        const data: CreateHazardConfigRequest = {
          name: name.trim(),
          prompts,
          detection_backend: backend,
          confidence_threshold: thr,
          is_active: isActive,
          is_default: isDefault,
        }
        await createHazardConfig(data)
      }
      onSaved()
    } catch (err: unknown) {
      setError(extractError(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" style={{ maxWidth: 520 }}>
        <div className="modal-title">{isEdit ? 'Edit Hazard Config' : 'Create Hazard Config'}</div>

        {error && (
          <div className="alert alert-error mb-4">
            <AlertCircle size={14} />
            <span>{error}</span>
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="form-group">
            <label className="form-label">Name <span style={{ color: 'var(--danger)' }}>*</span></label>
            <input
              type="text"
              className="form-input"
              placeholder="e.g. Default Inspection Profile"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
            />
          </div>

          <div className="form-group">
            <label className="form-label">
              Detection Prompts <span style={{ color: 'var(--danger)' }}>*</span>
              <span style={{ opacity: 0.5, textTransform: 'none', letterSpacing: 0, marginLeft: 6 }}>
                (one per line)
              </span>
            </label>
            <textarea
              className="form-input"
              placeholder={'metallic pipe\nrust\ncontainer\ncorrosion'}
              value={promptsText}
              onChange={(e) => setPromptsText(e.target.value)}
              rows={5}
              style={{ fontFamily: 'var(--font-mono)', fontSize: 12, resize: 'vertical' }}
            />
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4, fontFamily: 'var(--font-mono)' }}>
              {promptsText.split('\n').filter(s => s.trim()).length} prompt(s)
            </div>
          </div>

          <div className="grid-2">
            <div className="form-group">
              <label className="form-label">Backend</label>
              <select
                className="form-input form-select"
                value={backend}
                onChange={(e) => setBackend(e.target.value)}
              >
                <option value="sam3_perceptra">SAM3 (perceptra-seg)</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Confidence Threshold</label>
              <input
                type="number"
                className="form-input"
                placeholder="0.3"
                value={threshold}
                onChange={(e) => setThreshold(e.target.value)}
                min="0"
                max="1"
                step="0.05"
                style={{ fontFamily: 'var(--font-mono)' }}
              />
            </div>
          </div>

          <div className="grid-2">
            <div className="form-group">
              <label className="form-label">Active</label>
              <label style={{
                display: 'flex', alignItems: 'center', gap: 8,
                cursor: 'pointer', fontSize: 13, color: 'var(--text-secondary)',
              }}>
                <input
                  type="checkbox"
                  checked={isActive}
                  onChange={(e) => setIsActive(e.target.checked)}
                  style={{ accentColor: 'var(--amber)' }}
                />
                Run on new uploads
              </label>
            </div>
            <div className="form-group">
              <label className="form-label">Default</label>
              <label style={{
                display: 'flex', alignItems: 'center', gap: 8,
                cursor: 'pointer', fontSize: 13, color: 'var(--text-secondary)',
              }}>
                <input
                  type="checkbox"
                  checked={isDefault}
                  onChange={(e) => setIsDefault(e.target.checked)}
                  style={{ accentColor: 'var(--amber)' }}
                />
                Use as default profile
              </label>
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-3 mt-6">
          <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={handleSave} disabled={loading}>
            {loading ? (isEdit ? 'Saving...' : 'Creating...') : (isEdit ? 'Save Changes' : 'Create Config')}
          </button>
        </div>
      </div>
    </div>
  )
}

/* ─── Delete Confirmation Modal ────────────────────────────── */

interface DeleteModalProps {
  config: HazardConfigType
  onClose: () => void
  onDeleted: () => void
}

function DeleteConfirmModal({ config, onClose, onDeleted }: DeleteModalProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState('')

  const handleDelete = async () => {
    setLoading(true); setError('')
    try {
      await deleteHazardConfig(config.id)
      onDeleted()
    } catch (err: unknown) {
      setError(extractError(err))
      setLoading(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" style={{ maxWidth: 440 }}>
        <div style={{
          textAlign: 'center', marginBottom: 20,
          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12,
        }}>
          <div style={{
            width: 48, height: 48, borderRadius: '50%',
            background: 'var(--danger-dim)', border: '1px solid rgba(239,68,68,0.3)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Trash2 size={22} style={{ color: 'var(--danger)' }} />
          </div>
          <div>
            <div className="modal-title" style={{ marginBottom: 4 }}>Delete Detection Profile</div>
            <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              Are you sure you want to delete <strong style={{ color: 'var(--text-primary)' }}>{config.name}</strong>?
            </p>
          </div>
        </div>

        {/* Profile summary */}
        <div style={{
          background: 'var(--bg-elevated)',
          border: '1px solid var(--border-dim)',
          borderRadius: 'var(--radius-md)',
          padding: '12px 14px',
          marginBottom: 16,
        }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div className="flex items-center justify-between" style={{ fontSize: 12 }}>
              <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-display)', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', fontSize: 11 }}>
                Backend
              </span>
              <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)', fontSize: 11 }}>
                {config.detection_backend}
              </code>
            </div>
            <div className="flex items-center justify-between" style={{ fontSize: 12 }}>
              <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-display)', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', fontSize: 11 }}>
                Prompts
              </span>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)', fontSize: 11 }}>
                {config.prompts.length}
              </span>
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 2 }}>
              {config.prompts.slice(0, 6).map((p, i) => (
                <span
                  key={i}
                  style={{
                    fontSize: 10, fontFamily: 'var(--font-mono)',
                    padding: '2px 6px', borderRadius: 3,
                    background: 'var(--bg-muted)',
                    border: '1px solid var(--border-dim)',
                    color: 'var(--text-muted)',
                  }}
                >
                  {p}
                </span>
              ))}
              {config.prompts.length > 6 && (
                <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', padding: '2px 4px' }}>
                  +{config.prompts.length - 6} more
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Warning */}
        <div style={{
          background: 'var(--danger-dim)', border: '1px solid rgba(239,68,68,0.2)',
          borderRadius: 'var(--radius-md)', padding: '10px 12px',
          fontSize: 12, color: 'var(--danger)', marginBottom: 20,
          display: 'flex', alignItems: 'flex-start', gap: 8,
        }}>
          <AlertCircle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
          <span>
            This action is permanent. Future uploads will no longer be analysed with this profile.
            Existing detections created by this profile will not be removed.
          </span>
        </div>

        {error && (
          <div className="alert alert-error mb-4">
            <AlertCircle size={14} />
            <span>{error}</span>
          </div>
        )}

        <div className="flex justify-end gap-3">
          <button className="btn btn-ghost" onClick={onClose} disabled={loading}>Cancel</button>
          <button className="btn btn-danger" onClick={handleDelete} disabled={loading}>
            {loading ? 'Deleting...' : 'Delete Profile'}
          </button>
        </div>
      </div>
    </div>
  )
}

/* ─── Detection Jobs Panel ────────────────────────────────── */

function DetectionJobsPanel() {
  const [jobs, setJobs]         = useState<DetectionJob[]>([])
  const [loading, setLoading]   = useState(false)
  const [page, setPage]         = useState(1)
  const [pagination, setPagination] = useState<PaginationMeta | null>(null)

  const fetchJobs = async () => {
    setLoading(true)
    try {
      const r = await getDetectionJobs({ page, page_size: 10 })
      setJobs(r.data.items)
      setPagination(r.data.pagination)
    } catch { /* silent */ }
    finally { setLoading(false) }
  }

  useEffect(() => { fetchJobs() }, [page])

  return (
    <div className="card anim-3">
      <div className="card-header">
        <span className="card-title flex items-center gap-2">
          <Zap size={12} />
          Detection Jobs
          {pagination && (
            <span style={{
              fontSize: 10, fontFamily: 'var(--font-mono)',
              background: 'var(--bg-muted)', color: 'var(--text-muted)',
              borderRadius: 3, padding: '1px 5px',
            }}>
              {pagination.total_items}
            </span>
          )}
        </span>
        <button className="btn btn-ghost btn-sm" onClick={fetchJobs} title="Refresh">
          <Zap size={12} />
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center" style={{ padding: '40px 0' }}>
          <div className="spinner" />
        </div>
      ) : jobs.length === 0 ? (
        <div className="empty-state" style={{ padding: '40px 20px' }}>
          <div className="empty-state-icon"><Zap size={22} /></div>
          <p style={{ color: 'var(--text-secondary)', fontSize: 14, fontFamily: 'var(--font-display)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            No Detection Jobs
          </p>
          <p style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 4 }}>
            Jobs appear here when images are processed with hazard detection.
          </p>
        </div>
      ) : (
        <>
          <div className="table-wrapper">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Image</th>
                  <th>Config</th>
                  <th>Status</th>
                  <th>Detections</th>
                  <th>Inference</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr key={job.id}>
                    <td>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)' }}>
                        {job.image_filename || `#${job.image_id}`}
                      </span>
                    </td>
                    <td>
                      <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                        {job.hazard_config_name ?? '—'}
                      </span>
                    </td>
                    <td><StatusBadge status={job.status} /></td>
                    <td>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-primary)' }}>
                        {job.total_detections}
                      </span>
                    </td>
                    <td>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>
                        {job.inference_time_ms != null ? `${job.inference_time_ms.toFixed(0)}ms` : '—'}
                      </span>
                    </td>
                    <td>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                        {fmtDate(job.created_at)}
                        <br />
                        {fmtTime(job.created_at)}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {pagination && pagination.total_pages > 1 && (
            <div className="flex items-center justify-between" style={{ padding: '12px 0' }}>
              <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                Page {pagination.page} of {pagination.total_pages}
              </span>
              <div className="flex items-center gap-2">
                <button
                  className="btn btn-ghost btn-sm"
                  disabled={!pagination.has_previous}
                  onClick={() => setPage(p => p - 1)}
                >
                  <ChevronLeft size={12} /> Prev
                </button>
                <button
                  className="btn btn-ghost btn-sm"
                  disabled={!pagination.has_next}
                  onClick={() => setPage(p => p + 1)}
                >
                  Next <ChevronRight size={12} />
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

/* ─── Main Page ───────────────────────────────────────────── */

export default function HazardConfig() {
  const [configs, setConfigs]       = useState<HazardConfigType[]>([])
  const [loading, setLoading]       = useState(false)
  const [error, setError]           = useState('')
  const [showModal, setShowModal]   = useState(false)
  const [editing, setEditing]       = useState<HazardConfigType | null>(null)
  const [deleting, setDeleting]     = useState<HazardConfigType | null>(null)
  const [page, setPage]             = useState(1)
  const [pagination, setPagination] = useState<PaginationMeta | null>(null)

  const fetchConfigs = async () => {
    setLoading(true); setError('')
    try {
      const r = await getHazardConfigs({ page, page_size: 20 })
      setConfigs(r.data.items)
      setPagination(r.data.pagination)
    } catch (err: unknown) {
      setError(extractError(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchConfigs() }, [page])

  const handleDelete = (cfg: HazardConfigType) => {
    setDeleting(cfg)
  }

  const handleToggleActive = async (cfg: HazardConfigType) => {
    try {
      await updateHazardConfig(cfg.id, { is_active: !cfg.is_active })
      fetchConfigs()
    } catch { /* silent */ }
  }

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">Hazard Detection</h1>
        <p className="page-subtitle">Configure automatic hazard detection profiles for inspection images</p>
      </div>

      {error && (
        <div className="alert alert-error mb-4" style={{ animation: 'fadeUp 0.3s ease-out' }}>
          <AlertCircle size={14} />
          <span>{error}</span>
          <button
            className="btn btn-ghost btn-icon btn-sm"
            onClick={() => setError('')}
            style={{ marginLeft: 'auto' }}
          >
            <X size={12} />
          </button>
        </div>
      )}

      {/* Configs List */}
      <div className="card anim-1">
        <div className="card-header">
          <span className="card-title flex items-center gap-2">
            <AlertTriangle size={12} />
            Detection Profiles
            {configs.length > 0 && (
              <span style={{
                fontSize: 10, fontFamily: 'var(--font-mono)',
                background: 'var(--bg-muted)', color: 'var(--text-muted)',
                borderRadius: 3, padding: '1px 5px',
              }}>
                {pagination?.total_items ?? configs.length}
              </span>
            )}
          </span>
          <button
            className="btn btn-primary btn-sm"
            onClick={() => { setEditing(null); setShowModal(true) }}
          >
            <Plus size={12} /> New Profile
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center" style={{ padding: '40px 0' }}>
            <div className="spinner" />
          </div>
        ) : configs.length === 0 ? (
          <div className="empty-state" style={{ padding: '48px 20px' }}>
            <div className="empty-state-icon"><AlertTriangle size={22} /></div>
            <p style={{ color: 'var(--text-secondary)', fontSize: 14, fontFamily: 'var(--font-display)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              No Detection Profiles
            </p>
            <p style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 4, maxWidth: 360, textAlign: 'center' }}>
              Create a profile with hazard prompts to automatically detect objects like metallic pipes, rust, and containers in uploaded images.
            </p>
            <button
              className="btn btn-primary btn-sm mt-4"
              onClick={() => { setEditing(null); setShowModal(true) }}
            >
              <Plus size={12} /> Create Profile
            </button>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
            {configs.map((cfg) => (
              <div
                key={cfg.id}
                style={{
                  padding: '16px 0',
                  borderBottom: '1px solid var(--border-dim)',
                  display: 'flex', flexDirection: 'column', gap: 10,
                }}
              >
                {/* Row 1: Name + badges */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div style={{
                      width: 36, height: 36, borderRadius: 'var(--radius-md)',
                      background: cfg.is_active ? 'var(--amber-glow)' : 'var(--bg-muted)',
                      border: `1px solid ${cfg.is_active ? 'var(--border-amber)' : 'var(--border-dim)'}`,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      flexShrink: 0,
                    }}>
                      <Shield size={16} style={{ color: cfg.is_active ? 'var(--amber)' : 'var(--text-muted)' }} />
                    </div>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 14, color: cfg.is_active ? 'var(--text-primary)' : 'var(--text-muted)' }}>
                        {cfg.name}
                      </div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                        {cfg.detection_backend} &middot; threshold {cfg.confidence_threshold}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {cfg.is_default && <span className="badge badge-cyan">Default</span>}
                    <span className={`badge ${cfg.is_active ? 'badge-success' : 'badge-muted'}`}>
                      {cfg.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </div>
                </div>

                {/* Row 2: Prompts */}
                <div style={{
                  display: 'flex', flexWrap: 'wrap', gap: 6,
                  padding: '8px 12px',
                  background: 'var(--bg-elevated)',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--border-dim)',
                }}>
                  {cfg.prompts.map((p, i) => (
                    <span
                      key={i}
                      style={{
                        fontSize: 11, fontFamily: 'var(--font-mono)',
                        padding: '3px 8px', borderRadius: 4,
                        background: 'var(--amber-glow)',
                        border: '1px solid var(--border-amber)',
                        color: 'var(--amber)',
                      }}
                    >
                      {p}
                    </span>
                  ))}
                </div>

                {/* Row 3: Meta + actions */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4" style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                    <div className="flex items-center gap-1">
                      <Eye size={10} />
                      {cfg.prompts.length} prompt{cfg.prompts.length !== 1 ? 's' : ''}
                    </div>
                    <div className="flex items-center gap-1">
                      <Clock size={10} />
                      Updated {fmtDate(cfg.updated_at)}
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => handleToggleActive(cfg)}
                      style={{ fontSize: 11 }}
                    >
                      {cfg.is_active ? 'Deactivate' : 'Activate'}
                    </button>
                    <button
                      className="btn btn-ghost btn-icon btn-sm"
                      onClick={() => { setEditing(cfg); setShowModal(true) }}
                      title="Edit"
                    >
                      <Pencil size={12} />
                    </button>
                    <button
                      className="btn btn-danger btn-icon btn-sm"
                      onClick={() => handleDelete(cfg)}
                      title="Delete"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>
              </div>
            ))}

            {/* Pagination */}
            {pagination && pagination.total_pages > 1 && (
              <div className="flex items-center justify-between" style={{ padding: '12px 0' }}>
                <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                  Page {pagination.page} of {pagination.total_pages}
                </span>
                <div className="flex items-center gap-2">
                  <button
                    className="btn btn-ghost btn-sm"
                    disabled={!pagination.has_previous}
                    onClick={() => setPage(p => p - 1)}
                  >
                    <ChevronLeft size={12} /> Prev
                  </button>
                  <button
                    className="btn btn-ghost btn-sm"
                    disabled={!pagination.has_next}
                    onClick={() => setPage(p => p + 1)}
                  >
                    Next <ChevronRight size={12} />
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Detection Jobs */}
      <div style={{ marginTop: 24 }}>
        <DetectionJobsPanel />
      </div>

      {/* Create / Edit Modal */}
      {showModal && (
        <ConfigModal
          initial={editing}
          onClose={() => { setShowModal(false); setEditing(null) }}
          onSaved={() => { setShowModal(false); setEditing(null); fetchConfigs() }}
        />
      )}

      {/* Delete Confirmation Modal */}
      {deleting && (
        <DeleteConfirmModal
          config={deleting}
          onClose={() => setDeleting(null)}
          onDeleted={() => { setDeleting(null); fetchConfigs() }}
        />
      )}
    </div>
  )
}
