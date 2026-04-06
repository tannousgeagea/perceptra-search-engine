import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Bell, Shield, Plus, Trash2, Edit2, Check, CheckCheck,
  AlertTriangle, AlertCircle, Info, X, Power, Filter, Calendar,
  MapPin, RefreshCw,
} from 'lucide-react'
import type { AlertResponse, AlertRule, PaginationMeta, CreateAlertRuleRequest } from '../types/api'
import {
  getAlerts, acknowledgeAlert, acknowledgeAllAlerts,
  getAlertRules, createAlertRule, updateAlertRule, deleteAlertRule,
} from '../api/client'
import { useAlerts } from '../context/AlertContext'

function extractError(err: unknown): string {
  if (typeof err === 'object' && err !== null && 'response' in err) {
    const r = (err as { response?: { data?: { detail?: string } } }).response
    if (r?.data?.detail) return r.data.detail
  }
  return 'An error occurred'
}

// ── Severity visual config ───────────────────────────────────

const SEVERITY_MAP: Record<string, { icon: typeof AlertTriangle; color: string; badge: string; label: string }> = {
  critical: { icon: AlertTriangle, color: 'var(--danger)',  badge: 'badge-danger',  label: 'CRITICAL' },
  warning:  { icon: AlertCircle,   color: 'var(--warning)', badge: 'badge-amber',   label: 'WARNING' },
  info:     { icon: Info,          color: 'var(--info)',    badge: 'badge-cyan',    label: 'INFO' },
}

// ── Filter bar component ─────────────────────────────────────

function FilterBar({ children, count }: { children: React.ReactNode; count?: number }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px',
      background: 'var(--bg-elevated)', border: '1px solid var(--border-dim)',
      borderRadius: 'var(--radius-lg)', marginBottom: 20,
      flexWrap: 'wrap',
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6,
        paddingRight: 12, borderRight: '1px solid var(--border-dim)',
        marginRight: 2,
      }}>
        <Filter size={12} style={{ color: 'var(--text-muted)' }} />
        <span style={{
          fontFamily: 'var(--font-display)', fontSize: 10, fontWeight: 600,
          letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--text-muted)',
        }}>
          Filters
        </span>
      </div>
      {children}
      {count !== undefined && (
        <span style={{
          marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: 11,
          color: 'var(--text-muted)', letterSpacing: '0.04em',
        }}>
          {count.toLocaleString()} result{count !== 1 ? 's' : ''}
        </span>
      )}
    </div>
  )
}

function FilterSelect({ value, onChange, options, placeholder, icon: Icon, width = 140 }: {
  value: string
  onChange: (v: string) => void
  options: { value: string; label: string }[]
  placeholder: string
  icon?: typeof Bell
  width?: number
}) {
  return (
    <div style={{ position: 'relative' }}>
      {Icon && (
        <Icon size={12} style={{
          position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)',
          color: 'var(--text-muted)', pointerEvents: 'none',
        }} />
      )}
      <select
        className="form-input form-select"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          width,
          height: 34,
          padding: Icon ? '0 32px 0 30px' : '0 32px 0 12px',
          fontSize: 12,
          fontFamily: 'var(--font-mono)',
          background: 'var(--bg-surface)',
          borderColor: value ? 'var(--border-bright)' : 'var(--border-dim)',
        }}
      >
        <option value="">{placeholder}</option>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  )
}

function FilterInput({ value, onChange, placeholder, icon: Icon, width = 160, type = 'text' }: {
  value: string
  onChange: (v: string) => void
  placeholder: string
  icon?: typeof Bell
  width?: number
  type?: string
}) {
  return (
    <div style={{ position: 'relative' }}>
      {Icon && (
        <Icon size={12} style={{
          position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)',
          color: 'var(--text-muted)', pointerEvents: 'none',
        }} />
      )}
      <input
        className="form-input"
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        style={{
          width,
          height: 34,
          padding: Icon ? '0 12px 0 30px' : '0 12px',
          fontSize: 12,
          fontFamily: 'var(--font-mono)',
          background: 'var(--bg-surface)',
          borderColor: value ? 'var(--border-bright)' : 'var(--border-dim)',
        }}
      />
    </div>
  )
}

// ── Alert History Tab ────────────────────────────────────────

