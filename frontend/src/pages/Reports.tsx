import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import {
  FileText, Download, ArrowUpRight, ArrowDownRight, Minus,
  Upload as UploadIcon, Target, AlertTriangle, TrendingUp,
  Clock, MapPin, Filter, RefreshCw,
} from 'lucide-react'
import type { ShiftSummaryResponse } from '../types/api'
import { getShiftSummary, downloadShiftPdf } from '../api/client'

const TOOLTIP_STYLE = {
  backgroundColor: 'var(--bg-elevated)',
  border: '1px solid var(--border-bright)',
  borderRadius: 'var(--radius-md)',
  fontFamily: 'var(--font-mono)',
  fontSize: 12,
  color: 'var(--text-primary)',
}

const SHIFT_LABELS: Record<string, { label: string; time: string; color: string }> = {
  morning:   { label: 'Morning',   time: '06:00 — 14:00', color: 'var(--amber)' },
  afternoon: { label: 'Afternoon', time: '14:00 — 22:00', color: 'var(--cyan-400)' },
  night:     { label: 'Night',     time: '22:00 — 06:00', color: '#8B5CF6' },
}

function DeltaBadge({ pct }: { pct: number }) {
  if (Math.abs(pct) < 0.5) {
    return (
      <span style={{
        display: 'inline-flex', alignItems: 'center', gap: 3, padding: '2px 8px',
        borderRadius: 'var(--radius-sm)', fontSize: 11, fontWeight: 600,
        fontFamily: 'var(--font-mono)', background: 'var(--bg-muted)', color: 'var(--text-muted)',
      }}>
        <Minus size={10} /> 0%
      </span>
    )
  }
  const up = pct > 0
  const Icon = up ? ArrowUpRight : ArrowDownRight
  // For defects: up is bad (danger), down is good (success)
  const color = up ? 'var(--danger)' : 'var(--success)'
  const bg = up ? 'var(--danger-dim)' : 'var(--success-dim)'
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 3, padding: '2px 8px',
      borderRadius: 'var(--radius-sm)', fontSize: 11, fontWeight: 600,
      fontFamily: 'var(--font-mono)', background: bg, color,
      border: `1px solid ${color}25`,
    }}>
      <Icon size={12} /> {Math.abs(pct).toFixed(1)}%
    </span>
  )
}

