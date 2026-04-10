import { useState, useEffect } from 'react'
import { apiFetch } from '../api.js'
import s from './ProjectBar.module.css'

export default function ProjectBar({ onLoaded, current }) {
  const [path, setPath]     = useState('')
  const [loading, setLoading] = useState(false)
  const [projects, setProjects] = useState([])
  const [open, setOpen]     = useState(false)

  useEffect(() => {
    apiFetch('/projects').then(r => r.json()).then(d => setProjects(d.projects ?? []))
  }, [current])

  async function register() {
    if (!path.trim()) return
    setLoading(true)
    try {
      const r = await apiFetch('/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: path.trim() }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail)
      onLoaded({ path: path.trim(), ...d })
      setPath('')
      setOpen(false)
    } catch (e) { alert(e.message) }
    finally { setLoading(false) }
  }

  function select(proj) {
    onLoaded({ path: proj.path, name: proj.name })
    setOpen(false)
  }

  return (
    <div className={s.bar}>
      {current && (
        <div className={s.current} onClick={() => setOpen(o => !o)}>
          <span className={s.currentName}>{current.name || current.path.split('/').slice(-1)[0]}</span>
          <span className={s.currentPath}>{current.path}</span>
          <span className={s.arrow}>{open ? '▲' : '▼'}</span>
        </div>
      )}

      {(!current || open) && (
        <div className={s.panel}>
          {projects.length > 0 && (
            <div className={s.recentList}>
              {projects.map(p => (
                <button key={p.path} className={s.recentItem} onClick={() => select(p)}>
                  <span className={s.rName}>{p.name || p.path.split('/').slice(-1)[0]}</span>
                  <span className={s.rPath}>{p.path}</span>
                </button>
              ))}
            </div>
          )}
          <div className={s.inputRow}>
            <input className={s.input} value={path} onChange={e => setPath(e.target.value)}
              placeholder="/path/to/project" onKeyDown={e => e.key === 'Enter' && register()} />
            <button className={s.btn} onClick={register} disabled={loading}>
              {loading ? '…' : 'Register'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