function AlertHistoryTab() {
  const navigate = useNavigate()
  const { refreshUnreadCount } = useAlerts()
  const [alerts, setAlerts] = useState<AlertResponse[]>([])
  const [pagination, setPagination] = useState<PaginationMeta | null>(null)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [severity, setSeverity] = useState('')
  const [acknowledged, setAcknowledged] = useState<string>('')
  const [plantSite, setPlantSite] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [ackingId, setAckingId] = useState<number | null>(null)

  const fetchAlerts = () => {
    setLoading(true)
    const params: Record<string, unknown> = { page, page_size: 20 }
    if (severity) params.severity = severity
    if (acknowledged === 'true') params.is_acknowledged = true
    if (acknowledged === 'false') params.is_acknowledged = false
    if (plantSite) params.plant_site = plantSite
    if (dateFrom) params.date_from = dateFrom
    if (dateTo) params.date_to = dateTo
    getAlerts(params as Parameters<typeof getAlerts>[0])
      .then((r) => { setAlerts(r.data.items); setPagination(r.data.pagination) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchAlerts() }, [page, severity, acknowledged, plantSite, dateFrom, dateTo])

  const handleAck = async (id: number) => {
    setAckingId(id)
    try {
      await acknowledgeAlert(id)
      setAlerts((prev) => prev.map((a) => a.id === id ? { ...a, is_acknowledged: true } : a))
      refreshUnreadCount()
    } catch { /* ignore */ }
    setAckingId(null)
  }

  const handleAckAll = async () => {
    try {
      await acknowledgeAllAlerts()
      fetchAlerts()
      refreshUnreadCount()
    } catch { /* ignore */ }
  }

  const hasActiveFilters = severity || acknowledged || plantSite || dateFrom || dateTo
  const clearFilters = () => {
    setSeverity(''); setAcknowledged(''); setPlantSite(''); setDateFrom(''); setDateTo(''); setPage(1)
  }

  const formatDate = (d: string) => {
    const dt = new Date(d)
    return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  }

  return (
    <div>
      {/* Filter bar */}
      <FilterBar count={pagination?.total_items}>
        <FilterSelect
          value={severity}
          onChange={(v) => { setSeverity(v); setPage(1) }}
          options={[
            { value: 'critical', label: 'Critical' },
            { value: 'warning', label: 'Warning' },
            { value: 'info', label: 'Info' },
          ]}
          placeholder="All Severity"
          icon={AlertTriangle}
          width={150}
        />
        <FilterSelect
          value={acknowledged}
          onChange={(v) => { setAcknowledged(v); setPage(1) }}
          options={[
            { value: 'false', label: 'Unacknowledged' },
            { value: 'true', label: 'Acknowledged' },
          ]}
          placeholder="All Status"
          icon={Bell}
          width={165}
        />
        <FilterInput
          value={plantSite}
          onChange={(v) => { setPlantSite(v); setPage(1) }}
          placeholder="Plant site..."
          icon={MapPin}
          width={150}
        />
        <FilterInput
          value={dateFrom}
          onChange={(v) => { setDateFrom(v); setPage(1) }}
          placeholder="From"
          icon={Calendar}
          width={150}
          type="date"
        />
        <FilterInput
          value={dateTo}
          onChange={(v) => { setDateTo(v); setPage(1) }}
          placeholder="To"
          width={140}
          type="date"
        />
        {hasActiveFilters && (
          <button className="btn btn-ghost btn-sm" onClick={clearFilters} style={{ color: 'var(--text-muted)', fontSize: 10 }}>
            <X size={11} /> Clear
          </button>
        )}
      </FilterBar>

      {/* Actions row */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
        <button className="btn btn-secondary btn-sm" onClick={handleAckAll}>
          <CheckCheck size={12} /> Acknowledge All
        </button>
      </div>

      {/* Table */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div className="table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ width: 90 }}>Severity</th>
                <th>Label</th>
                <th style={{ width: 85 }}>Confidence</th>
                <th>Plant Site</th>
                <th>Rule</th>
                <th style={{ width: 85 }}>Status</th>
                <th style={{ width: 140 }}>Created</th>
                <th style={{ width: 60 }}></th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={8} style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                  <RefreshCw size={16} style={{ animation: 'spin 1s linear infinite', display: 'inline-block', marginRight: 8, verticalAlign: 'middle' }} />
                  Loading alerts...
                </td></tr>
              ) : alerts.length === 0 ? (
                <tr><td colSpan={8} style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                  {hasActiveFilters ? 'No alerts match your filters' : 'No alerts yet'}
                </td></tr>
              ) : alerts.map((alert) => {
                const sev = SEVERITY_MAP[alert.severity] ?? SEVERITY_MAP.info
                return (
                  <tr
                    key={alert.id}
                    style={{ cursor: 'pointer', transition: 'background var(--transition-fast)' }}
                    onClick={() => navigate(`/media/detections/${alert.detection_id}`)}
                    onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--bg-hover)' }}
                    onMouseLeave={(e) => { e.currentTarget.style.background = '' }}
                  >
                    <td>
                      <span className={`badge ${sev.badge}`} style={{ fontSize: 9 }}>
                        {sev.label}
                      </span>
                    </td>
                    <td style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{alert.label}</td>
                    <td>
                      <span style={{
                        fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 600,
                        color: alert.confidence >= 0.85 ? 'var(--danger)' : alert.confidence >= 0.6 ? 'var(--amber)' : 'var(--text-secondary)',
                      }}>
                        {(alert.confidence * 100).toFixed(1)}%
                      </span>
                    </td>
                    <td style={{ color: 'var(--text-secondary)', fontSize: 12 }}>
                      {alert.plant_site ? (
                        <span className="flex items-center gap-1"><MapPin size={10} style={{ color: 'var(--text-muted)' }} />{alert.plant_site}</span>
                      ) : '—'}
                    </td>
                    <td style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{alert.alert_rule_name ?? '—'}</td>
                    <td>
                      {alert.is_acknowledged ? (
                        <span className="badge badge-success" style={{ fontSize: 9 }}>ACK</span>
                      ) : (
                        <span className="badge badge-danger" style={{ fontSize: 9, animation: 'glow-pulse 2s ease-in-out infinite' }}>ACTIVE</span>
                      )}
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>{formatDate(alert.created_at)}</td>
                    <td onClick={(e) => e.stopPropagation()}>
                      {!alert.is_acknowledged && (
                        <button
                          className="btn btn-ghost btn-icon btn-sm"
                          onClick={() => handleAck(alert.id)}
                          disabled={ackingId === alert.id}
                          title="Acknowledge"
                          style={{ padding: 4 }}
                        >
                          <Check size={14} style={{ color: 'var(--success)' }} />
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      {pagination && pagination.total_pages > 1 && (
        <div style={{ display: 'flex', justifyContent: 'center', gap: 8, marginTop: 16, alignItems: 'center' }}>
          <button className="btn btn-ghost btn-sm" disabled={!pagination.has_previous} onClick={() => setPage((p) => p - 1)}>Prev</button>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)' }}>
            Page {pagination.page} of {pagination.total_pages}
          </span>
          <button className="btn btn-ghost btn-sm" disabled={!pagination.has_next} onClick={() => setPage((p) => p + 1)}>Next</button>
        </div>
      )}
    </div>
  )
}

// ── Alert Rules Tab ──────────────────────────────────────────

function RuleModal({ rule, onClose, onSave }: {
  rule: AlertRule | null
  onClose: () => void
  onSave: () => void
}) {
  const [name, setName] = useState(rule?.name ?? '')
  const [labelPattern, setLabelPattern] = useState(rule?.label_pattern ?? '')
  const [minConfidence, setMinConfidence] = useState(rule?.min_confidence ?? 0.5)
  const [plantSite, setPlantSite] = useState(rule?.plant_site ?? '')
  const [webhookUrl, setWebhookUrl] = useState(rule?.webhook_url ?? '')
  const [notifyWebsocket, setNotifyWebsocket] = useState(rule?.notify_websocket ?? true)
  const [cooldownMinutes, setCooldownMinutes] = useState(rule?.cooldown_minutes ?? 5)
  const [isActive, setIsActive] = useState(rule?.is_active ?? true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const handleSave = async () => {
    if (!name.trim() || !labelPattern.trim()) {
      setError('Name and label pattern are required')
      return
    }
    setSaving(true)
    setError('')
    try {
      const data: CreateAlertRuleRequest = {
        name: name.trim(),
        label_pattern: labelPattern.trim(),
        min_confidence: minConfidence,
        plant_site: plantSite.trim() || null,
        webhook_url: webhookUrl.trim() || null,
        notify_websocket: notifyWebsocket,
        cooldown_minutes: cooldownMinutes,
        is_active: isActive,
      }
      if (rule) {
        await updateAlertRule(rule.id, data)
      } else {
        await createAlertRule(data)
      }
      onSave()
    } catch (err) {
      setError(extractError(err))
    }
    setSaving(false)
  }

  return (
    <>
      <div className="modal-overlay" onClick={onClose} />
      <div className="modal" style={{ maxWidth: 520 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h3 className="modal-title" style={{ fontSize: 14 }}>{rule ? 'Edit Alert Rule' : 'New Alert Rule'}</h3>
          <button className="btn btn-ghost btn-icon" onClick={onClose}><X size={16} /></button>
        </div>

        {error && (
          <div style={{ padding: '10px 14px', marginBottom: 16, background: 'var(--danger-dim)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 'var(--radius-md)', fontSize: 12, color: 'var(--danger)', fontFamily: 'var(--font-mono)' }}>
            {error}
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="form-group">
            <label className="form-label">Rule Name</label>
            <input className="form-input" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. High-severity rust alert" />
          </div>

          <div className="form-group">
            <label className="form-label">Label Pattern (regex)</label>
            <input className="form-input" value={labelPattern} onChange={(e) => setLabelPattern(e.target.value)} placeholder="e.g. rust|crack|corrosion" />
            <span style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
              Uses regex matching — separate multiple labels with |
            </span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <div className="form-group">
              <label className="form-label">Min Confidence</label>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <input type="range" min="0" max="1" step="0.05" value={minConfidence}
                  onChange={(e) => setMinConfidence(parseFloat(e.target.value))}
                  style={{ flex: 1, accentColor: 'var(--amber)' }}
                />
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600,
                  color: minConfidence >= 0.8 ? 'var(--danger)' : minConfidence >= 0.5 ? 'var(--amber)' : 'var(--text-secondary)',
                  minWidth: 36, textAlign: 'right',
                }}>
                  {(minConfidence * 100).toFixed(0)}%
                </span>
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">Cooldown (min)</label>
              <input className="form-input" type="number" min="0" value={cooldownMinutes}
                onChange={(e) => setCooldownMinutes(parseInt(e.target.value) || 0)}
              />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">Plant Site <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>— optional</span></label>
            <input className="form-input" value={plantSite} onChange={(e) => setPlantSite(e.target.value)} placeholder="Leave empty for all plants" />
          </div>

          <div className="form-group">
            <label className="form-label">Webhook URL <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>— optional</span></label>
            <input className="form-input" value={webhookUrl} onChange={(e) => setWebhookUrl(e.target.value)} placeholder="https://hooks.slack.com/..." />
          </div>

          <div style={{
            display: 'flex', gap: 20, padding: '12px 14px',
            background: 'var(--bg-elevated)', borderRadius: 'var(--radius-md)',
            border: '1px solid var(--border-dim)',
          }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, cursor: 'pointer', color: 'var(--text-secondary)' }}>
              <input type="checkbox" checked={notifyWebsocket} onChange={(e) => setNotifyWebsocket(e.target.checked)}
                style={{ accentColor: 'var(--amber)' }}
              />
              Push notifications
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, cursor: 'pointer', color: 'var(--text-secondary)' }}>
              <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)}
                style={{ accentColor: 'var(--success)' }}
              />
              Active
            </label>
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 24, paddingTop: 16, borderTop: '1px solid var(--border-dim)' }}>
          <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
            {saving ? 'Saving...' : rule ? 'Update Rule' : 'Create Rule'}
          </button>
        </div>
      </div>
    </>
  )
}

function AlertRulesTab() {
  const [rules, setRules] = useState<AlertRule[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editing, setEditing] = useState<AlertRule | null>(null)
  const [deleting, setDeleting] = useState<number | null>(null)

  const fetchRules = () => {
    setLoading(true)
    getAlertRules()
      .then((r) => setRules(r.data.items))
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchRules() }, [])

  const handleDelete = async (id: number) => {
    setDeleting(id)
    try {
      await deleteAlertRule(id)
      setRules((prev) => prev.filter((r) => r.id !== id))
    } catch { /* ignore */ }
    setDeleting(null)
  }

  const handleToggleActive = async (rule: AlertRule) => {
    try {
      await updateAlertRule(rule.id, { is_active: !rule.is_active })
      setRules((prev) => prev.map((r) => r.id === rule.id ? { ...r, is_active: !r.is_active } : r))
    } catch { /* ignore */ }
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <p style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', letterSpacing: '0.02em' }}>
          Rules trigger alerts when new detections match label patterns above confidence thresholds.
        </p>
        <button className="btn btn-primary btn-sm" onClick={() => { setEditing(null); setShowModal(true) }}>
          <Plus size={12} /> New Rule
        </button>
      </div>

      {loading ? (
        <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
          <RefreshCw size={16} style={{ animation: 'spin 1s linear infinite', display: 'inline-block', marginRight: 8, verticalAlign: 'middle' }} />
          Loading rules...
        </div>
      ) : rules.length === 0 ? (
        <div className="empty-state" style={{ padding: '48px 20px' }}>
          <div className="empty-state-icon"><Shield size={28} /></div>
          <p style={{ color: 'var(--text-secondary)', marginBottom: 4 }}>No alert rules configured</p>
          <p style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 16, fontFamily: 'var(--font-mono)' }}>
            Create a rule to start receiving defect alerts
          </p>
          <button className="btn btn-primary btn-sm" onClick={() => { setEditing(null); setShowModal(true) }}>
            <Plus size={12} /> Create First Rule
          </button>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {rules.map((rule) => (
            <div
              key={rule.id}
              className="card"
              style={{
                padding: '14px 18px',
                display: 'flex', alignItems: 'center', gap: 14,
                opacity: rule.is_active ? 1 : 0.5,
                borderLeft: `3px solid ${rule.is_active ? 'var(--success)' : 'var(--border-dim)'}`,
                transition: 'all var(--transition-fast)',
              }}
            >
              <button
                className="btn btn-ghost btn-icon"
                onClick={() => handleToggleActive(rule)}
                title={rule.is_active ? 'Deactivate' : 'Activate'}
                style={{ padding: 4 }}
              >
                <Power size={15} style={{ color: rule.is_active ? 'var(--success)' : 'var(--text-muted)' }} />
              </button>

              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                  <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{rule.name}</span>
                  <code style={{
                    fontSize: 11, fontFamily: 'var(--font-mono)', padding: '2px 8px',
                    background: 'var(--amber-glow)', color: 'var(--amber)',
                    borderRadius: 'var(--radius-sm)', border: '1px solid rgba(245,158,11,0.15)',
                  }}>
                    {rule.label_pattern}
                  </code>
                </div>
                <div style={{ display: 'flex', gap: 16, fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                  <span>&#8805; {(rule.min_confidence * 100).toFixed(0)}%</span>
                  <span>{rule.plant_site ?? 'All plants'}</span>
                  <span>{rule.cooldown_minutes}m cooldown</span>
                  {rule.webhook_url && <span style={{ color: 'var(--cyan-400)' }}>Webhook</span>}
                  {rule.notify_websocket && <span style={{ color: 'var(--success)' }}>Push</span>}
                </div>
              </div>

              <button className="btn btn-ghost btn-icon" onClick={() => { setEditing(rule); setShowModal(true) }} title="Edit" style={{ padding: 4 }}>
                <Edit2 size={13} style={{ color: 'var(--text-secondary)' }} />
              </button>
              <button
                className="btn btn-ghost btn-icon"
                onClick={() => handleDelete(rule.id)}
                disabled={deleting === rule.id}
                title="Delete"
                style={{ padding: 4 }}
              >
                <Trash2 size={13} style={{ color: 'var(--danger)' }} />
              </button>
            </div>
          ))}
        </div>
      )}

      {showModal && (
        <RuleModal
          rule={editing}
          onClose={() => setShowModal(false)}
          onSave={() => { setShowModal(false); fetchRules() }}
        />
      )}
    </div>
  )
}

// ── Main Page ────────────────────────────────────────────────

export default function Alerts() {
  const { unreadCount } = useAlerts()
  const [tab, setTab] = useState<'history' | 'rules'>('history')

  return (
    <div className="page-container">
      <div className="page-header flex items-center justify-between">
        <div>
          <h1 className="page-title">Alerts</h1>
          <p className="page-subtitle">Real-time defect notifications & rule configuration</p>
        </div>
        {unreadCount > 0 && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px',
            background: 'var(--danger-dim)', border: '1px solid rgba(239,68,68,0.25)',
            borderRadius: 'var(--radius-md)',
          }}>
            <span style={{
              width: 8, height: 8, borderRadius: '50%', background: 'var(--danger)',
              animation: 'glow-pulse 2s ease-in-out infinite',
            }} />
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--danger)', fontWeight: 600 }}>
              {unreadCount} unacknowledged
            </span>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="tab-bar">
        {([
          { key: 'history' as const, icon: Bell, label: 'Alert History' },
          { key: 'rules' as const, icon: Shield, label: 'Alert Rules' },
        ]).map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            className={`tab-btn${tab === key ? ' active' : ''}`}
            onClick={() => setTab(key)}
          >
            <Icon size={13} />
            {label}
          </button>
        ))}
      </div>

      {tab === 'history' ? <AlertHistoryTab /> : <AlertRulesTab />}
    </div>
  )
}
