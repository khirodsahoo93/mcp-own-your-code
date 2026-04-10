import { useState, useEffect } from 'react'
import s from './IntentMap.module.css'

export default function IntentMap({ projectPath, selected, onSelect }) {
  const [map, setMap]       = useState(null)
  const [filter, setFilter] = useState('all')  // all | annotated | unannotated
  const [search, setSearch] = useState('')

  useEffect(() => {
    fetch(`/map?project_path=${encodeURIComponent(projectPath)}`)
      .then(r => r.json()).then(setMap)
  }, [projectPath])

  if (!map) return <div className={s.loading}>Loading map…</div>

  const entries = Object.entries(map.by_file)

  const groups = entries.map(([file, fns]) => {
    const visible = fns.filter(fn => {
      const matchFilter = filter === 'all' || (filter === 'annotated' ? fn.has_intent : !fn.has_intent)
      const ft = (fn.feature_titles || []).join(' ').toLowerCase()
      const matchSearch = !search || fn.qualname.toLowerCase().includes(search.toLowerCase()) ||
        (fn.intent?.user_request || '').toLowerCase().includes(search.toLowerCase()) ||
        ft.includes(search.toLowerCase())
      return matchFilter && matchSearch
    })
    if (!visible.length) return null
    return (
      <div key={file} className={s.group}>
        <div className={s.fileHeader}>📄 {file}</div>
        {visible.map(fn => (
          <button
            key={fn.qualname}
            className={`${s.fnRow} ${selected === fn.qualname ? s.fnRowActive : ''}`}
            onClick={() => onSelect(fn.qualname)}
          >
            <span className={s.dot} style={{ background: fn.has_intent ? 'var(--green)' : 'var(--text3)' }} />
            <div className={s.fnBody}>
              <div className={s.fnNameRow}>
                <span className={s.fnName}>{fn.name}</span>
                {fn.language && fn.language !== 'python' && (
                  <span className={s.lang}>{fn.language}</span>
                )}
              </div>
              {(fn.feature_titles || []).length > 0 && (
                <span className={s.fnFeature}>{(fn.feature_titles || []).join(' · ')}</span>
              )}
              {fn.has_intent && fn.intent?.user_request && (
                <span className={s.fnIntent}>
                  {fn.intent.user_request.slice(0, 60)}{fn.intent.user_request.length > 60 ? '…' : ''}
                </span>
              )}
              {!fn.has_intent && <span className={s.fnNoIntent}>not yet annotated</span>}
            </div>
            {fn.intent?.confidence && (
              <span className={s.conf} title="annotation confidence">
                {'●'.repeat(fn.intent.confidence)}{'○'.repeat(5 - fn.intent.confidence)}
              </span>
            )}
          </button>
        ))}
      </div>
    )
  })
  const hasVisible = groups.some(Boolean)

  return (
    <div className={s.container}>
      <div className={s.controls}>
        <input className={s.search} placeholder="Filter functions…" value={search} onChange={e => setSearch(e.target.value)} />
        <div className={s.filterRow}>
          {['all','annotated','unannotated'].map(f => (
            <button key={f} className={`${s.filter} ${filter===f?s.fa:''}`} onClick={() => setFilter(f)}>
              {f === 'all' ? 'all' : f === 'annotated' ? '✅' : '○'}
            </button>
          ))}
        </div>
      </div>

      <div className={s.list}>
        {hasVisible ? (
          groups
        ) : (
          <div className={s.empty}>
            {entries.length === 0
              ? 'No functions in the map yet.'
              : 'No functions match this filter or search.'}
          </div>
        )}
      </div>
    </div>
  )
}
