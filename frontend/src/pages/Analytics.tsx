import { useEffect, useState } from 'react'
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import {
  TrendingUp, Search, Clock, Target, AlertTriangle, BarChart3,
  RefreshCw, History, RotateCcw, Zap, Grid3X3, Download, Filter,
  Tag, MapPin, CalendarDays, type LucideIcon,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import {
  getSearchStats, getMediaStats, getSearchVolume, getSearchHistory,
  getDetectionTrends, getAnomalies, getHeatmap,
} from '../api/client'
import type {
  SearchStatsResponse, MediaStats, SearchVolumeDay, SearchHistoryItem,
  TrendResponse, AnomalyResponse, HeatmapResponse,
} from '../types/api'

const PIE_COLORS = ['#F5A623', '#22D3EE', '#10B981', '#8B5CF6', '#EF4444', '#4E5A73']
const TREND_COLORS = ['#F5A623', '#22D3EE', '#10B981', '#EF4444', '#8B5CF6', '#EC4899', '#14B8A6', '#F97316']

const TOOLTIP_STYLE = {
  backgroundColor: 'var(--bg-elevated)',
  border: '1px solid var(--border-bright)',
  borderRadius: 'var(--radius-md)',
  fontFamily: 'var(--font-mono)',
  fontSize: 12,
  color: 'var(--text-primary)',
}

interface KpiCardProps {
  icon: LucideIcon
  label: string
  value: string
  sub?: string
  accentColor?: string
  delay?: number
}

function KpiCard({ icon: Icon, label, value, sub, accentColor = 'var(--amber)', delay = 0 }: KpiCardProps) {
  return (
    <div className="stat-card" style={{ animation: `fadeUp 0.35s ease-out ${delay}s both` }}>
      <div className="stat-icon" style={{ background: `${accentColor}18`, borderColor: `${accentColor}40`, color: accentColor }}>
        <Icon size={18} />
      </div>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {sub && (
        <div style={{ marginTop: 4, fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
          {sub}
        </div>
      )}
    </div>
  )
}

// ── Overview Tab (original content) ──────────────────────────

function OverviewTab() {
  const navigate = useNavigate()
  const [searchStats, setSearchStats] = useState<SearchStatsResponse | null>(null)
  const [mediaStats, setMediaStats]   = useState<MediaStats | null>(null)
  const [volume, setVolume]           = useState<SearchVolumeDay[]>([])
  const [history, setHistory]         = useState<SearchHistoryItem[]>([])
  const [loading, setLoading]         = useState(false)

  const fetchStats = async () => {
    setLoading(true)
    try {
      const [s, m, v, h] = await Promise.all([
        getSearchStats(), getMediaStats(), getSearchVolume(30),
        getSearchHistory({ page: 1, page_size: 15 }),
      ])
      setSearchStats(s.data); setMediaStats(m.data); setVolume(v.data); setHistory(h.data.items)
    } catch { /* silent */ }
    finally { setLoading(false) }
  }

  useEffect(() => { fetchStats() }, [])

  const topLabels = (mediaStats?.top_labels ?? []).slice(0, 8).map((l, i) => ({
    label: l.label, count: l.count, color: PIE_COLORS[i % PIE_COLORS.length],
  }))

  const typeData = searchStats?.search_type_distribution
    ? Object.entries(searchStats.search_type_distribution).map(([name, value], i) => ({
        name: name.charAt(0).toUpperCase() + name.slice(1), value, color: PIE_COLORS[i % PIE_COLORS.length],
      }))
    : []

  const volumeFormatted = volume.map((v) => ({
    ...v,
    dateLabel: new Date(v.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
  }))

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
        <button className="btn btn-secondary btn-sm" onClick={fetchStats} disabled={loading}>
          <RefreshCw size={13} style={loading ? { animation: 'spin 1s linear infinite' } : {}} /> Refresh
        </button>
      </div>

      <div className="stats-grid">
        <KpiCard icon={Search} label="Total Searches" value={searchStats?.total_searches?.toLocaleString() ?? '—'} sub={`${searchStats?.searches_today ?? 0} today`} delay={0.05} />
        <KpiCard icon={Clock} label="Avg Response Time" value={searchStats?.avg_execution_time_ms ? `${Math.round(searchStats.avg_execution_time_ms)}ms` : '—'} sub="P50 latency" accentColor="var(--cyan-400)" delay={0.10} />
        <KpiCard icon={Target} label="Total Detections" value={mediaStats?.total_detections?.toLocaleString() ?? '—'} accentColor="var(--danger)" delay={0.15} />
        <KpiCard icon={AlertTriangle} label="Top Defect" value={topLabels[0]?.label ?? '—'} sub={topLabels[0] ? `${topLabels[0].count} occurrences` : undefined} accentColor="var(--warning)" delay={0.20} />
      </div>

      <div className="card mb-4" style={{ marginBottom: 20 }}>
        <div className="card-header">
          <span className="card-title flex items-center gap-2"><TrendingUp size={13} /> Search Volume — Last 30 Days</span>
        </div>
        {volumeFormatted.length > 0 ? (
          <ResponsiveContainer width="100%" height={250}>
            <AreaChart data={volumeFormatted} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="gradSearches" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--amber)" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="var(--amber)" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gradDetections" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--cyan-400)" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="var(--cyan-400)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-dim)" />
              <XAxis dataKey="dateLabel" tick={{ fill: 'var(--text-muted)', fontSize: 10, fontFamily: 'var(--font-mono)' }} axisLine={false} tickLine={false} interval={Math.max(Math.floor(volumeFormatted.length / 6), 1)} />
              <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 10, fontFamily: 'var(--font-mono)' }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Area type="monotone" dataKey="searches" stroke="var(--amber)" strokeWidth={2} fill="url(#gradSearches)" name="Searches" />
              <Area type="monotone" dataKey="detections" stroke="var(--cyan-400)" strokeWidth={2} fill="url(#gradDetections)" name="With Results" />
              <Legend wrapperStyle={{ fontFamily: 'var(--font-mono)', fontSize: 11, paddingTop: 8 }} />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div style={{ height: 250, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 13 }}>No search data yet</div>
        )}
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-header"><span className="card-title flex items-center gap-2"><Search size={13} /> Search Type Distribution</span></div>
          {typeData.length > 0 ? (
            <div className="flex items-center gap-4" style={{ height: 220 }}>
              <ResponsiveContainer width="55%" height="100%">
                <PieChart>
                  <Pie data={typeData} cx="50%" cy="50%" innerRadius={55} outerRadius={85} paddingAngle={3} dataKey="value">
                    {typeData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                  </Pie>
                  <Tooltip contentStyle={TOOLTIP_STYLE} />
                </PieChart>
              </ResponsiveContainer>
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 10 }}>
                {typeData.map((d) => (
                  <div key={d.name} className="flex items-center gap-2">
                    <div style={{ width: 8, height: 8, borderRadius: 2, background: d.color, flexShrink: 0 }} />
                    <span style={{ fontSize: 12, color: 'var(--text-secondary)', flex: 1 }}>{d.name}</span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: d.color, fontWeight: 600 }}>{d.value}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div style={{ height: 220, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 13 }}>No search type data yet</div>
          )}
        </div>

        <div className="card">
          <div className="card-header"><span className="card-title flex items-center gap-2"><BarChart3 size={13} /> Top Defect Labels</span></div>
          {topLabels.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={topLabels} layout="vertical" margin={{ top: 0, right: 30, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-dim)" horizontal={false} />
                <XAxis type="number" tick={{ fill: 'var(--text-muted)', fontSize: 10, fontFamily: 'var(--font-mono)' }} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="label" width={100} tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Bar dataKey="count" name="Count" radius={[0, 4, 4, 0]}>
                  {topLabels.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ height: 220, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 13 }}>No detection labels yet</div>
          )}
        </div>
      </div>

      {searchStats?.most_searched_labels && searchStats.most_searched_labels.length > 0 && (
        <div className="card" style={{ marginTop: 20 }}>
          <div className="card-header"><span className="card-title">Most Searched Labels</span></div>
          <div className="table-wrapper">
            <table className="data-table">
              <thead><tr><th>#</th><th>Label</th><th>Search Count</th><th>Share</th></tr></thead>
              <tbody>
                {searchStats.most_searched_labels.map((item, i) => {
                  const total = searchStats.most_searched_labels.reduce((s, l) => s + l.count, 0)
                  const pct = total > 0 ? Math.round((item.count / total) * 100) : 0
                  return (
                    <tr key={i}>
                      <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)' }}>{i + 1}</td>
                      <td style={{ fontWeight: 500, color: 'var(--text-primary)' }}>{item.label}</td>
                      <td style={{ fontFamily: 'var(--font-mono)', fontSize: 13 }}>{(item.count ?? 0).toLocaleString()}</td>
                      <td>
                        <div className="flex items-center gap-2">
                          <div className="progress-bar" style={{ flex: 1, height: 4 }}><div className="progress-fill" style={{ width: `${pct}%` }} /></div>
                          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--amber)', minWidth: 30 }}>{pct}%</span>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="card" style={{ marginTop: 20 }}>
        <div className="card-header">
          <span className="card-title flex items-center gap-2">
            <History size={13} /> Recent Search History
            {history.length > 0 && <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', background: 'var(--bg-muted)', color: 'var(--text-muted)', borderRadius: 3, padding: '1px 5px' }}>{history.length}</span>}
          </span>
          <button className="btn btn-ghost btn-sm" onClick={() => navigate('/search')} style={{ fontSize: 11 }}><Search size={11} /> Go to Search</button>
        </div>
        {history.length > 0 ? (
          <div className="table-wrapper">
            <table className="data-table">
              <thead><tr><th>Query</th><th>Type</th><th>Results</th><th>Time</th><th>Date</th><th></th></tr></thead>
              <tbody>
                {history.map((item) => (
                  <tr key={String(item.id)}>
                    <td style={{ maxWidth: 280 }}><span style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.query_text || `[${item.query_type} search]`}</span></td>
                    <td><span className={`badge ${item.query_type === 'text' ? 'badge-cyan' : item.query_type === 'image' ? 'badge-amber' : item.query_type === 'agent' ? 'badge-success' : 'badge-dim'}`}>{item.query_type}</span></td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-primary)' }}>{item.results_count}</td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>{item.execution_time_ms}ms</td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>{new Date(item.created_at).toLocaleDateString()}<br />{new Date(item.created_at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}</td>
                    <td>{item.query_text && <button className="btn btn-ghost btn-sm" onClick={() => navigate('/search')} title="Go to search"><RotateCcw size={12} /></button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div style={{ height: 120, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 13 }}>No search history yet</div>
        )}
      </div>
    </>
  )
}

// ── Trends Tab ───────────────────────────────────────────────

function TrendsTab() {
  const [trends, setTrends] = useState<TrendResponse | null>(null)
  const [heatmap, setHeatmap] = useState<HeatmapResponse | null>(null)
  const [labels, setLabels] = useState('')
  const [plantSite, setPlantSite] = useState('')
  const [granularity, setGranularity] = useState('day')
  const [days, setDays] = useState(90)
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const fetchTrends = () => {
    setLoading(true)
    const params: Record<string, string | number> = { granularity, days }
    if (labels) params.labels = labels
    if (plantSite) params.plant_site = plantSite
    Promise.all([
      getDetectionTrends(params as Parameters<typeof getDetectionTrends>[0]),
      getHeatmap({ days }),
    ])
      .then(([t, h]) => { setTrends(t.data); setHeatmap(h.data) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchTrends() }, [granularity, days])

  // Merge all series into a unified dataset for LineChart
  const mergedData: Record<string, Record<string, number>>[] = []
  if (trends?.series) {
    const dateMap: Record<string, Record<string, number>> = {}
    for (const s of trends.series) {
      for (const p of s.data) {
        if (!dateMap[p.date]) dateMap[p.date] = { date: 0 }
        dateMap[p.date][s.label] = p.count
      }
    }
    // Sort by date
    const sorted = Object.entries(dateMap).sort(([a], [b]) => a.localeCompare(b))
    for (const [date, counts] of sorted) {
      mergedData.push({ date: { date: 0, ...counts }, ...counts, _date: date } as never)
    }
  }

  const chartData = trends?.series
    ? (() => {
        const dateMap = new Map<string, Record<string, number | string>>()
        for (const s of trends.series) {
          for (const p of s.data) {
            if (!dateMap.has(p.date)) dateMap.set(p.date, { date: new Date(p.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) })
            dateMap.get(p.date)![s.label] = p.count
          }
        }
        return [...dateMap.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([, v]) => v)
      })()
    : []

  const seriesLabels = trends?.series?.map((s) => s.label) ?? []

  // Heatmap helpers
  const heatmapMax = heatmap?.cells?.reduce((m, c) => Math.max(m, c.count), 0) ?? 1

  const heatColor = (count: number) => {
    if (count === 0) return 'transparent'
    const intensity = Math.min(count / heatmapMax, 1)
    if (intensity > 0.7) return 'var(--danger)'
    if (intensity > 0.4) return 'var(--amber)'
    return 'var(--amber-600)'
  }

  const getHeatCount = (label: string, plant: string) =>
    heatmap?.cells?.find((c) => c.label === label && c.plant_site === plant)?.count ?? 0

  return (
    <>
      {/* Filters */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px',
        background: 'var(--bg-elevated)', border: '1px solid var(--border-dim)',
        borderRadius: 'var(--radius-lg)', marginBottom: 20,
        flexWrap: 'wrap',
      }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
          paddingRight: 12, borderRight: '1px solid var(--border-dim)', marginRight: 2,
        }}>
          <Filter size={12} style={{ color: 'var(--text-muted)' }} />
          <span style={{
            fontFamily: 'var(--font-display)', fontSize: 10, fontWeight: 600,
            letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--text-muted)',
          }}>
            Filters
          </span>
        </div>

        {/* Labels input */}
        <div style={{ position: 'relative' }}>
          <Tag size={12} style={{
            position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)',
            color: 'var(--text-muted)', pointerEvents: 'none',
          }} />
          <input
            className="form-input"
            value={labels}
            onChange={(e) => setLabels(e.target.value)}
            placeholder="Labels (e.g. rust, crack)"
            style={{
              width: 210, height: 34, paddingLeft: 30, fontSize: 12,
              fontFamily: 'var(--font-mono)', background: 'var(--bg-surface)',
              borderColor: labels ? 'var(--border-bright)' : 'var(--border-dim)',
            }}
          />
        </div>

        {/* Plant input */}
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

        {/* Granularity pill */}
        <div style={{ display: 'flex', gap: 0, background: 'var(--bg-surface)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-dim)', overflow: 'hidden' }}>
          {(['day', 'week'] as const).map((g) => (
            <button
              key={g}
              onClick={() => setGranularity(g)}
              style={{
                padding: '6px 14px', fontSize: 10, fontFamily: 'var(--font-display)',
                fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase',
                color: granularity === g ? '#000' : 'var(--text-muted)',
                background: granularity === g ? 'var(--amber)' : 'transparent',
                transition: 'all var(--transition-fast)', cursor: 'pointer',
                borderRight: g === 'day' ? '1px solid var(--border-dim)' : 'none',
              }}
            >
              {g}
            </button>
          ))}
        </div>

        {/* Days pill */}
        <div style={{ display: 'flex', gap: 0, background: 'var(--bg-surface)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-dim)', overflow: 'hidden' }}>
          {([30, 60, 90] as const).map((d, i) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              style={{
                padding: '6px 12px', fontSize: 10, fontFamily: 'var(--font-mono)',
                fontWeight: 600,
                color: days === d ? '#000' : 'var(--text-muted)',
                background: days === d ? 'var(--cyan-400)' : 'transparent',
                transition: 'all var(--transition-fast)', cursor: 'pointer',
                borderRight: i < 2 ? '1px solid var(--border-dim)' : 'none',
              }}
            >
              {d}d
            </button>
          ))}
        </div>

        {/* Apply */}
        <button className="btn btn-primary btn-sm" onClick={fetchTrends} disabled={loading} style={{ marginLeft: 'auto' }}>
          {loading ? (
            <><RefreshCw size={11} style={{ animation: 'spin 1s linear infinite' }} /> Loading</>
          ) : 'Apply'}
        </button>
      </div>

      {/* Trend chart */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-header">
          <span className="card-title flex items-center gap-2"><TrendingUp size={13} /> Detection Trends</span>
          <span className="badge badge-muted">{days}d / {granularity}</span>
        </div>
        {chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={chartData} margin={{ top: 5, right: 20, left: -10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-dim)" />
              <XAxis dataKey="date" tick={{ fill: 'var(--text-muted)', fontSize: 10, fontFamily: 'var(--font-mono)' }} axisLine={false} tickLine={false} interval={Math.max(Math.floor(chartData.length / 8), 1)} />
              <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 10, fontFamily: 'var(--font-mono)' }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              {seriesLabels.map((label, i) => (
                <Line key={label} type="monotone" dataKey={label} stroke={TREND_COLORS[i % TREND_COLORS.length]} strokeWidth={2} dot={{ r: 2 }} name={label} />
              ))}
              <Legend wrapperStyle={{ fontFamily: 'var(--font-mono)', fontSize: 11, paddingTop: 8 }} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div style={{ height: 300, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
            {loading ? 'Loading trends...' : 'No trend data available'}
          </div>
        )}
      </div>

      {/* Heatmap */}
      {heatmap && heatmap.labels.length > 0 && heatmap.plant_sites.length > 0 && (
        <div className="card">
          <div className="card-header">
            <span className="card-title flex items-center gap-2"><Grid3X3 size={13} /> Label x Plant Heatmap</span>
          </div>
          <div className="table-wrapper" style={{ overflowX: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th style={{ position: 'sticky', left: 0, background: 'var(--bg-surface)', zIndex: 1 }}>Label</th>
                  {heatmap.plant_sites.map((p) => <th key={p} style={{ textAlign: 'center', fontSize: 11 }}>{p}</th>)}
                </tr>
              </thead>
              <tbody>
                {heatmap.labels.map((label) => (
                  <tr key={label}>
                    <td style={{ fontWeight: 500, position: 'sticky', left: 0, background: 'var(--bg-surface)', zIndex: 1 }}>{label}</td>
                    {heatmap.plant_sites.map((plant) => {
                      const count = getHeatCount(label, plant)
                      return (
                        <td
                          key={plant}
                          style={{
                            textAlign: 'center',
                            fontFamily: 'var(--font-mono)',
                            fontSize: 12,
                            color: count > 0 ? 'var(--text-primary)' : 'var(--text-disabled)',
                            background: count > 0 ? `${heatColor(count)}20` : 'transparent',
                            cursor: count > 0 ? 'pointer' : 'default',
                          }}
                          onClick={() => count > 0 && navigate(`/search?label=${label}&plant=${plant}`)}
                        >
                          {count || '—'}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  )
}

// ── Anomalies Tab ────────────────────────────────────────────

function AnomaliesTab() {
  const navigate = useNavigate()
  const [anomalies, setAnomalies] = useState<AnomalyResponse | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getAnomalies()
      .then((r) => setAnomalies(r.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>Analyzing detection patterns...</div>

  if (!anomalies?.anomalies?.length) {
    return (
      <div className="empty-state">
        <div className="empty-state-icon"><Zap size={32} /></div>
        <p>No anomalies detected</p>
        <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>Detection rates are within normal ranges</p>
      </div>
    )
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
      {anomalies.anomalies.map((a, i) => (
        <div
          key={i}
          className="card"
          style={{
            padding: 16,
            borderLeft: `3px solid ${a.severity === 'critical' ? 'var(--danger)' : 'var(--warning)'}`,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <span className={`badge ${a.severity === 'critical' ? 'badge-danger' : 'badge-amber'}`} style={{ fontSize: 10 }}>
              {a.severity.toUpperCase()}
            </span>
            <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>{a.label}</span>
          </div>

          <div style={{
            fontSize: 28, fontWeight: 700, fontFamily: 'var(--font-mono)',
            color: a.pct_change > 0 ? 'var(--danger)' : 'var(--success)',
            marginBottom: 4,
          }}>
            {a.pct_change > 0 ? '+' : ''}{a.pct_change.toFixed(0)}%
          </div>

          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 12, display: 'flex', flexDirection: 'column', gap: 2 }}>
            <span>Current: {a.current_count} detections</span>
            <span>Average: {a.avg_count.toFixed(1)} expected</span>
            <span>Z-score: {a.z_score.toFixed(2)}</span>
            {a.plant_site && <span>Plant: {a.plant_site}</span>}
            <span style={{ fontSize: 11 }}>{a.period}</span>
          </div>

          <button
            className="btn btn-secondary btn-sm"
            onClick={() => navigate(`/search?label=${a.label}${a.plant_site ? `&plant=${a.plant_site}` : ''}`)}
            style={{ width: '100%' }}
          >
            <Search size={12} /> Investigate
          </button>
        </div>
      ))}
    </div>
  )
}

// ── Main Page ────────────────────────────────────────────────

export default function Analytics() {
  const [tab, setTab] = useState<'overview' | 'trends' | 'anomalies'>('overview')

  const tabs = [
    { key: 'overview' as const, label: 'Overview', icon: BarChart3 },
    { key: 'trends' as const, label: 'Trends', icon: TrendingUp },
    { key: 'anomalies' as const, label: 'Anomalies', icon: Zap },
  ]

  return (
    <div className="page-container">
      <div className="page-header flex items-center justify-between">
        <div>
          <h1 className="page-title">System Analytics</h1>
          <p className="page-subtitle">Search performance, inspection metrics & anomaly detection</p>
        </div>
        <button
          className="btn btn-secondary btn-sm"
          onClick={async () => {
            try {
              const { exportAnalytics } = await import('../api/client')
              const r = await exportAnalytics({ days: 30 })
              const blob = new Blob([r.data])
              const url = URL.createObjectURL(blob)
              const a = document.createElement('a')
              a.href = url
              a.download = 'analytics_export.json'
              a.click()
              URL.revokeObjectURL(url)
            } catch { /* ignore */ }
          }}
        >
          <Download size={13} /> Export
        </button>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 0, borderBottom: '1px solid var(--border-dim)', marginBottom: 20 }}>
        {tabs.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            style={{
              padding: '10px 20px',
              fontFamily: 'var(--font-display)',
              fontSize: 13,
              fontWeight: 600,
              letterSpacing: '0.04em',
              color: tab === key ? 'var(--amber)' : 'var(--text-muted)',
              borderBottom: `2px solid ${tab === key ? 'var(--amber)' : 'transparent'}`,
              transition: 'all var(--transition-fast)',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              cursor: 'pointer',
              background: 'transparent',
            }}
          >
            <Icon size={14} />
            {label}
          </button>
        ))}
      </div>

      {tab === 'overview' && <OverviewTab />}
      {tab === 'trends' && <TrendsTab />}
      {tab === 'anomalies' && <AnomaliesTab />}
    </div>
  )
}
