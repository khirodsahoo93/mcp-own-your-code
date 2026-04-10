import { useState, useEffect } from 'react'
import s from './FeatureView.module.css'

export default function FeatureView({ projectPath, onSelect }) {
  const [features, setFeatures] = useState([])
  const [open, setOpen] = useState({})
  const [err, setErr] = useState(null)

  useEffect(() => {
    const q = new URLSearchParams({ project_path: projectPath })
    fetch(`/features?${q}`)
      .then(async r => {
        if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText)
        return r.json()
      })
      .then(d => setFeatures(d.features || []))
      .catch(e => setErr(e.message))
  }, [projectPath])

  function toggle(id) {
    setOpen(o => ({ ...o, [id]: !o[id] }))
  }

  if (err) {
    return <div className={s.error}>{err}</div>
  }

  if (!features.length) {
    return (
      <div className={s.empty}>
        No feature clusters yet. When intents include a <code className={s.code}>feature</code> label, related functions group here.
      </div>
    )
  }

  return (
    <div className={s.container}>
      <p className={s.hint}>Functions linked by the same user-facing feature (MCP tool <code className={s.code}>record_intent</code>).</p>
      <ul className={s.list}>
        {features.map(f => (
          <li key={f.id} className={s.item}>
            <button
              type="button"
              className={s.row}
              onClick={() => toggle(f.id)}
              aria-expanded={!!open[f.id]}
            >
              <span className={s.chev}>{open[f.id] ? '▼' : '▶'}</span>
              <span className={s.title}>{f.title}</span>
              <span className={s.count}>{(f.functions || []).length}</span>
            </button>
            {open[f.id] && (
              <div className={s.panel}>
                {f.description && <p className={s.desc}>{f.description}</p>}
                <ul className={s.fnList}>
                  {(f.functions || []).map(fn => (
                    <li key={`${fn.file}::${fn.qualname}`}>
                      <button
                        type="button"
                        className={s.fnBtn}
                        onClick={() => onSelect(fn.qualname)}
                      >
                        <span className={s.fnName}>{fn.qualname}</span>
                        <span className={s.fnFile}>{fn.file}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
