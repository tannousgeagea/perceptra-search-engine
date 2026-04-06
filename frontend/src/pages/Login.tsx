import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Flame, KeyRound, Mail, Eye, EyeOff, AlertCircle, Loader2, UserPlus } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { getSession, loginWithCredentials, registerUser } from '../api/client'
import type { AuthState } from '../types/api'

type TabId = 'apikey' | 'signin' | 'register'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()

  const [tab, setTab] = useState<TabId>('apikey')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [showSecret, setShowSecret] = useState(false)

  // API key form
  const [apiKey, setApiKey]     = useState('')
  const [keyLabel, setKeyLabel] = useState('')

  // Sign-in form
  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [tenantId, setTenantId] = useState('')

  // Register form
  const [regEmail, setRegEmail]       = useState('')
  const [regName, setRegName]         = useState('')
  const [regPassword, setRegPassword] = useState('')
  const [regConfirm, setRegConfirm]   = useState('')

  const handleApiKeyLogin = async (e: FormEvent) => {
    e.preventDefault()
    if (!apiKey.trim()) { setError('API key is required'); return }
    setError('')
    setLoading(true)
    try {
      const authData: AuthState = {
        mode: 'apikey',
        apiKey: apiKey.trim(),
        apiKeyLabel: keyLabel.trim() || 'API Key',
      }
      localStorage.setItem('auth', JSON.stringify(authData))
      const sessionRes = await getSession()
      authData.session = sessionRes.data
      login(authData)
      navigate('/dashboard', { replace: true })
    } catch (err: unknown) {
      localStorage.removeItem('auth')
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 401) setError('Invalid API key. Please check and try again.')
      else setError('Unable to connect to the API. Ensure the backend is running.')
    } finally {
      setLoading(false)
    }
  }

  const handleCredentialsLogin = async (e: FormEvent) => {
    e.preventDefault()
    if (!email || !password) { setError('Email and password are required'); return }
    setError('')
    setLoading(true)
    try {
      const res = await loginWithCredentials({ email, password })
      const tenantValue = tenantId.trim()
      const isUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(tenantValue)
      const authData: AuthState = {
        mode: 'jwt',
        token: res.data.access,
        refreshToken: res.data.refresh,
        email,
        tenantId: isUuid ? tenantValue : undefined,
        tenantDomain: !isUuid && tenantValue ? tenantValue : undefined,
      }
      // Store tokens first so the session fetch has auth headers
      localStorage.setItem('auth', JSON.stringify(authData))
      try {
        const sessionRes = await getSession()
        authData.session = sessionRes.data
      } catch {
        // Session fetch may fail if no tenant assigned yet — proceed anyway
      }
      login(authData)
      navigate('/dashboard', { replace: true })
    } catch (err: unknown) {
      localStorage.removeItem('auth')
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 401 || status === 400) setError('Invalid email or password.')
      else setError('Unable to connect to the API. Ensure the backend is running.')
    } finally {
      setLoading(false)
    }
  }

  const handleRegister = async (e: FormEvent) => {
    e.preventDefault()
    if (!regEmail || !regPassword) { setError('Email and password are required'); return }
    if (regPassword !== regConfirm) { setError('Passwords do not match'); return }
    setError(''); setSuccess('')
    setLoading(true)
    try {
      await registerUser({ email: regEmail, password: regPassword, name: regName.trim() || undefined })
      setSuccess('Account created! You can now sign in.')
      setTab('signin')
      setEmail(regEmail)
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 409) setError('An account with this email already exists.')
      else if (detail) setError(detail)
      else setError('Registration failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const TABS: { id: TabId; label: string; icon: React.ReactNode }[] = [
    { id: 'apikey',   label: 'API Key',   icon: <KeyRound size={13} /> },
    { id: 'signin',   label: 'Sign In',   icon: <Mail size={13} /> },
    { id: 'register', label: 'Register',  icon: <UserPlus size={13} /> },
  ]

  return (
    <div style={{
      minHeight: '100vh', width: '100%',
      background: 'var(--bg-void)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      position: 'relative', overflow: 'hidden',
    }}>
      {/* Grid background */}
      <div style={{
        position: 'absolute', inset: 0,
        backgroundImage: `
          linear-gradient(var(--border-dim) 1px, transparent 1px),
          linear-gradient(90deg, var(--border-dim) 1px, transparent 1px)
        `,
        backgroundSize: '40px 40px',
        opacity: 0.6,
      }} />

      {/* Amber radial glow */}
      <div style={{
        position: 'absolute',
        width: 600, height: 600,
        borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(245,166,35,0.07) 0%, transparent 70%)',
        top: '50%', left: '50%',
        transform: 'translate(-50%, -50%)',
        pointerEvents: 'none',
      }} />

      {/* Corner decorations */}
      <div style={{ position: 'absolute', top: 24, left: 24, opacity: 0.4 }}>
        <div style={{ width: 20, height: 20, borderTop: '2px solid var(--amber)', borderLeft: '2px solid var(--amber)' }} />
      </div>
      <div style={{ position: 'absolute', top: 24, right: 24, opacity: 0.4 }}>
        <div style={{ width: 20, height: 20, borderTop: '2px solid var(--amber)', borderRight: '2px solid var(--amber)' }} />
      </div>
      <div style={{ position: 'absolute', bottom: 24, left: 24, opacity: 0.4 }}>
        <div style={{ width: 20, height: 20, borderBottom: '2px solid var(--amber)', borderLeft: '2px solid var(--amber)' }} />
      </div>
      <div style={{ position: 'absolute', bottom: 24, right: 24, opacity: 0.4 }}>
        <div style={{ width: 20, height: 20, borderBottom: '2px solid var(--amber)', borderRight: '2px solid var(--amber)' }} />
      </div>

      {/* Login card */}
      <div style={{
        position: 'relative', zIndex: 10,
        width: '100%', maxWidth: 440,
        padding: '0 20px',
        animation: 'fadeUp 0.4s ease-out',
      }}>
        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 36 }}>
          <div style={{
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            width: 64, height: 64, borderRadius: 16,
            background: 'linear-gradient(135deg, var(--amber-700), var(--amber))',
            marginBottom: 16,
            boxShadow: '0 0 32px rgba(245,166,35,0.4), 0 0 64px rgba(245,166,35,0.15)',
            animation: 'glow-pulse 3s ease-in-out infinite',
          }}>
            <Flame size={28} color="#000" strokeWidth={2.5} />
          </div>
          <h1 style={{
            fontFamily: 'var(--font-display)', fontSize: 28, fontWeight: 700,
            letterSpacing: '0.1em', textTransform: 'uppercase',
            color: 'var(--text-primary)', marginBottom: 6,
          }}>
            OPTIVYN
          </h1>
          <p style={{
            fontFamily: 'var(--font-mono)', fontSize: 11,
            color: 'var(--text-muted)', letterSpacing: '0.15em',
          }}>
            VISUAL SEARCH PLATFORM — v1.0
          </p>
        </div>

        {/* Card */}
        <div style={{
          background: 'var(--bg-surface)',
          border: '1px solid var(--border-base)',
          borderRadius: 'var(--radius-xl)',
          overflow: 'hidden',
          boxShadow: 'var(--shadow-lg)',
        }}>
          {/* Tabs */}
          <div style={{ display: 'flex', borderBottom: '1px solid var(--border-base)' }}>
            {TABS.map(({ id, label, icon }) => (
              <button
                key={id}
                onClick={() => { setTab(id); setError(''); setSuccess('') }}
                style={{
                  flex: 1, padding: '14px 0',
                  fontFamily: 'var(--font-display)', fontSize: 11, fontWeight: 600,
                  letterSpacing: '0.08em', textTransform: 'uppercase',
                  color: tab === id ? 'var(--amber)' : 'var(--text-muted)',
                  background: tab === id ? 'var(--amber-glow)' : 'transparent',
                  borderBottom: tab === id ? '2px solid var(--amber)' : '2px solid transparent',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                  transition: 'all var(--transition-fast)',
                }}
              >
                {icon}{label}
              </button>
            ))}
          </div>

          {/* Form */}
          <div style={{ padding: 28 }}>
            {error && (
              <div className="alert alert-error mb-4" style={{ fontSize: 13 }}>
                <AlertCircle size={15} />
                <span>{error}</span>
              </div>
            )}
            {success && (
              <div className="alert alert-success mb-4" style={{ fontSize: 13 }}>
                <span>{success}</span>
              </div>
            )}

            {tab === 'apikey' && (
              <form onSubmit={handleApiKeyLogin} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                <div className="form-group">
                  <label className="form-label">API Key</label>
                  <div style={{ position: 'relative' }}>
                    <input
                      type={showSecret ? 'text' : 'password'}
                      className="form-input"
                      placeholder="sk-xxxxxxxxxxxxxxxxxxxxxxxx"
                      value={apiKey}
                      onChange={(e) => setApiKey(e.target.value)}
                      style={{ fontFamily: 'var(--font-mono)', paddingRight: 44 }}
                      autoFocus
                      autoComplete="current-password"
                    />
                    <button
                      type="button"
                      onClick={() => setShowSecret((s) => !s)}
                      style={{
                        position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)',
                        color: 'var(--text-muted)', display: 'flex', alignItems: 'center',
                      }}
                    >
                      {showSecret ? <EyeOff size={15} /> : <Eye size={15} />}
                    </button>
                  </div>
                </div>
                <div className="form-group">
                  <label className="form-label">Label <span style={{ opacity: 0.5, textTransform: 'none', letterSpacing: 0 }}>(optional)</span></label>
                  <input
                    type="text"
                    className="form-input"
                    placeholder="My Inspection Key"
                    value={keyLabel}
                    onChange={(e) => setKeyLabel(e.target.value)}
                  />
                </div>
                <div style={{
                  padding: '10px 12px',
                  background: 'var(--info-dim)',
                  border: '1px solid rgba(59,130,246,0.2)',
                  borderRadius: 'var(--radius-md)',
                  fontSize: 12,
                  color: 'var(--text-secondary)',
                  fontFamily: 'var(--font-mono)',
                  lineHeight: 1.5,
                }}>
                  Sends <code style={{ color: 'var(--cyan-400)' }}>X-API-Key</code> header.
                  Tenant is resolved automatically from the key.
                </div>
                <button
                  type="submit"
                  disabled={loading}
                  className="btn btn-primary btn-lg w-full"
                  style={{ justifyContent: 'center', marginTop: 4 }}
                >
                  {loading
                    ? <><Loader2 size={16} style={{ animation: 'spin 0.8s linear infinite' }} /> Verifying...</>
                    : 'Access System'
                  }
                </button>
              </form>
            )}

            {tab === 'signin' && (
              <form onSubmit={handleCredentialsLogin} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                <div className="form-group">
                  <label className="form-label">Email</label>
                  <input
                    type="email"
                    className="form-input"
                    placeholder="operator@plant.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    autoFocus
                    autoComplete="email"
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Password</label>
                  <div style={{ position: 'relative' }}>
                    <input
                      type={showSecret ? 'text' : 'password'}
                      className="form-input"
                      placeholder="••••••••"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      style={{ paddingRight: 44 }}
                      autoComplete="current-password"
                    />
                    <button
                      type="button"
                      onClick={() => setShowSecret((s) => !s)}
                      style={{
                        position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)',
                        color: 'var(--text-muted)', display: 'flex', alignItems: 'center',
                      }}
                    >
                      {showSecret ? <EyeOff size={15} /> : <Eye size={15} />}
                    </button>
                  </div>
                </div>
                <div className="form-group">
                  <label className="form-label">Tenant ID <span style={{ opacity: 0.5, textTransform: 'none', letterSpacing: 0 }}>(optional)</span></label>
                  <input
                    type="text"
                    className="form-input"
                    placeholder="tenant-uuid or domain"
                    value={tenantId}
                    onChange={(e) => setTenantId(e.target.value)}
                  />
                </div>
                <button
                  type="submit"
                  disabled={loading}
                  className="btn btn-primary btn-lg w-full"
                  style={{ justifyContent: 'center', marginTop: 4 }}
                >
                  {loading
                    ? <><Loader2 size={16} style={{ animation: 'spin 0.8s linear infinite' }} /> Authenticating...</>
                    : 'Sign In'
                  }
                </button>
                <p style={{ textAlign: 'center', fontSize: 12, color: 'var(--text-muted)' }}>
                  No account?{' '}
                  <button
                    type="button"
                    onClick={() => { setTab('register'); setError('') }}
                    style={{ color: 'var(--amber)', fontWeight: 600 }}
                  >
                    Register here
                  </button>
                </p>
              </form>
            )}

            {tab === 'register' && (
              <form onSubmit={handleRegister} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                <div className="form-group">
                  <label className="form-label">Email <span style={{ color: 'var(--danger)' }}>*</span></label>
                  <input
                    type="email"
                    className="form-input"
                    placeholder="operator@plant.com"
                    value={regEmail}
                    onChange={(e) => setRegEmail(e.target.value)}
                    autoFocus
                    autoComplete="email"
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Name <span style={{ opacity: 0.5, textTransform: 'none', letterSpacing: 0 }}>(optional)</span></label>
                  <input
                    type="text"
                    className="form-input"
                    placeholder="Jane Operator"
                    value={regName}
                    onChange={(e) => setRegName(e.target.value)}
                    autoComplete="name"
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Password <span style={{ color: 'var(--danger)' }}>*</span></label>
                  <div style={{ position: 'relative' }}>
                    <input
                      type={showSecret ? 'text' : 'password'}
                      className="form-input"
                      placeholder="Min 8 characters"
                      value={regPassword}
                      onChange={(e) => setRegPassword(e.target.value)}
                      style={{ paddingRight: 44 }}
                      autoComplete="new-password"
                    />
                    <button
                      type="button"
                      onClick={() => setShowSecret((s) => !s)}
                      style={{
                        position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)',
                        color: 'var(--text-muted)', display: 'flex', alignItems: 'center',
                      }}
                    >
                      {showSecret ? <EyeOff size={15} /> : <Eye size={15} />}
                    </button>
                  </div>
                </div>
                <div className="form-group">
                  <label className="form-label">Confirm Password <span style={{ color: 'var(--danger)' }}>*</span></label>
                  <input
                    type={showSecret ? 'text' : 'password'}
                    className="form-input"
                    placeholder="Repeat password"
                    value={regConfirm}
                    onChange={(e) => setRegConfirm(e.target.value)}
                    autoComplete="new-password"
                  />
                </div>
                <button
                  type="submit"
                  disabled={loading}
                  className="btn btn-primary btn-lg w-full"
                  style={{ justifyContent: 'center', marginTop: 4 }}
                >
                  {loading
                    ? <><Loader2 size={16} style={{ animation: 'spin 0.8s linear infinite' }} /> Creating account...</>
                    : 'Create Account'
                  }
                </button>
                <p style={{ textAlign: 'center', fontSize: 12, color: 'var(--text-muted)' }}>
                  Already have an account?{' '}
                  <button
                    type="button"
                    onClick={() => { setTab('signin'); setError('') }}
                    style={{ color: 'var(--amber)', fontWeight: 600 }}
                  >
                    Sign in
                  </button>
                </p>
              </form>
            )}
          </div>
        </div>

        <p style={{
          textAlign: 'center', marginTop: 20,
          fontFamily: 'var(--font-mono)', fontSize: 11,
          color: 'var(--text-disabled)', letterSpacing: '0.05em',
        }}>
          MULTI-MODAL VISUAL INSPECTION PLATFORM
        </p>
      </div>
    </div>
  )
}
