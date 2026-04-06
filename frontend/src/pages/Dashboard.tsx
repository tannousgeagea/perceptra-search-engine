import { useEffect, useState } from 'react'
import {
  LineChart, Line, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import { useNavigate } from 'react-router-dom'
import {
  Search, Image, Target, TrendingUp, Clock,
  Activity, AlertTriangle, Bell, FileText, UserCheck, type LucideIcon,
} from 'lucide-react'
import { getSearchStats, getMediaStats, getSearchVolume, getRecentActivity, getMyAssignments, getActivityFeed } from '../api/client'
import type { SearchStatsResponse, MediaStats, SearchVolumeDay, ActivityItem, AssignmentResponse, ActivityEventResponse } from '../types/api'
import { useAlerts } from '../context/AlertContext'

const PIE_COLORS = ['#F5A623', '#06B6D4', '#10B981', '#8B5CF6', '#4E5A73']

const TOOLTIP_STYLE = {
  backgroundColor: 'var(--bg-elevated)',
  border: '1px solid var(--border-bright)',
  borderRadius: 'var(--radius-md)',
  fontFamily: 'var(--font-mono)',
  fontSize: 12,
  color: 'var(--text-primary)',
}

interface StatCardProps {
  icon: LucideIcon
  value: string
  label: string
  trend?: string
  trendUp?: boolean
  delay?: number
  accentColor?: string
}

function StatCard({ icon: Icon, value, label, trend, trendUp, delay = 0, accentColor = 'var(--amber)' }: StatCardProps) {
  return (
    <div className="stat-card" style={{ animationDelay: `${delay}s`, animation: 'fadeUp 0.35s ease-out both' }}>
      <div className="stat-icon" style={{ background: `${accentColor}18`, borderColor: `${accentColor}40`, color: accentColor }}>
        <Icon size={18} strokeWidth={2} />
      </div>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {trend && (
        <div className={`stat-trend ${trendUp ? 'up' : 'down'}`}>
          {trendUp ? '↑' : '↓'} {trend}
        </div>
      )}
    </div>
  )
}

export default function Dashboard() {
  const navigate = useNavigate()
  const { unreadCount } = useAlerts()
  const [searchStats, setSearchStats] = useState<SearchStatsResponse | null>(null)
  const [mediaStats, setMediaStats]   = useState<MediaStats | null>(null)
  const [volume, setVolume]           = useState<SearchVolumeDay[]>([])
  const [activity, setActivity]       = useState<ActivityItem[]>([])
  const [myAssignments, setMyAssignments] = useState<AssignmentResponse[]>([])
  const [teamActivity, setTeamActivity] = useState<ActivityEventResponse[]>([])

  useEffect(() => {
    getSearchStats().then((r) => setSearchStats(r.data)).catch(() => {})
    getMediaStats().then((r) => setMediaStats(r.data)).catch(() => {})
    getSearchVolume().then((r) => setVolume(r.data)).catch(() => {})
    getRecentActivity().then((r) => setActivity(r.data)).catch(() => {})
    getMyAssignments({ page_size: 5 }).then((r) => setMyAssignments(r.data.items)).catch(() => {})
    getActivityFeed({ page_size: 10 }).then((r) => setTeamActivity(r.data.items)).catch(() => {})
  }, [])

  const totalImages    = mediaStats?.total_images    ?? 0
  const totalVideos    = mediaStats?.total_videos    ?? 0
  const totalDetects   = mediaStats?.total_detections ?? 0
  const totalSearches  = searchStats?.total_searches  ?? 0
  const searchesToday  = searchStats?.searches_today  ?? 0
  const searchesYesterday = searchStats?.searches_yesterday ?? 0
  const avgMs          = searchStats?.avg_execution_time_ms ?? 0
  const mediaTrendPct  = mediaStats?.media_trend_pct ?? 0

  // Search trend: today vs yesterday
  const searchTrend = searchesToday > 0 ? `${searchesToday} today` : undefined
  const searchTrendUp = searchesToday >= searchesYesterday

  // Media trend
  const mediaTrend = mediaTrendPct !== 0 ? `${mediaTrendPct > 0 ? '+' : ''}${mediaTrendPct}%` : undefined
  const mediaTrendUp = mediaTrendPct >= 0

  // Plant breakdown from API
  const plantData = (mediaStats?.plant_breakdown ?? []).map((p) => ({
    plant:   p.plant_site,
    total:   p.total,
    detections: p.detections,
  }))

  // Defect pie from API
  const defectData = (mediaStats?.top_labels ?? []).slice(0, 5).map((l, i) => ({
    name:  l.label,
    value: l.count,
    color: PIE_COLORS[i % PIE_COLORS.length],
  }))

  return (
    <div className="page-container">
      {/* Header */}
      <div className="page-header flex items-center justify-between">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="page-subtitle">
            Real-time monitoring — Optivyn
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="status-dot" />
          <span className="text-sm text-mono" style={{ color: 'var(--success)', letterSpacing: '0.06em' }}>
            LIVE
          </span>
        </div>
      </div>

      {/* Stat cards */}
      <div className="stats-grid">
        <StatCard
          icon={Search}
          value={totalSearches > 0 ? totalSearches.toLocaleString() : '—'}
          label="Total Searches"
          trend={searchTrend}
          trendUp={searchTrendUp}
          delay={0.05}
        />
        <StatCard
          icon={Image}
          value={(totalImages + totalVideos) > 0 ? (totalImages + totalVideos).toLocaleString() : '—'}
          label="Media Files"
          trend={mediaTrend}
          trendUp={mediaTrendUp}
          delay={0.10}
          accentColor="var(--cyan-400)"
        />
        <StatCard
          icon={Target}
          value={totalDetects > 0 ? totalDetects.toLocaleString() : '—'}
          label="Detections"
          delay={0.15}
          accentColor="var(--danger)"
        />
        <StatCard
          icon={Bell}
          value={unreadCount > 0 ? unreadCount.toLocaleString() : '0'}
          label="Active Alerts"
          delay={0.20}
          accentColor={unreadCount > 0 ? 'var(--danger)' : 'var(--success)'}
        />
        <StatCard
          icon={Clock}
          value={avgMs > 0 ? `${Math.round(avgMs)}ms` : '—'}
          label="Avg Response"
          delay={0.25}
          accentColor="var(--success)"
        />
      </div>

      {/* Quick Actions */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
        <button
          className="card"
          onClick={() => navigate('/reports')}
          style={{
            padding: '14px 20px', cursor: 'pointer',
            display: 'flex', alignItems: 'center', gap: 10,
            transition: 'border-color var(--transition-fast)',
            flex: 1, maxWidth: 280,
          }}
          onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--amber)' }}
          onMouseLeave={(e) => { e.currentTarget.style.borderColor = '' }}
        >
          <FileText size={18} style={{ color: 'var(--amber)', flexShrink: 0 }} />
          <div style={{ textAlign: 'left' }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>Generate Shift Report</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>View summary & download PDF</div>
          </div>
        </button>
      </div>

      {/* Charts row 1 */}
      <div className="grid-2 mb-4" style={{ marginBottom: 20 }}>
        {/* Search Volume */}
        <div className="card anim-3">
          <div className="card-header">
            <span className="card-title flex items-center gap-2">
              <TrendingUp size={13} />
              Search Volume — 7 Days
            </span>
            <span className="badge badge-cyan">LIVE</span>
          </div>
          {volume.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={volume} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-dim)" />
                <XAxis dataKey="day" tick={{ fill: 'var(--text-muted)', fontSize: 11, fontFamily: 'var(--font-mono)' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 11, fontFamily: 'var(--font-mono)' }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Line type="monotone" dataKey="searches" stroke="var(--amber)" strokeWidth={2} dot={{ fill: 'var(--amber)', strokeWidth: 0, r: 3 }} activeDot={{ r: 5 }} name="Searches" />
                <Line type="monotone" dataKey="detections" stroke="var(--cyan-400)" strokeWidth={2} dot={{ fill: 'var(--cyan-400)', strokeWidth: 0, r: 3 }} activeDot={{ r: 5 }} name="With Results" />
                <Legend wrapperStyle={{ fontFamily: 'var(--font-mono)', fontSize: 11, paddingTop: 8 }} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
              No search data yet
            </div>
          )}
        </div>

        {/* Defect Distribution */}
        <div className="card anim-4">
          <div className="card-header">
            <span className="card-title flex items-center gap-2">
              <AlertTriangle size={13} />
              Defect Distribution
            </span>
          </div>
          {defectData.length > 0 ? (
            <div className="flex items-center gap-4" style={{ height: 200 }}>
              <ResponsiveContainer width="55%" height="100%">
                <PieChart>
                  <Pie
                    data={defectData}
                    cx="50%" cy="50%"
                    innerRadius={50} outerRadius={80}
                    paddingAngle={2}
                    dataKey="value"
                  >
                    {defectData.map((entry, i) => (
                      <Cell key={i} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={TOOLTIP_STYLE} />
                </PieChart>
              </ResponsiveContainer>
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>
                {defectData.map((d) => (
                  <div key={d.name} className="flex items-center gap-2">
                    <div style={{ width: 8, height: 8, borderRadius: 2, background: d.color, flexShrink: 0 }} />
                    <span style={{ fontSize: 11, color: 'var(--text-secondary)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {d.name}
                    </span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: d.color, fontWeight: 600 }}>
                      {d.value}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div style={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
              No detection data yet
            </div>
          )}
        </div>
      </div>

      {/* Charts row 2 */}
      <div className="grid-2">
        {/* Plant Breakdown */}
        <div className="card anim-5">
          <div className="card-header">
            <span className="card-title flex items-center gap-2">
              <Activity size={13} />
              Plant Unit Breakdown
            </span>
          </div>
          {plantData.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={plantData} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-dim)" vertical={false} />
                <XAxis dataKey="plant" tick={{ fill: 'var(--text-muted)', fontSize: 11, fontFamily: 'var(--font-mono)' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 11, fontFamily: 'var(--font-mono)' }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Bar dataKey="total"      name="Total Media"    fill="var(--bg-hover)" radius={[3,3,0,0]} />
                <Bar dataKey="detections" name="Detections"     fill="var(--amber)"    radius={[3,3,0,0]} />
                <Legend wrapperStyle={{ fontFamily: 'var(--font-mono)', fontSize: 11, paddingTop: 8 }} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
              No plant data yet
            </div>
          )}
        </div>

        {/* Recent Activity */}
        <div className="card anim-6">
          <div className="card-header">
            <span className="card-title flex items-center gap-2">
              <Activity size={13} />
              Recent Activity
            </span>
            <span className="badge badge-muted">LIVE FEED</span>
          </div>
          {activity.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
              {activity.map((item, i) => (
                <div
                  key={i}
                  style={{
                    display: 'flex', alignItems: 'flex-start', gap: 10,
                    padding: '9px 0',
                    borderBottom: i < activity.length - 1 ? '1px solid var(--border-dim)' : 'none',
                  }}
                >
                  <span className={`badge ${
                    item.tag === 'TEXT' || item.tag === 'HYBRID' ? 'badge-cyan' :
                    item.tag === 'IMAGE' ? 'badge-amber' :
                    item.tag === 'DETECT' ? 'badge-danger' : 'badge-muted'
                  }`} style={{ marginTop: 1, flexShrink: 0 }}>
                    {item.tag}
                  </span>
                  <span style={{ fontSize: 12, color: 'var(--text-secondary)', flex: 1, lineHeight: 1.4 }}>
                    {item.msg}
                  </span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)', whiteSpace: 'nowrap', marginTop: 1 }}>
                    {item.time}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ padding: '32px 0', textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
              No recent activity
            </div>
          )}
        </div>
      </div>

      {/* My Assignments */}
      {myAssignments.length > 0 && (
        <div className="card" style={{ marginTop: 20 }}>
          <div className="card-header">
            <span className="card-title flex items-center gap-2">
              <UserCheck size={13} />
              My Assignments
            </span>
            <span className="badge badge-amber">{myAssignments.length}</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
            {myAssignments.map((a) => (
              <div
                key={a.id}
                onClick={() => navigate(`/media/detections/${a.detection_id}`)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  padding: '9px 12px', cursor: 'pointer',
                  borderBottom: '1px solid var(--border-dim)',
                  transition: 'background var(--transition-fast)',
                }}
                onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--bg-hover)' }}
                onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
              >
                {a.detection_crop_url && (
                  <div style={{ width: 32, height: 32, borderRadius: 'var(--radius-sm)', overflow: 'hidden', flexShrink: 0, background: 'var(--bg-muted)' }}>
                    <img src={a.detection_crop_url} alt={a.detection_label ?? ''} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                  </div>
                )}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>
                    {a.detection_label ?? 'Detection'}
                  </span>
                </div>
                <span className={`badge ${a.priority === 'critical' ? 'badge-danger' : a.priority === 'high' ? 'badge-amber' : 'badge-muted'}`} style={{ fontSize: 9 }}>
                  {a.priority.toUpperCase()}
                </span>
                <span className={`badge ${a.status === 'open' ? 'badge-cyan' : a.status === 'resolved' ? 'badge-success' : 'badge-muted'}`} style={{ fontSize: 9 }}>
                  {a.status.toUpperCase().replace('_', ' ')}
                </span>
                {a.due_date && (
                  <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                    Due {a.due_date}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
