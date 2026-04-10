import { useMemo, useState, useEffect } from 'react'
import { apiFetch } from '../api.js'
import s from './EvolutionTimeline.module.css'

const REPO_URL = (() => { const u = import.meta.env.VITE_REPO_URL || ''; return u.endsWith('/') ? u.slice(0, -1) : u })()

function matchesDateRange(ts, from, to) {
  if (!ts) return false
  if (from && ts.slice(0, 10) < from) return false
  if (to && ts.slice(0, 10) > to) return false
  return true
}

export default function EvolutionTimeline({ projectPath, onSelect }) {
  const [entries, setEntries] = useState(null)
  const [err, setErr] = useState(null)
  const [q, setQ] = useState('')
  const [file, setFile] = useState('all')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')

  useEffect(() => {
    setEntries(null)
    setErr(null)
    apiFetch(`/evolution?project_path=${encodeURIComponent(projectPath)}&limit=300`)
      .then(async r => {
        if (!r.ok) {
          const d = await r.json().catch(() => ({}))
          throw new Error(d.detail || r.statusText)
        }
        return r.json()
      })
      .then(d => setEntries(d.entries || []))
      .catch(e => setErr(e.message))
  }, [projectPath])

  const files = useMemo(() => {
    const set = new Set((entries || []).map(e => e.file).filter(Boolean))
    return Array.from(set).sort()
  }, [entries])

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return (entries || []).filter(e => {
      if (file !== 'all' && e.file !== file) return false
      if (!matchesDateRange(String(e.changed_at || ''), from, to)) return false
      if (!needle) return true
      const hay = [e.qualname, e.file, e.change_summary, e.reason, e.triggered_by]
        .filter(Boolean)
        .join(' \n')
        .toLowerCase()
      return hay.includes(needle)
    })
  }, [entries, q, file, from, to])

  async function copyHash(hash) {
    if (!hash) return
    try {
      await navigator.clipboard.writeText(hash)
    } catch {}
  }

  if (err) return <div className={s.error}>{err}</div>
  if (!entries) return <div className={s.loading}>Loading timeline…</div>

  return (
    <div className={s.container}>
      <p className={s.hint}>Newest changes first · filter by file/date/search</p>

      <div className={s.filters}>
        <input
          className={s.input}
          value={q}
          onChange={e => setQ(e.target.value)}
          placeholder="Search function, file, summary, reason..."
        />
        <select className={s.select} value={file} onChange={e => setFile(e.target.value)}>
          <option value="all">All files</option>
          {files.map(f => <option key={f} value={f}>{f}</option>)}
        </select>
        <label className={s.dateLabel}>
          From
          <input className={s.date} type="date" value={from} onChange={e => setFrom(e.target.value)} />
        </label>
        <label className={s.dateLabel}>
          To
          <input className={s.date} type="date" value={to} onChange={e => setTo(e.target.value)} />
        </label>
      </div>

      {filtered.length === 0 ? (
        <div className={s.empty}>
          No timeline entries match your filter.
        </div>
      ) : (
        <ul className={s.list}>
          {filtered.map(e => (
            <li key={e.id}>
              <div className={s.row}>
                <button type="button" className={s.main} onClick={() => onSelect(e.qualname)}>
                  <span className={s.when}>{e.changed_at}</span>
                  <span className={s.fn}>{e.qualname}</span>
                  <span className={s.file}>{e.file}</span>
                  <span className={s.summary}>{e.change_summary}</span>
                  {e.reason && <span className={s.reason}>{e.reason}</span>}
                </button>
                <div className={s.actions}>
                  {e.git_hash && (
                    <>
                      <button type="button" className={s.actionBtn} onClick={() => copyHash(e.git_hash)}>
                        Copy hash
                      </button>
                      {REPO_URL ? (
                        <a className={s.actionLink} href={`${REPO_URL}/commit/${e.git_hash}`} target="_blank" rel="noreferrer">
                          View commit
                        </a>
                      ) : null}
                    </>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
