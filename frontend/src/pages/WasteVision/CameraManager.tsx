import { useState } from 'react'
import { Plus, Play, Square, Trash2, RefreshCw } from 'lucide-react'
import type { WasteCamera, WasteCameraCreate } from '../../types/api'
import {
  createWasteCamera, deleteWasteCamera,
  startWasteCamera, stopWasteCamera,
} from '../../api/client'

interface Props {
  cameras: WasteCamera[]
  onRefresh: () => void
}

const EMPTY_FORM: WasteCameraCreate = {
  name: '', location: '', plant_site: '', stream_type: 'rtsp', stream_url: '', target_fps: 2,
}

export default function CameraManager({ cameras, onRefresh }: Props) {
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<WasteCameraCreate>(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const handleCreate = async () => {
    if (!form.name || !form.location) { setError('Name and location are required.'); return }
    setSaving(true)
    setError('')
    try {
      await createWasteCamera(form)
      setForm(EMPTY_FORM)
      setShowForm(false)
      onRefresh()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Failed to create camera.'
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg))
    } finally {
      setSaving(false)
    }
  }

  const handleStart = async (uuid: string) => {
    await startWasteCamera(uuid).catch(() => {})
    onRefresh()
  }

  const handleStop = async (uuid: string) => {
    await stopWasteCamera(uuid).catch(() => {})
    onRefresh()
  }

  const handleDelete = async (uuid: string) => {
    if (!window.confirm('Delete this camera and all its inspection history?')) return
    setDeletingId(uuid)
    await deleteWasteCamera(uuid).catch(() => {})
    setDeletingId(null)
    onRefresh()
  }

  return (
    <div style={{ padding: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
          {cameras.length} Camera{cameras.length !== 1 ? 's' : ''} Registered
        </span>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="wv-btn wv-btn-ghost" onClick={onRefresh} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <RefreshCw size={13} />
            REFRESH
          </button>
          <button className="wv-btn wv-btn-primary" onClick={() => setShowForm(s => !s)} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <Plus size={13} />
            ADD CAMERA
          </button>
        </div>
      </div>

      {/* Add form */}
      {showForm && (
        <div className="wv-panel" style={{ marginBottom: 20 }}>
          <div className="wv-panel-header">
            <span>New Camera</span>
            <button className="wv-btn wv-btn-ghost" style={{ padding: '2px 8px', fontSize: '0.6rem' }} onClick={() => setShowForm(false)}>
              CANCEL
            </button>
          </div>
          <div style={{ padding: 16, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label style={{ fontSize: '0.62rem', color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase', display: 'block', marginBottom: 4 }}>Name *</label>
              <input className="wv-input" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="CAM-01" />
            </div>
            <div>
              <label style={{ fontSize: '0.62rem', color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase', display: 'block', marginBottom: 4 }}>Location *</label>
              <input className="wv-input" value={form.location} onChange={e => setForm(f => ({ ...f, location: e.target.value }))} placeholder="Sorting Line A" />
            </div>
            <div>
              <label style={{ fontSize: '0.62rem', color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase', display: 'block', marginBottom: 4 }}>Plant Site</label>
              <input className="wv-input" value={form.plant_site ?? ''} onChange={e => setForm(f => ({ ...f, plant_site: e.target.value }))} placeholder="Plant A" />
            </div>
            <div>
              <label style={{ fontSize: '0.62rem', color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase', display: 'block', marginBottom: 4 }}>Stream Type</label>
              <select className="wv-select" style={{ width: '100%' }} value={form.stream_type} onChange={e => setForm(f => ({ ...f, stream_type: e.target.value as WasteCameraCreate['stream_type'] }))}>
                <option value="rtsp">RTSP</option>
                <option value="mjpeg">MJPEG HTTP</option>
                <option value="upload">Uploaded File</option>
              </select>
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={{ fontSize: '0.62rem', color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase', display: 'block', marginBottom: 4 }}>Stream URL</label>
              <input className="wv-input" value={form.stream_url ?? ''} onChange={e => setForm(f => ({ ...f, stream_url: e.target.value }))} placeholder="rtsp://user:pass@192.168.1.100:554/stream1" />
            </div>
            <div>
              <label style={{ fontSize: '0.62rem', color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase', display: 'block', marginBottom: 4 }}>Target FPS</label>
              <input
                type="number" className="wv-input" min={0.1} max={30} step={0.5}
                value={form.target_fps}
                onChange={e => setForm(f => ({ ...f, target_fps: parseFloat(e.target.value) || 2 }))}
              />
            </div>
            {error && (
              <div style={{ gridColumn: '1 / -1', color: 'var(--wv-red)', fontSize: '0.72rem' }}>{error}</div>
            )}
            <div style={{ gridColumn: '1 / -1', display: 'flex', justifyContent: 'flex-end' }}>
              <button className="wv-btn wv-btn-primary" onClick={handleCreate} disabled={saving}>
                {saving ? 'SAVING...' : 'CREATE CAMERA'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Camera table */}
      <div style={{ overflowX: 'auto' }}>
        <table className="wv-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Location</th>
              <th>Type</th>
              <th>FPS</th>
              <th>Status</th>
              <th>Last Inspection</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {cameras.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 24 }}>
                  No cameras yet. Click ADD CAMERA to register one.
                </td>
              </tr>
            ) : cameras.map(cam => (
              <tr key={cam.camera_uuid}>
                <td style={{ fontWeight: 600 }}>{cam.name}</td>
                <td style={{ color: 'var(--text-secondary)' }}>{cam.location}</td>
                <td style={{ fontSize: '0.65rem', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{cam.stream_type}</td>
                <td style={{ color: 'var(--text-muted)' }}>{cam.target_fps}</td>
                <td>
                  <span className={`wv-status ${cam.status}`}>
                    <span className="wv-live-dot" style={{ background: cam.status === 'streaming' ? 'var(--wv-green)' : cam.status === 'error' ? 'var(--wv-red)' : 'var(--text-muted)' }} />
                    {cam.status.toUpperCase()}
                  </span>
                </td>
                <td style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>
                  {cam.last_frame_at ? new Date(cam.last_frame_at).toLocaleTimeString() : '—'}
                </td>
                <td>
                  <div style={{ display: 'flex', gap: 6 }}>
                    {cam.status !== 'streaming'
                      ? <button className="wv-btn wv-btn-ghost" style={{ padding: '3px 8px', fontSize: '0.62rem', display: 'flex', gap: 4, alignItems: 'center' }} onClick={() => handleStart(cam.camera_uuid)}>
                          <Play size={11} /> START
                        </button>
                      : <button className="wv-btn wv-btn-ghost" style={{ padding: '3px 8px', fontSize: '0.62rem', display: 'flex', gap: 4, alignItems: 'center' }} onClick={() => handleStop(cam.camera_uuid)}>
                          <Square size={11} /> STOP
                        </button>
                    }
                    <button
                      className="wv-btn wv-btn-danger"
                      style={{ padding: '3px 8px', fontSize: '0.62rem', display: 'flex', gap: 4, alignItems: 'center' }}
                      disabled={deletingId === cam.camera_uuid}
                      onClick={() => handleDelete(cam.camera_uuid)}
                    >
                      <Trash2 size={11} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
