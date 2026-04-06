import { useEffect, useState } from 'react'
import { MessageSquare, Send, Trash2 } from 'lucide-react'
import type { CommentResponse } from '../types/api'
import { getComments, createComment, deleteComment } from '../api/client'
import { useAuth } from '../context/AuthContext'

interface CommentThreadProps {
  contentType: string
  objectId: number
}

export default function CommentThread({ contentType, objectId }: CommentThreadProps) {
  const { session } = useAuth()
  const [comments, setComments] = useState<CommentResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [text, setText] = useState('')
  const [posting, setPosting] = useState(false)

  useEffect(() => {
    setLoading(true)
    getComments({ content_type: contentType, object_id: objectId })
      .then((r) => setComments(r.data.items))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [contentType, objectId])

  const handlePost = async () => {
    if (!text.trim()) return
    setPosting(true)
    try {
      const r = await createComment({
        content_type: contentType,
        object_id: objectId,
        text: text.trim(),
      })
      setComments((prev) => [...prev, r.data])
      setText('')
    } catch { /* ignore */ }
    setPosting(false)
  }

  const handleDelete = async (id: number) => {
    try {
      await deleteComment(id)
      setComments((prev) => prev.filter((c) => c.id !== id))
    } catch { /* ignore */ }
  }

  const formatTime = (d: string) => {
    const dt = new Date(d)
    const now = new Date()
    const diffMin = Math.floor((now.getTime() - dt.getTime()) / 60000)
    if (diffMin < 1) return 'just now'
    if (diffMin < 60) return `${diffMin}m ago`
    const diffHr = Math.floor(diffMin / 60)
    if (diffHr < 24) return `${diffHr}h ago`
    return dt.toLocaleDateString()
  }

  const currentUserId = session?.user?.id

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title flex items-center gap-2">
          <MessageSquare size={12} />
          Comments
          {comments.length > 0 && (
            <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', background: 'var(--bg-muted)', color: 'var(--text-muted)', borderRadius: 3, padding: '1px 5px' }}>
              {comments.length}
            </span>
          )}
        </span>
      </div>

      {/* Comment list */}
      {loading ? (
        <div style={{ padding: 16, textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>Loading...</div>
      ) : comments.length === 0 ? (
        <div style={{ padding: 16, textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>No comments yet</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
          {comments.map((c) => (
            <div key={c.id} style={{
              padding: '8px 12px', borderBottom: '1px solid var(--border-dim)',
              display: 'flex', gap: 8,
            }}>
              <div style={{
                width: 26, height: 26, borderRadius: '50%', flexShrink: 0,
                background: 'linear-gradient(135deg, var(--amber-700), var(--amber-500))',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 10, fontWeight: 700, color: '#000',
              }}>
                {(c.author_name?.[0] || c.author_email[0]).toUpperCase()}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                  <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>
                    {c.author_name || c.author_email.split('@')[0]}
                  </span>
                  <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                    {formatTime(c.created_at)}
                  </span>
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                  {c.text}
                </div>
              </div>
              {currentUserId === c.author_id && (
                <button className="btn btn-ghost btn-icon" onClick={() => handleDelete(c.id)} title="Delete" style={{ alignSelf: 'flex-start' }}>
                  <Trash2 size={11} style={{ color: 'var(--text-muted)' }} />
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Input */}
      <div style={{ padding: '8px 12px', display: 'flex', gap: 8 }}>
        <input
          className="form-input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Add a comment..."
          onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handlePost()}
          style={{ flex: 1, fontSize: 12 }}
        />
        <button
          className="btn btn-primary btn-sm"
          onClick={handlePost}
          disabled={posting || !text.trim()}
        >
          <Send size={12} />
        </button>
      </div>
    </div>
  )
}
