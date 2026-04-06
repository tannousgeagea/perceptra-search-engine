import { useEffect, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import {
  ClipboardCheck, ListChecks, Shield, Plus, Trash2, Edit2,
  Check, X, Power, ChevronRight,
} from 'lucide-react'
import type {
  ChecklistTemplate, ChecklistInstance, ChecklistItemSchema,
  ComplianceStats, PaginationMeta, CreateChecklistTemplateRequest,
} from '../types/api'
import {
  getChecklistTemplates, createChecklistTemplate, updateChecklistTemplate,
  deleteChecklistTemplate, getChecklistInstances, createChecklistInstance,
  submitChecklistItem, completeChecklist, getComplianceStats,
} from '../api/client'

const TOOLTIP_STYLE = {
  backgroundColor: 'var(--bg-elevated)',
  border: '1px solid var(--border-bright)',
  borderRadius: 'var(--radius-md)',
  fontFamily: 'var(--font-mono)',
  fontSize: 12,
  color: 'var(--text-primary)',
}

function extractError(err: unknown): string {
  if (typeof err === 'object' && err !== null && 'response' in err) {
    const r = (err as { response?: { data?: { detail?: string } } }).response
    if (r?.data?.detail) return r.data.detail
  }
  return 'An error occurred'
}

// ── Active Tab ───────────────────────────────────────────────

function ActiveTab() {
  const [instances, setInstances] = useState<ChecklistInstance[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<ChecklistInstance | null>(null)
  const [templates, setTemplates] = useState<ChecklistTemplate[]>([])
  const [showStart, setShowStart] = useState(false)
  const [startTemplateId, setStartTemplateId] = useState<number | null>(null)
  const [startShift, setStartShift] = useState('morning')
  const [startDate, setStartDate] = useState(() => new Date().toISOString().split('T')[0])

  useEffect(() => {
    setLoading(true)
    getChecklistInstances({ page_size: 50 })
      .then((r) => setInstances(r.data.items))
      .catch(() => {})
      .finally(() => setLoading(false))
    getChecklistTemplates({ is_active: true })
      .then((r) => setTemplates(r.data.items))
      .catch(() => {})
  }, [])

  const handleStart = async () => {
    if (!startTemplateId) return
    try {
      const r = await createChecklistInstance({ template_id: startTemplateId, shift: startShift, date: startDate })
      setInstances((prev) => [r.data, ...prev])
      setShowStart(false)
      setSelected(r.data)
    } catch { /* ignore */ }
  }

  const handleSubmitItem = async (instanceId: number, itemIndex: number, status: string) => {
    try {
      const r = await submitChecklistItem(instanceId, itemIndex, { status })
      setSelected(r.data)
      setInstances((prev) => prev.map((i) => i.id === instanceId ? r.data : i))
    } catch { /* ignore */ }
  }

  const handleComplete = async (instanceId: number) => {
    try {
      const r = await completeChecklist(instanceId)
      setSelected(r.data)
      setInstances((prev) => prev.map((i) => i.id === instanceId ? r.data : i))
    } catch { /* ignore */ }
  }

  if (selected) {
    const allDone = selected.items.every((i) => i.status !== 'pending')
    return (
      <div>
        <button className="btn btn-ghost btn-sm" onClick={() => setSelected(null)} style={{ marginBottom: 12 }}>
          &larr; Back to list
        </button>
        <div className="card" style={{ padding: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <div>
              <h3 style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>{selected.template_name}</h3>
              <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>{selected.plant_site} — {selected.shift} — {selected.date}</p>
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <span className={`badge ${selected.status === 'completed' ? 'badge-success' : selected.status === 'in_progress' ? 'badge-amber' : 'badge-muted'}`}>
                {selected.status.toUpperCase().replace('_', ' ')}
              </span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)' }}>
                {selected.progress.toFixed(0)}%
              </span>
            </div>
          </div>

          {/* Progress bar */}
          <div style={{ width: '100%', height: 6, background: 'var(--bg-muted)', borderRadius: 3, marginBottom: 16 }}>
            <div style={{ width: `${selected.progress}%`, height: '100%', background: 'var(--amber)', borderRadius: 3, transition: 'width 0.3s ease' }} />
          </div>

          {/* Items */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {selected.items.map((item) => (
              <div
                key={item.item_index}
                style={{
                  display: 'flex', gap: 12, padding: '10px 12px',
                  background: 'var(--bg-elevated)', border: '1px solid var(--border-dim)',
                  borderRadius: 'var(--radius-md)', alignItems: 'center',
                  borderLeft: `3px solid ${item.status === 'passed' ? 'var(--success)' : item.status === 'failed' ? 'var(--danger)' : item.status === 'flagged' ? 'var(--warning)' : 'var(--border-dim)'}`,
                }}
              >
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 2 }}>
                    {item.description}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', display: 'flex', gap: 8 }}>
                    {item.required_photo && <span>Photo required</span>}
                    {item.auto_detect && <span>Auto-detect</span>}
                    {item.detection_count > 0 && <span>{item.detection_count} detections</span>}
                  </div>
                </div>
                {selected.status !== 'completed' && item.status === 'pending' ? (
                  <div style={{ display: 'flex', gap: 4 }}>
                    <button className="btn btn-ghost btn-sm" onClick={() => handleSubmitItem(selected.id, item.item_index, 'passed')} title="Pass" style={{ color: 'var(--success)' }}>
                      <Check size={14} /> Pass
                    </button>
                    <button className="btn btn-ghost btn-sm" onClick={() => handleSubmitItem(selected.id, item.item_index, 'failed')} title="Fail" style={{ color: 'var(--danger)' }}>
                      <X size={14} /> Fail
                    </button>
                  </div>
                ) : (
                  <span className={`badge ${item.status === 'passed' ? 'badge-success' : item.status === 'failed' ? 'badge-danger' : item.status === 'flagged' ? 'badge-amber' : 'badge-muted'}`} style={{ fontSize: 10 }}>
                    {item.status.toUpperCase()}
                  </span>
                )}
              </div>
            ))}
          </div>

          {selected.status !== 'completed' && allDone && (
            <button className="btn btn-primary" style={{ marginTop: 16, width: '100%' }} onClick={() => handleComplete(selected.id)}>
              <ClipboardCheck size={14} /> Complete Checklist
            </button>
          )}
        </div>
      </div>
    )
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <p style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Active and recent checklists</p>
        <button className="btn btn-primary btn-sm" onClick={() => setShowStart(true)}>
          <Plus size={13} /> Start Checklist
        </button>
      </div>

      {showStart && (
        <>
          <div className="modal-overlay" onClick={() => setShowStart(false)} />
          <div className="modal" style={{ maxWidth: 400 }}>
            <h3 className="modal-title">Start New Checklist</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 12 }}>
              <div>
                <label className="form-label">Template</label>
                <select className="form-select" value={startTemplateId ?? ''} onChange={(e) => setStartTemplateId(Number(e.target.value) || null)}>
                  <option value="">Select template...</option>
                  {templates.map((t) => <option key={t.id} value={t.id}>{t.name} ({t.plant_site})</option>)}
                </select>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label className="form-label">Shift</label>
                  <select className="form-select" value={startShift} onChange={(e) => setStartShift(e.target.value)}>
                    <option value="morning">Morning</option>
                    <option value="afternoon">Afternoon</option>
                    <option value="night">Night</option>
                  </select>
                </div>
                <div>
                  <label className="form-label">Date</label>
                  <input className="form-input" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
                </div>
              </div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
              <button className="btn btn-ghost" onClick={() => setShowStart(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={handleStart} disabled={!startTemplateId}>Start</button>
            </div>
          </div>
        </>
      )}

      {loading ? (
        <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-muted)' }}>Loading...</div>
      ) : instances.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon"><ClipboardCheck size={32} /></div>
          <p>No checklists yet</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {instances.map((inst) => (
            <div
              key={inst.id}
              className="card"
              style={{ padding: '12px 16px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 12, transition: 'border-color var(--transition-fast)' }}
              onClick={() => setSelected(inst)}
              onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--amber)' }}
              onMouseLeave={(e) => { e.currentTarget.style.borderColor = '' }}
            >
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 2 }}>{inst.template_name}</div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', display: 'flex', gap: 8 }}>
                  <span>{inst.plant_site}</span>
                  <span>{inst.shift}</span>
                  <span>{inst.date}</span>
                </div>
              </div>
              <div style={{ width: 80, height: 6, background: 'var(--bg-muted)', borderRadius: 3 }}>
                <div style={{ width: `${inst.progress}%`, height: '100%', background: inst.status === 'completed' ? 'var(--success)' : 'var(--amber)', borderRadius: 3 }} />
              </div>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', width: 35 }}>{inst.progress.toFixed(0)}%</span>
              <span className={`badge ${inst.status === 'completed' ? 'badge-success' : inst.status === 'in_progress' ? 'badge-amber' : inst.status === 'overdue' ? 'badge-danger' : 'badge-muted'}`} style={{ fontSize: 10 }}>
                {inst.status.toUpperCase().replace('_', ' ')}
              </span>
              <ChevronRight size={14} style={{ color: 'var(--text-muted)' }} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Templates Tab ────────────────────────────────────────────

function TemplatesTab() {
  const [templates, setTemplates] = useState<ChecklistTemplate[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editing, setEditing] = useState<ChecklistTemplate | null>(null)
  const [name, setName] = useState('')
  const [plantSite, setPlantSite] = useState('')
  const [items, setItems] = useState<ChecklistItemSchema[]>([{ description: '', required_photo: false, auto_detect: false }])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const fetchTemplates = () => {
    setLoading(true)
    getChecklistTemplates()
      .then((r) => setTemplates(r.data.items))
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchTemplates() }, [])

  const openModal = (tmpl: ChecklistTemplate | null) => {
    setEditing(tmpl)
    setName(tmpl?.name ?? '')
    setPlantSite(tmpl?.plant_site ?? '')
    setItems(tmpl?.items?.length ? tmpl.items : [{ description: '', required_photo: false, auto_detect: false }])
    setError('')
    setShowModal(true)
  }

  const handleSave = async () => {
    if (!name.trim() || !plantSite.trim() || items.some((i) => !i.description.trim())) {
      setError('Name, plant site, and all item descriptions are required')
      return
    }
    setSaving(true)
    try {
      const data: CreateChecklistTemplateRequest = { name, plant_site: plantSite, items }
      if (editing) {
        await updateChecklistTemplate(editing.id, data)
      } else {
        await createChecklistTemplate(data)
      }
      setShowModal(false)
      fetchTemplates()
    } catch (err) { setError(extractError(err)) }
    setSaving(false)
  }

  const handleDelete = async (id: number) => {
    try { await deleteChecklistTemplate(id); setTemplates((prev) => prev.filter((t) => t.id !== id)) } catch { /* */ }
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <p style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Manage inspection checklist templates</p>
        <button className="btn btn-primary btn-sm" onClick={() => openModal(null)}><Plus size={13} /> New Template</button>
      </div>

      {loading ? (
        <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-muted)' }}>Loading...</div>
      ) : templates.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon"><ListChecks size={32} /></div>
          <p>No templates yet</p>
          <button className="btn btn-primary btn-sm" onClick={() => openModal(null)}><Plus size={13} /> Create First Template</button>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {templates.map((t) => (
            <div key={t.id} className="card" style={{ padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 12, opacity: t.is_active ? 1 : 0.6 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{t.name}</div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', display: 'flex', gap: 8 }}>
                  <span>{t.plant_site}</span>
                  {t.shift && <span>Shift: {t.shift}</span>}
                  <span>{t.items.length} items</span>
                </div>
              </div>
              <button className="btn btn-ghost btn-icon" onClick={() => openModal(t)}><Edit2 size={13} /></button>
              <button className="btn btn-ghost btn-icon" onClick={() => handleDelete(t.id)}><Trash2 size={13} style={{ color: 'var(--danger)' }} /></button>
            </div>
          ))}
        </div>
      )}

      {showModal && (
        <>
          <div className="modal-overlay" onClick={() => setShowModal(false)} />
          <div className="modal" style={{ maxWidth: 560 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
              <h3 className="modal-title">{editing ? 'Edit Template' : 'New Template'}</h3>
              <button className="btn btn-ghost btn-icon" onClick={() => setShowModal(false)}><X size={16} /></button>
            </div>
            {error && <div style={{ padding: '8px 12px', marginBottom: 12, background: 'var(--danger-dim)', border: '1px solid var(--danger)', borderRadius: 'var(--radius-md)', fontSize: 12, color: 'var(--danger)' }}>{error}</div>}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div><label className="form-label">Name</label><input className="form-input" value={name} onChange={(e) => setName(e.target.value)} /></div>
                <div><label className="form-label">Plant Site</label><input className="form-input" value={plantSite} onChange={(e) => setPlantSite(e.target.value)} /></div>
              </div>
              <div>
                <label className="form-label">Checklist Items</label>
                {items.map((item, i) => (
                  <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', width: 20 }}>{i + 1}.</span>
                    <input className="form-input" value={item.description} placeholder="Item description"
                      onChange={(e) => setItems((prev) => prev.map((it, idx) => idx === i ? { ...it, description: e.target.value } : it))}
                      style={{ flex: 1 }}
                    />
                    <label style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 10, whiteSpace: 'nowrap' }}>
                      <input type="checkbox" checked={item.required_photo} onChange={(e) => setItems((prev) => prev.map((it, idx) => idx === i ? { ...it, required_photo: e.target.checked } : it))} />
                      Photo
                    </label>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 10, whiteSpace: 'nowrap' }}>
                      <input type="checkbox" checked={item.auto_detect} onChange={(e) => setItems((prev) => prev.map((it, idx) => idx === i ? { ...it, auto_detect: e.target.checked } : it))} />
                      Detect
                    </label>
                    {items.length > 1 && (
                      <button className="btn btn-ghost btn-icon" onClick={() => setItems((prev) => prev.filter((_, idx) => idx !== i))}><X size={12} /></button>
                    )}
                  </div>
                ))}
                <button className="btn btn-ghost btn-sm" onClick={() => setItems((prev) => [...prev, { description: '', required_photo: false, auto_detect: false }])}>
                  <Plus size={12} /> Add Item
                </button>
              </div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
              <button className="btn btn-ghost" onClick={() => setShowModal(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={handleSave} disabled={saving}>{saving ? 'Saving...' : editing ? 'Update' : 'Create'}</button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

// ── Compliance Tab ───────────────────────────────────────────

function ComplianceTab() {
  const [stats, setStats] = useState<ComplianceStats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getComplianceStats({ days: 30 })
      .then((r) => setStats(r.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-muted)' }}>Loading compliance data...</div>
  if (!stats) return <div className="empty-state"><p>No compliance data available</p></div>

  return (
    <div>
      <div className="stats-grid" style={{ marginBottom: 20 }}>
        <div className="stat-card"><div className="stat-value">{stats.total_instances}</div><div className="stat-label">Total Checklists</div></div>
        <div className="stat-card"><div className="stat-value" style={{ color: 'var(--success)' }}>{stats.completed}</div><div className="stat-label">Completed</div></div>
        <div className="stat-card"><div className="stat-value" style={{ color: 'var(--amber)' }}>{stats.completion_rate.toFixed(1)}%</div><div className="stat-label">Completion Rate</div></div>
        <div className="stat-card"><div className="stat-value" style={{ color: 'var(--danger)' }}>{stats.overdue}</div><div className="stat-label">Overdue</div></div>
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-header"><span className="card-title">By Plant</span></div>
          {stats.by_plant.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={stats.by_plant.map((p) => ({ ...p, name: p.plant_site, rate: p.total > 0 ? Math.round(p.completed / p.total * 100) : 0 }))} margin={{ top: 5, right: 20, left: -10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-dim)" vertical={false} />
                <XAxis dataKey="name" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 10 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Bar dataKey="completed" name="Completed" fill="var(--success)" radius={[3, 3, 0, 0]} />
                <Bar dataKey="total" name="Total" fill="var(--bg-hover)" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>No data</div>}
        </div>

        <div className="card">
          <div className="card-header"><span className="card-title">By Shift</span></div>
          {stats.by_shift.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={stats.by_shift.map((s) => ({ ...s, name: s.shift, rate: s.total > 0 ? Math.round(s.completed / s.total * 100) : 0 }))} margin={{ top: 5, right: 20, left: -10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-dim)" vertical={false} />
                <XAxis dataKey="name" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 10 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Bar dataKey="completed" name="Completed" fill="var(--amber)" radius={[3, 3, 0, 0]} />
                <Bar dataKey="total" name="Total" fill="var(--bg-hover)" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>No data</div>}
        </div>
      </div>
    </div>
  )
}

// ── Main Page ────────────────────────────────────────────────

export default function Checklists() {
  const [tab, setTab] = useState<'active' | 'templates' | 'compliance'>('active')

  const tabs = [
    { key: 'active' as const, label: 'Active', icon: ClipboardCheck },
    { key: 'templates' as const, label: 'Templates', icon: ListChecks },
    { key: 'compliance' as const, label: 'Compliance', icon: Shield },
  ]

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">Inspection Checklists</h1>
        <p className="page-subtitle">Manage inspections, templates, and compliance tracking</p>
      </div>

      <div style={{ display: 'flex', gap: 0, borderBottom: '1px solid var(--border-dim)', marginBottom: 20 }}>
        {tabs.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            style={{
              padding: '10px 20px', fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: 600, letterSpacing: '0.04em',
              color: tab === key ? 'var(--amber)' : 'var(--text-muted)',
              borderBottom: `2px solid ${tab === key ? 'var(--amber)' : 'transparent'}`,
              transition: 'all var(--transition-fast)', display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', background: 'transparent',
            }}
          >
            <Icon size={14} /> {label}
          </button>
        ))}
      </div>

      {tab === 'active' && <ActiveTab />}
      {tab === 'templates' && <TemplatesTab />}
      {tab === 'compliance' && <ComplianceTab />}
    </div>
  )
}
