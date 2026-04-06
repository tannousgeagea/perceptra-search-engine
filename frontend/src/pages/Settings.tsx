import { useEffect, useState, type FormEvent } from 'react'
import {
  KeyRound, Plus, Trash2, Eye, EyeOff, Copy, Check,
  AlertCircle, User, Shield, Clock, Activity, Lock,
} from 'lucide-react'
import { getApiKeys, createApiKey, updateApiKey, deleteApiKey, changePassword } from '../api/client'
import { useAuth } from '../context/AuthContext'
import type { ApiKey, CreateApiKeyRequest, CreateApiKeyResponse, ApiKeyPermission } from '../types/api'

function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    navigator.clipboard.writeText(value).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }
  return (
    <button className="btn btn-ghost btn-icon btn-sm" onClick={copy} title="Copy">
      {copied ? <Check size={12} style={{ color: 'var(--success)' }} /> : <Copy size={12} />}
    </button>
  )
}

function PermissionBadge({ perm }: { perm: ApiKeyPermission }) {
  const map: Record<ApiKeyPermission, string> = {
    read:  'badge-cyan',
    write: 'badge-amber',
    admin: 'badge-danger',
  }
  return <span className={`badge ${map[perm]}`}>{perm}</span>
}

interface CreateKeyModalProps {
  onClose: () => void
  onCreated: (key: CreateApiKeyResponse) => void
}

