import { useCallback, useEffect, useState } from 'react'
import { Download, ChevronLeft, ChevronRight } from 'lucide-react'
import type { WasteCamera, WasteInspection } from '../../types/api'
import { exportWasteInspections, listWasteInspections } from '../../api/client'

function RiskBadge({ risk }: { risk: string }) {
  return <span className={`wv-risk-badge ${risk}`}>{risk.toUpperCase()}</span>
}

export default function InspectorLog({ cameras }: { cameras: WasteCamera[] }) {
  const [inspections, setInspections] = useState<WasteInspection[]>([])
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [filterCamera, setFilterCamera] = useState('')
  const [filterRisk, setFilterRisk] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const load = useCallback(() => {
    setLoading(true)
    listWasteInspections({
      camera_uuid: filterCamera || undefined,
      overall_risk: filterRisk || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      page,
      page_size: 25,
    })
      .then(r => {
        setInspections(r.data.items)
        setTotalPages(r.data.pagination.total_pages)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [filterCamera, filterRisk, dateFrom, dateTo, page])

  useEffect(() => { load() }, [load])

  const handleExport = async () => {
    try {
      const r = await exportWasteInspections({
        camera_uuid: filterCamera || undefined,
        overall_risk: filterRisk || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      })
      const url = URL.createObjectURL(r.data as Blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'wastevision_inspections.csv'
      a.click()
      URL.revokeObjectURL(url)
    } catch { /* ignore */ }
  }

  return (
    <div>
      {/* Filters */}
      <div style={{
        display: 'flex', flexWrap: 'wrap', gap: 10, padding: '12px 16px',
        borderBottom: '1px solid var(--wv-border)',
      }}>
        <select
          className="wv-select"
          style={{ fontSize: '0.72rem' }}
          value={filterCamera}
          onChange={e => { setFilterCamera(e.target.value); setPage(1) }}
        >
          <option value="">All Cameras</option>
          {cameras.map(c => <option key={c.camera_uuid} value={c.camera_uuid}>{c.name}</option>)}
        </select>
        <select
          className="wv-select"
          style={{ fontSize: '0.72rem' }}
          value={filterRisk}
          onChange={e => { setFilterRisk(e.target.value); setPage(1) }}
        >
          <option value="">All Risk Levels</option>
          {['low', 'medium', 'high', 'critical'].map(r => (
            <option key={r} value={r}>{r.toUpperCase()}</option>
          ))}
        </select>
        <input
          type="datetime-local"
          className="wv-input"
          style={{ width: 200, fontSize: '0.72rem' }}
          value={dateFrom}
          onChange={e => { setDateFrom(e.target.value); setPage(1) }}
          placeholder="From"
        />
        <input
          type="datetime-local"
          className="wv-input"
          style={{ width: 200, fontSize: '0.72rem' }}
          value={dateTo}
          onChange={e => { setDateTo(e.target.value); setPage(1) }}
          placeholder="To"
        />
        <button className="wv-btn wv-btn-ghost" onClick={handleExport} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Download size={13} />
          EXPORT CSV
        </button>
      </div>

      {/* Table */}
      <div style={{ overflowX: 'auto' }}>
        <table className="wv-table">
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Camera</th>
              <th>Seq#</th>
              <th>Risk</th>
              <th>Confidence</th>
              <th>Top Contaminant</th>
              <th>Blocked</th>
              <th>VLM ms</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={8} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 24 }}>
                  Loading...
                </td>
              </tr>
            ) : inspections.length === 0 ? (
              <tr>
                <td colSpan={8} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 24 }}>
                  No inspections found.
                </td>
              </tr>
            ) : inspections.map(insp => {
              const topAlert = insp.contamination_alerts?.[0]
              return (
                <tr key={insp.inspection_uuid}>
                  <td style={{ whiteSpace: 'nowrap', fontSize: '0.65rem' }}>
                    {new Date(insp.created_at).toLocaleString()}
                  </td>
                  <td>
                    {cameras.find(c => c.camera_uuid === insp.camera_uuid)?.name ?? insp.camera_uuid.slice(0, 8)}
                  </td>
                  <td style={{ color: 'var(--text-muted)' }}>#{insp.sequence_no}</td>
                  <td><RiskBadge risk={insp.overall_risk} /></td>
                  <td style={{ color: 'var(--text-secondary)' }}>{(insp.confidence * 100).toFixed(1)}%</td>
                  <td>
                    {topAlert
                      ? <span style={{ color: topAlert.severity === 'critical' ? 'var(--wv-red)' : 'var(--wv-amber)' }}>
                          {topAlert.item}
                        </span>
                      : <span style={{ color: 'var(--text-muted)' }}>—</span>
                    }
                  </td>
                  <td>
                    {insp.line_blockage
                      ? <span style={{ color: 'var(--wv-red)', fontWeight: 700 }}>YES</span>
                      : <span style={{ color: 'var(--text-muted)' }}>—</span>
                    }
                  </td>
                  <td style={{ color: 'var(--text-muted)', fontSize: '0.65rem' }}>
                    {insp.processing_time_ms ?? '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          gap: 12, padding: '12px 16px', borderTop: '1px solid var(--wv-border)',
        }}>
          <button className="wv-btn wv-btn-ghost" style={{ padding: '4px 8px' }} disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
            <ChevronLeft size={14} />
          </button>
          <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', letterSpacing: '0.08em' }}>
            PAGE {page} / {totalPages}
          </span>
          <button className="wv-btn wv-btn-ghost" style={{ padding: '4px 8px' }} disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>
            <ChevronRight size={14} />
          </button>
        </div>
      )}
    </div>
  )
}
