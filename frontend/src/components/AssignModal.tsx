import { useEffect, useState } from 'react'
import { X, UserPlus } from 'lucide-react'
import type { TenantUser } from '../types/api'
import { getTenantUsers, createAssignment } from '../api/client'

interface AssignModalProps {
  detectionId: number
  onClose: () => void
  onAssigned: () => void
}

export default function AssignModal({ detectionId, onClose, onAssigned }: AssignModalProps) {
  const [users, setUsers] = useState<TenantUser[]>([])
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null)
  const [priority, setPriority] = useState('medium')
  const [dueDate, setDueDate] = useState('')
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    getTenantUsers().then((r) => setUsers(r.data)).catch(() => {})
  }, [])

  const handleSave = async () => {
    if (!selectedUserId) {
      setError('Select a user to assign')
      return
    }
    setSaving(true)
    setError('')
    try {
      await createAssignment({
        detection_id: detectionId,
        assigned_to_id: selectedUserId,
        priority,
        due_date: dueDate || null,
        notes: notes || null,
      })
      onAssigned()
    } catch (err) {
      const r = err as { response?: { data?: { detail?: string } } }
      setError(r?.response?.data?.detail || 'Failed to create assignment')
    }
    setSaving(false)
  }

  return (
    <>
      <div className="modal-overlay" onClick={onClose} />
      <div className="modal" style={{ maxWidth: 420 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 className="modal-title flex items-center gap-2">
            <UserPlus size={16} /> Assign Detection
          </h3>
          <button className="btn btn-ghost btn-icon" onClick={onClose}><X size={16} /></button>
        </div>

        {error && (
          <div style={{ padding: '8px 12px', marginBottom: 12, background: 'var(--danger-dim)', border: '1px solid var(--danger)', borderRadius: 'var(--radius-md)', fontSize: 12, color: 'var(--danger)' }}>
            {error}
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <label className="form-label">Assign To</label>
            <select className="form-select" value={selectedUserId ?? ''} onChange={(e) => setSelectedUserId(Number(e.target.value) || null)}>
              <option value="">Select team member...</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>{u.name || u.email}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="form-label">Priority</label>
            <select className="form-select" value={priority} onChange={(e) => setPriority(e.target.value)}>
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
              <option value="critical">Critical</option>
            </select>
          </div>
          <div>
            <label className="form-label">Due Date (optional)</label>
            <input className="form-input" type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
          </div>
          <div>
            <label className="form-label">Notes (optional)</label>
            <textarea className="form-textarea" value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} placeholder="Additional context..." />
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
          <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={handleSave} disabled={saving || !selectedUserId}>
            {saving ? 'Assigning...' : 'Assign'}
          </button>
        </div>
      </div>
    </>
  )
}