function CreateKeyModal({ onClose, onCreated }: CreateKeyModalProps) {
  const [name, setName]               = useState('')
  const [permissions, setPermissions] = useState<ApiKeyPermission>('read')
  const [rateMin, setRateMin]         = useState('')
  const [rateHour, setRateHour]       = useState('')
  const [expiresAt, setExpiresAt]     = useState('')
  const [loading, setLoading]         = useState(false)
  const [error, setError]             = useState('')

  const handleCreate = async () => {
    if (!name.trim()) { setError('Name is required'); return }
    setLoading(true); setError('')
    try {
      const req: CreateApiKeyRequest = {
        name: name.trim(),
        permissions,
        ...(rateMin ? { rate_limit_per_minute: parseInt(rateMin) } : {}),
        ...(rateHour ? { rate_limit_per_hour: parseInt(rateHour) } : {}),
        ...(expiresAt ? { expires_at: new Date(expiresAt).toISOString() } : {}),
      }
      const res = await createApiKey(req)
      onCreated(res.data)
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? 'Failed to create API key.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <div className="modal-title">Create API Key</div>
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
              placeholder="e.g. Production Key, CI/CD Key"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
            />
          </div>
          <div className="form-group">
            <label className="form-label">Permission Level</label>
            <select
              className="form-input form-select"
              value={permissions}
              onChange={(e) => setPermissions(e.target.value as ApiKeyPermission)}
            >
              <option value="read">Read — Search and view only</option>
              <option value="write">Write — Upload and manage media</option>
              <option value="admin">Admin — Full access</option>
            </select>
          </div>
          <div className="grid-2">
            <div className="form-group">
              <label className="form-label">Rate Limit / Min</label>
              <input
                type="number"
                className="form-input"
                placeholder="Unlimited"
                value={rateMin}
                onChange={(e) => setRateMin(e.target.value)}
                style={{ fontFamily: 'var(--font-mono)' }}
                min="1"
              />
            </div>
            <div className="form-group">
              <label className="form-label">Rate Limit / Hour</label>
              <input
                type="number"
                className="form-input"
                placeholder="Unlimited"
                value={rateHour}
                onChange={(e) => setRateHour(e.target.value)}
                style={{ fontFamily: 'var(--font-mono)' }}
                min="1"
              />
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">Expires At <span style={{ opacity: 0.5, textTransform: 'none', letterSpacing: 0 }}>(optional)</span></label>
            <input
              type="date"
              className="form-input"
              value={expiresAt}
              onChange={(e) => setExpiresAt(e.target.value)}
              min={new Date().toISOString().slice(0, 10)}
            />
          </div>
        </div>
        <div className="flex justify-end gap-3 mt-6">
          <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={handleCreate} disabled={loading}>
            {loading ? 'Creating...' : 'Create Key'}
          </button>
        </div>
      </div>
    </div>
  )
}

interface NewKeyDisplayProps {
  keyData: CreateApiKeyResponse
  onDone: () => void
}

function NewKeyDisplay({ keyData, onDone }: NewKeyDisplayProps) {
  const [visible, setVisible] = useState(false)
  return (
    <div className="modal-overlay">
      <div className="modal">
        <div style={{
          textAlign: 'center', marginBottom: 20,
          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10,
        }}>
          <div style={{
            width: 48, height: 48, borderRadius: '50%',
            background: 'var(--success-dim)', border: '1px solid rgba(16,185,129,0.3)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Check size={22} style={{ color: 'var(--success)' }} />
          </div>
          <div>
            <div className="modal-title" style={{ marginBottom: 4 }}>API Key Created</div>
            <p style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
              Save this secret now. It will <strong style={{ color: 'var(--danger)' }}>not be shown again</strong>.
            </p>
          </div>
        </div>

        <div style={{
          background: 'var(--bg-void)',
          border: '1px solid var(--border-bright)',
          borderRadius: 'var(--radius-md)',
          padding: '12px 14px',
          marginBottom: 16,
        }}>
          <div style={{ fontSize: 11, fontFamily: 'var(--font-display)', fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 8 }}>
            API Key
          </div>
          <div className="flex items-center gap-2">
            <code style={{ flex: 1, fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-primary)', wordBreak: 'break-all' }}>
              {visible ? keyData.secret : '•'.repeat(Math.min(keyData.secret.length, 40))}
            </code>
            <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setVisible((v) => !v)}>
              {visible ? <EyeOff size={13} /> : <Eye size={13} />}
            </button>
            <CopyButton value={keyData.secret} />
          </div>
        </div>

        <div style={{
          background: 'var(--warning-dim)', border: '1px solid rgba(245,158,11,0.2)',
          borderRadius: 'var(--radius-md)', padding: '10px 12px',
          fontSize: 12, color: 'var(--warning)', marginBottom: 20,
          display: 'flex', alignItems: 'flex-start', gap: 8,
        }}>
          <AlertCircle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
          <span>Store this key securely. It grants <strong>{keyData.permissions}</strong> access to your tenant data.</span>
        </div>

        <button className="btn btn-primary w-full" onClick={onDone} style={{ justifyContent: 'center' }}>
          Done
        </button>
      </div>
    </div>
  )
}

function ChangePasswordCard() {
  const [current, setCurrent]     = useState('')
  const [next, setNext]           = useState('')
  const [confirm, setConfirm]     = useState('')
  const [showPw, setShowPw]       = useState(false)
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState('')
  const [success, setSuccess]     = useState('')

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!current || !next) { setError('All fields are required'); return }
    if (next !== confirm) { setError('New passwords do not match'); return }
    setError(''); setSuccess(''); setLoading(true)
    try {
      await changePassword({ current_password: current, new_password: next })
      setSuccess('Password changed successfully.')
      setCurrent(''); setNext(''); setConfirm('')
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail ?? 'Failed to change password.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card anim-3">
      <div className="card-header">
        <span className="card-title flex items-center gap-2">
          <Lock size={12} />
          Change Password
        </span>
      </div>
      {error && (
        <div className="alert alert-error mb-4" style={{ fontSize: 13 }}>
          <AlertCircle size={14} />
          <span>{error}</span>
        </div>
      )}
      {success && (
        <div className="alert alert-success mb-4" style={{ fontSize: 13 }}>
          <Check size={14} />
          <span>{success}</span>
        </div>
      )}
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div className="form-group">
          <label className="form-label">Current Password</label>
          <div style={{ position: 'relative' }}>
            <input
              type={showPw ? 'text' : 'password'}
              className="form-input"
              placeholder="••••••••"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              style={{ paddingRight: 44 }}
              autoComplete="current-password"
            />
            <button
              type="button"
              onClick={() => setShowPw((v) => !v)}
              style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', display: 'flex' }}
            >
              {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
          </div>
        </div>
        <div className="form-group">
          <label className="form-label">New Password</label>
          <input
            type={showPw ? 'text' : 'password'}
            className="form-input"
            placeholder="Min 8 characters"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            autoComplete="new-password"
          />
        </div>
        <div className="form-group">
          <label className="form-label">Confirm New Password</label>
          <input
            type={showPw ? 'text' : 'password'}
            className="form-input"
            placeholder="Repeat new password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            autoComplete="new-password"
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="btn btn-primary"
          style={{ alignSelf: 'flex-end' }}
        >
          {loading ? 'Updating...' : 'Update Password'}
        </button>
      </form>
    </div>
  )
}

export default function Settings() {
  const { auth, session, displayName } = useAuth()

  const [apiKeys, setApiKeys]         = useState<ApiKey[]>([])
  const [loadingKeys, setLoadingKeys] = useState(false)
  const [showCreate, setShowCreate]   = useState(false)
  const [newKey, setNewKey]           = useState<CreateApiKeyResponse | null>(null)

  const fetchKeys = async () => {
    setLoadingKeys(true)
    try {
      const r = await getApiKeys()
      setApiKeys(r.data)
    } catch { /* silent */ }
    finally { setLoadingKeys(false) }
  }

  useEffect(() => { fetchKeys() }, [])

  const handleToggleActive = async (key: ApiKey) => {
    try {
      await updateApiKey(key.id, { is_active: !key.is_active })
      fetchKeys()
    } catch { /* ignore */ }
  }

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`Revoke API key "${name}"? This cannot be undone.`)) return
    try { await deleteApiKey(id); fetchKeys() } catch { /* ignore */ }
  }

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">Configuration</h1>
        <p className="page-subtitle">Profile settings & API key management</p>
      </div>

      <div className="grid-2" style={{ gridTemplateColumns: '340px 1fr', gap: 24, alignItems: 'start' }}>
        {/* Profile card */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="card anim-1">
            <div className="card-header">
              <span className="card-title flex items-center gap-2">
                <User size={12} />
                Profile
              </span>
            </div>
            <div style={{ textAlign: 'center', marginBottom: 20 }}>
              <div style={{
                width: 72, height: 72, borderRadius: '50%',
                background: 'linear-gradient(135deg, var(--amber-700), var(--amber))',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                margin: '0 auto 12px',
                fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 28, color: '#000',
                boxShadow: 'var(--shadow-amber)',
              }}>
                {displayName[0]?.toUpperCase() ?? 'I'}
              </div>
              <div style={{ fontWeight: 600, fontSize: 16, color: 'var(--text-primary)', marginBottom: 2 }}>
                {displayName}
              </div>
              <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', letterSpacing: '0.08em' }}>
                {session?.role?.toUpperCase() ?? 'INSPECTOR'}
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '10px 12px',
                background: 'var(--bg-elevated)', border: '1px solid var(--border-dim)',
                borderRadius: 'var(--radius-md)',
              }}>
                <span style={{ fontSize: 12, color: 'var(--text-muted)', fontFamily: 'var(--font-display)', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                  Auth Mode
                </span>
                <span className={`badge ${auth?.mode === 'apikey' ? 'badge-amber' : 'badge-cyan'}`}>
                  {auth?.mode === 'apikey' ? 'API Key' : 'JWT'}
                </span>
              </div>

              {(session?.tenant || auth?.tenantId) && (
                <div style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '10px 12px',
                  background: 'var(--bg-elevated)', border: '1px solid var(--border-dim)',
                  borderRadius: 'var(--radius-md)',
                }}>
                  <span style={{ fontSize: 12, color: 'var(--text-muted)', fontFamily: 'var(--font-display)', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                    Tenant
                  </span>
                  <div className="flex items-center gap-1">
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)' }}>
                      {session?.tenant?.name ?? auth?.tenantId?.slice(0, 8) + '…'}
                    </span>
                    {(session?.tenant?.id || auth?.tenantId) && (
                      <CopyButton value={session?.tenant?.id ?? auth?.tenantId ?? ''} />
                    )}
                  </div>
                </div>
              )}

              {session?.role && (
                <div style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '10px 12px',
                  background: 'var(--bg-elevated)', border: '1px solid var(--border-dim)',
                  borderRadius: 'var(--radius-md)',
                }}>
                  <span style={{ fontSize: 12, color: 'var(--text-muted)', fontFamily: 'var(--font-display)', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                    Role
                  </span>
                  <span className={`badge ${session.role === 'admin' ? 'badge-amber' : session.role === 'operator' ? 'badge-cyan' : 'badge-dim'}`}>
                    {session.role}
                  </span>
                </div>
              )}

              {session?.api_key && (
                <div style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '10px 12px',
                  background: 'var(--bg-elevated)', border: '1px solid var(--border-dim)',
                  borderRadius: 'var(--radius-md)',
                }}>
                  <span style={{ fontSize: 12, color: 'var(--text-muted)', fontFamily: 'var(--font-display)', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                    Permissions
                  </span>
                  <span className="badge badge-cyan">
                    {session.api_key.permissions}
                  </span>
                </div>
              )}

              {session?.tenant?.location && (
                <div style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '10px 12px',
                  background: 'var(--bg-elevated)', border: '1px solid var(--border-dim)',
                  borderRadius: 'var(--radius-md)',
                }}>
                  <span style={{ fontSize: 12, color: 'var(--text-muted)', fontFamily: 'var(--font-display)', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                    Location
                  </span>
                  <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                    {session.tenant.location}
                  </span>
                </div>
              )}

              <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '10px 12px',
                background: 'var(--bg-elevated)', border: '1px solid var(--border-dim)',
                borderRadius: 'var(--radius-md)',
              }}>
                <span style={{ fontSize: 12, color: 'var(--text-muted)', fontFamily: 'var(--font-display)', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                  Status
                </span>
                <div className="flex items-center gap-2">
                  <span className="status-dot" />
                  <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--success)' }}>ONLINE</span>
                </div>
              </div>
            </div>
          </div>

          {/* API info card */}
          <div className="card anim-2">
            <div className="card-header">
              <span className="card-title flex items-center gap-2">
                <Activity size={12} />
                API Connection
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {[
                { label: 'Endpoint', value: 'http://localhost:8000' },
                { label: 'Version',  value: 'v1' },
                { label: 'Protocol', value: 'HTTP/1.1' },
              ].map(({ label, value }) => (
                <div key={label} className="flex items-center justify-between" style={{ fontSize: 12 }}>
                  <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-display)', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', fontSize: 11 }}>
                    {label}
                  </span>
                  <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{value}</code>
                </div>
              ))}
            </div>
          </div>

          {auth?.mode === 'jwt' && <ChangePasswordCard />}
        </div>

        {/* API Keys panel */}
        <div className="card anim-3">
          <div className="card-header">
            <span className="card-title flex items-center gap-2">
              <KeyRound size={12} />
              API Keys
              {apiKeys.length > 0 && (
                <span style={{
                  fontSize: 10, fontFamily: 'var(--font-mono)',
                  background: 'var(--bg-muted)', color: 'var(--text-muted)',
                  borderRadius: 3, padding: '1px 5px',
                }}>
                  {apiKeys.length}
                </span>
              )}
            </span>
            <button
              className="btn btn-primary btn-sm"
              onClick={() => setShowCreate(true)}
            >
              <Plus size={12} /> New Key
            </button>
          </div>

          {loadingKeys ? (
            <div className="flex items-center justify-center" style={{ padding: '40px 0' }}>
              <div className="spinner" />
            </div>
          ) : apiKeys.length === 0 ? (
            <div className="empty-state" style={{ padding: '40px 20px' }}>
              <div className="empty-state-icon"><KeyRound size={22} /></div>
              <p style={{ color: 'var(--text-secondary)', fontSize: 14, fontFamily: 'var(--font-display)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                No API Keys
              </p>
              <p style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 4 }}>
                Create a key to access the API programmatically.
              </p>
              <button className="btn btn-primary btn-sm mt-4" onClick={() => setShowCreate(true)}>
                <Plus size={12} /> Create Key
              </button>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
              {apiKeys.map((key) => (
                <div
                  key={key.id}
                  style={{
                    padding: '16px 0',
                    borderBottom: '1px solid var(--border-dim)',
                    display: 'flex', flexDirection: 'column', gap: 8,
                  }}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div style={{
                        width: 32, height: 32, borderRadius: 'var(--radius-md)',
                        background: key.is_active ? 'var(--amber-glow)' : 'var(--bg-muted)',
                        border: `1px solid ${key.is_active ? 'var(--border-amber)' : 'var(--border-dim)'}`,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                      }}>
                        <Shield size={14} style={{ color: key.is_active ? 'var(--amber)' : 'var(--text-muted)' }} />
                      </div>
                      <div>
                        <div style={{ fontWeight: 600, fontSize: 14, color: key.is_active ? 'var(--text-primary)' : 'var(--text-muted)' }}>
                          {key.name}
                        </div>
                        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                          {key.key_prefix}••••••••
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <PermissionBadge perm={key.permissions} />
                      <span className={`badge ${key.is_active ? 'badge-success' : 'badge-muted'}`}>
                        {key.is_active ? 'Active' : 'Revoked'}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4" style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                      {key.last_used_at && (
                        <div className="flex items-center gap-1">
                          <Clock size={10} />
                          Last used: {new Date(key.last_used_at).toLocaleDateString()}
                        </div>
                      )}
                      {key.expires_at && (
                        <div className="flex items-center gap-1">
                          <Clock size={10} />
                          Expires: {new Date(key.expires_at).toLocaleDateString()}
                        </div>
                      )}
                      <div>Calls: {(key.usage_count ?? 0).toLocaleString()}</div>
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => handleToggleActive(key)}
                        style={{ fontSize: 11 }}
                      >
                        {key.is_active ? 'Revoke' : 'Activate'}
                      </button>
                      <button
                        className="btn btn-danger btn-icon btn-sm"
                        onClick={() => handleDelete(key.id, key.name)}
                        title="Delete key"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </div>

                  {(key.rate_limit_per_minute || key.rate_limit_per_hour) && (
                    <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                      Rate limit:
                      {key.rate_limit_per_minute && ` ${key.rate_limit_per_minute}/min`}
                      {key.rate_limit_per_hour && ` ${key.rate_limit_per_hour}/hr`}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {showCreate && (
        <CreateKeyModal
          onClose={() => setShowCreate(false)}
          onCreated={(key) => {
            setShowCreate(false)
            setNewKey(key)
            fetchKeys()
          }}
        />
      )}

      {newKey && (
        <NewKeyDisplay keyData={newKey} onDone={() => setNewKey(null)} />
      )}
    </div>
  )
}