export default function Reports() {
  const navigate = useNavigate()
  const [shift, setShift] = useState('morning')
  const [date, setDate] = useState(() => new Date().toISOString().split('T')[0])
  const [plantSite, setPlantSite] = useState('')
  const [summary, setSummary] = useState<ShiftSummaryResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState('')

  const fetchReport = () => {
    setLoading(true)
    setError('')
    const params: { shift: string; date: string; plant_site?: string } = { shift, date }
    if (plantSite) params.plant_site = plantSite
    getShiftSummary(params)
      .then((r) => setSummary(r.data))
      .catch(() => setError('Failed to load shift summary'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchReport() }, [shift, date, plantSite])

  const handleDownloadPdf = async () => {
    setDownloading(true)
    try {
      const params: { shift: string; date: string; plant_site?: string } = { shift, date }
      if (plantSite) params.plant_site = plantSite
      const response = await downloadShiftPdf(params)
      const blob = new Blob([response.data], { type: 'application/pdf' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `shift_report_${shift}_${date}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      setError('PDF generation failed')
    }
    setDownloading(false)
  }

  const shiftInfo = SHIFT_LABELS[shift] ?? SHIFT_LABELS.morning
  const s = summary

  return (
    <div className="page-container">
      {/* Header */}
      <div className="page-header flex items-center justify-between">
        <div>
          <h1 className="page-title">Shift Reports</h1>
          <p className="page-subtitle">End-of-shift handoff summaries with trend comparison</p>
        </div>
        <button
          className="btn btn-primary"
          onClick={handleDownloadPdf}
          disabled={downloading || !summary}
        >
          <Download size={14} />
          {downloading ? 'Generating...' : 'Download PDF'}
        </button>
      </div>

      {/* Filter bar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px',
        background: 'var(--bg-elevated)', border: '1px solid var(--border-dim)',
        borderRadius: 'var(--radius-lg)', marginBottom: 24,
        flexWrap: 'wrap',
      }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
          paddingRight: 14, borderRight: '1px solid var(--border-dim)',
          marginRight: 4,
        }}>
          <Filter size={12} style={{ color: 'var(--text-muted)' }} />
          <span style={{
            fontFamily: 'var(--font-display)', fontSize: 10, fontWeight: 600,
            letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--text-muted)',
          }}>
            Shift
          </span>
        </div>

        {/* Shift selector as pill group */}
        <div style={{ display: 'flex', gap: 0, background: 'var(--bg-surface)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-dim)', overflow: 'hidden' }}>
          {Object.entries(SHIFT_LABELS).map(([key, { label, time, color }]) => (
            <button
              key={key}
              onClick={() => setShift(key)}
              style={{
                padding: '6px 16px',
                fontSize: 11,
                fontFamily: 'var(--font-display)',
                fontWeight: 600,
                letterSpacing: '0.06em',
                textTransform: 'uppercase',
                color: shift === key ? '#000' : 'var(--text-muted)',
                background: shift === key ? color : 'transparent',
                transition: 'all var(--transition-fast)',
                cursor: 'pointer',
                borderRight: '1px solid var(--border-dim)',
              }}
              title={time}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Date picker */}
        <div style={{ position: 'relative' }}>
          <Clock size={12} style={{
            position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)',
            color: 'var(--text-muted)', pointerEvents: 'none',
          }} />
          <input
            className="form-input"
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            style={{
              width: 160, height: 34, paddingLeft: 30, fontSize: 12,
              fontFamily: 'var(--font-mono)', background: 'var(--bg-surface)',
              borderColor: 'var(--border-dim)',
            }}
          />
        </div>

        {/* Plant */}
        <div style={{ position: 'relative' }}>
          <MapPin size={12} style={{
            position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)',
            color: 'var(--text-muted)', pointerEvents: 'none',
          }} />
          <input
            className="form-input"
            value={plantSite}
            onChange={(e) => setPlantSite(e.target.value)}
            placeholder="All plants"
            style={{
              width: 150, height: 34, paddingLeft: 30, fontSize: 12,
              fontFamily: 'var(--font-mono)', background: 'var(--bg-surface)',
              borderColor: plantSite ? 'var(--border-bright)' : 'var(--border-dim)',
            }}
          />
        </div>

        {/* Shift time label */}
        <span style={{
          marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: 11,
          color: shiftInfo.color, letterSpacing: '0.04em', fontWeight: 600,
        }}>
          {shiftInfo.time}
        </span>
      </div>

      {error && (
        <div style={{ padding: '10px 16px', marginBottom: 16, background: 'var(--danger-dim)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 'var(--radius-md)', fontSize: 12, color: 'var(--danger)', fontFamily: 'var(--font-mono)' }}>
          {error}
        </div>
      )}

      {loading ? (
        <div style={{ padding: 60, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
          <RefreshCw size={18} style={{ animation: 'spin 1s linear infinite', display: 'inline-block', marginRight: 8, verticalAlign: 'middle' }} />
          Loading shift summary...
        </div>
      ) : !s ? (
        <div className="empty-state" style={{ padding: '60px 20px' }}>
          <div className="empty-state-icon"><FileText size={28} /></div>
          <p style={{ color: 'var(--text-secondary)' }}>No data for this shift</p>
          <p style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
            Try a different date or shift window
          </p>
        </div>
      ) : (
        <>
          {/* KPI Cards */}
          <div className="stats-grid" style={{ marginBottom: 24 }}>
            <div className="stat-card" style={{ animation: 'fadeUp 0.3s ease-out both' }}>
              <div className="stat-icon" style={{ background: 'var(--cyan-glow)', borderColor: 'rgba(6,182,212,0.3)', color: 'var(--cyan-400)' }}>
                <UploadIcon size={18} />
              </div>
              <div className="stat-value">{s.uploads.total}</div>
              <div className="stat-label">Uploads</div>
              <div style={{ position: 'absolute', top: 16, right: 16 }}>
                <DeltaBadge pct={s.comparison.upload_delta_pct} />
              </div>
              <div style={{ marginTop: 6, fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                {s.uploads.images} images, {s.uploads.videos} videos
              </div>
            </div>

            <div className="stat-card" style={{ animation: 'fadeUp 0.3s ease-out both', animationDelay: '0.05s' }}>
              <div className="stat-icon" style={{ background: 'var(--amber-glow)', borderColor: 'var(--border-amber)', color: 'var(--amber)' }}>
                <Target size={18} />
              </div>
              <div className="stat-value">{s.detections.total}</div>
              <div className="stat-label">Detections</div>
              <div style={{ position: 'absolute', top: 16, right: 16 }}>
                <DeltaBadge pct={s.comparison.detection_delta_pct} />
              </div>
            </div>

            <div className="stat-card" style={{ animation: 'fadeUp 0.3s ease-out both', animationDelay: '0.1s' }}>
              <div className="stat-icon" style={{ background: 'var(--danger-dim)', borderColor: 'rgba(239,68,68,0.3)', color: 'var(--danger)' }}>
                <AlertTriangle size={18} />
              </div>
              <div className="stat-value">{s.detections.high_severity.length}</div>
              <div className="stat-label">High Severity</div>
              <div style={{ marginTop: 6, fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                confidence &ge; 80%
              </div>
            </div>

            <div className="stat-card" style={{ animation: 'fadeUp 0.3s ease-out both', animationDelay: '0.15s' }}>
              <div className="stat-icon" style={{ background: 'var(--warning-dim)', borderColor: 'rgba(245,158,11,0.3)', color: 'var(--warning)' }}>
                <TrendingUp size={18} />
              </div>
              <div className="stat-value">{s.alerts.total}</div>
              <div className="stat-label">Alerts</div>
              {s.alerts.critical > 0 && (
                <div style={{ marginTop: 6 }}>
                  <span className="badge badge-danger" style={{ fontSize: 9 }}>{s.alerts.critical} CRITICAL</span>
                </div>
              )}
            </div>
          </div>

          <div className="grid-2" style={{ marginBottom: 24 }}>
            {/* Detections by Label */}
            <div className="card">
              <div className="card-header">
                <span className="card-title flex items-center gap-2">
                  <Target size={12} /> Detections by Label
                </span>
                {s.detections.by_label.length > 0 && (
                  <span className="badge badge-muted">{s.detections.by_label.length} labels</span>
                )}
              </div>
              {s.detections.by_label.length > 0 ? (
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart
                    data={s.detections.by_label}
                    layout="vertical"
                    margin={{ top: 5, right: 20, left: 0, bottom: 5 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-dim)" horizontal={false} />
                    <XAxis type="number" tick={{ fill: 'var(--text-muted)', fontSize: 10, fontFamily: 'var(--font-mono)' }} axisLine={false} tickLine={false} />
                    <YAxis type="category" dataKey="label" tick={{ fill: 'var(--text-secondary)', fontSize: 11, fontFamily: 'var(--font-mono)' }} axisLine={false} tickLine={false} width={70} />
                    <Tooltip contentStyle={TOOLTIP_STYLE} />
                    <Bar dataKey="count" fill="var(--amber)" radius={[0, 4, 4, 0]} name="Detections" />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div style={{ height: 220, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 12, fontFamily: 'var(--font-mono)' }}>
                  No detections this shift
                </div>
              )}
            </div>

            {/* Shift Comparison */}
            <div className="card">
              <div className="card-header">
                <span className="card-title flex items-center gap-2">
                  <TrendingUp size={12} /> vs Previous Day
                </span>
                <span className="badge badge-muted">Same shift</span>
              </div>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart
                  data={[
                    { name: 'Uploads', current: s.uploads.total, previous: s.comparison.prev_uploads },
                    { name: 'Detections', current: s.detections.total, previous: s.comparison.prev_detections },
                  ]}
                  margin={{ top: 5, right: 20, left: -10, bottom: 5 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-dim)" vertical={false} />
                  <XAxis dataKey="name" tick={{ fill: 'var(--text-muted)', fontSize: 11, fontFamily: 'var(--font-mono)' }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 10, fontFamily: 'var(--font-mono)' }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} />
                  <Legend wrapperStyle={{ fontFamily: 'var(--font-mono)', fontSize: 11, paddingTop: 8 }} />
                  <Bar dataKey="current" name="This Shift" fill="var(--amber)" radius={[3, 3, 0, 0]} />
                  <Bar dataKey="previous" name="Previous" fill="var(--bg-hover)" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* High Severity Items */}
          {s.detections.high_severity.length > 0 && (
            <div className="card">
              <div className="card-header">
                <span className="card-title flex items-center gap-2">
                  <AlertTriangle size={12} /> High-Severity Detections
                </span>
                <span className="badge badge-danger">{s.detections.high_severity.length}</span>
              </div>
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
                gap: 10,
              }}>
                {s.detections.high_severity.map((item) => (
                  <div
                    key={item.detection_id}
                    style={{
                      background: 'var(--bg-elevated)',
                      border: '1px solid var(--border-dim)',
                      borderRadius: 'var(--radius-md)',
                      overflow: 'hidden',
                      cursor: 'pointer',
                      transition: 'all var(--transition-fast)',
                    }}
                    onClick={() => navigate(`/media/detections/${item.detection_id}`)}
                    onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--danger)'; e.currentTarget.style.transform = 'translateY(-2px)' }}
                    onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--border-dim)'; e.currentTarget.style.transform = '' }}
                  >
                    {item.crop_url && (
                      <div style={{ width: '100%', height: 90, background: 'var(--bg-muted)' }}>
                        <img src={item.crop_url} alt={item.label} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                      </div>
                    )}
                    <div style={{ padding: '8px 10px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                        <span className="badge badge-danger" style={{ fontSize: 9 }}>{item.label}</span>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--danger)', fontWeight: 700 }}>
                          {(item.confidence * 100).toFixed(0)}%
                        </span>
                      </div>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {item.image_filename}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
