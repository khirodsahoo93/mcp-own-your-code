import { useState, useCallback } from 'react'
import { apiJson } from '../api.js'
import s from './SearchView.module.css'

const MODES = [
  { value: 'keyword',  label: 'Keyword',  title: 'Fast LIKE-based substring search' },
  { value: 'semantic', label: 'Semantic', title: 'Vector similarity search (requires embed first)' },
  { value: 'hybrid',   label: 'Hybrid',   title: 'Merge keyword + semantic scores' },
]

export default function SearchView({ projectPath, onSelect }) {
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState('keyword')
  const [results, setResults] = useState(null)
  const [modeUsed, setModeUsed] = useState(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState(null)
  // null | 'checking' | 'indexing' | result object | { error } | { info }
  const [embedState, setEmbedState] = useState(null)

  const runSearch = useCallback(async () => {
    const q = query.trim()
    if (!q) {
      setResults([])
      setModeUsed(null)
      return
    }
    setLoading(true)
    setErr(null)
    try {
      const d = await apiJson('/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_path: projectPath, query: q, mode }),
      })
      setResults(d.results || [])
      setModeUsed(d.mode || mode)
    } catch (e) {
      setErr(e.message)
      setResults(null)
      setModeUsed(null)
    } finally {
      setLoading(false)
    }
  }, [projectPath, query, mode])

  const runEmbed = useCallback(async () => {
    setEmbedState('checking')
    try {
      const pre = await apiJson(
        `/embed/preflight?project_path=${encodeURIComponent(projectPath)}`
      )
      if (!pre.semantic_stack_installed) {
        setEmbedState({ error: pre.message || 'Semantic stack not installed.' })
        return
      }
      if (!pre.project_registered) {
        setEmbedState({ error: pre.message || 'Project not registered.' })
        return
      }
      if (!pre.can_start) {
        setEmbedState({ info: pre.message || 'Nothing to index.' })
        return
      }
      const warnText = (pre.warnings || []).filter(Boolean).join('\n')
      const ok = window.confirm(
        [pre.message, warnText && `Note:\n${warnText}`, 'Start indexing now?']
          .filter(Boolean)
          .join('\n\n')
      )
      if (!ok) {
        setEmbedState(null)
        return
      }
      setEmbedState('indexing')
      const d = await apiJson(`/embed?project_path=${encodeURIComponent(projectPath)}`, { method: 'POST' })
      const jobId = d.job_id
      for (let i = 0; i < 600; i++) {
        await new Promise(res => setTimeout(res, 500))
        const sd = await apiJson(`/embed/${jobId}`)
        if (sd.status === 'done') {
          setEmbedState(sd)
          return
        }
        if (sd.status === 'error') {
          setEmbedState({ error: sd.error })
          return
        }
      }
      setEmbedState({ error: 'Timed out waiting for embedding to complete.' })
    } catch (e) {
      setEmbedState({ error: e.message })
    }
  }, [projectPath])

  const needsEmbed = mode === 'semantic' || mode === 'hybrid'
  const embedBusy = embedState === 'checking' || embedState === 'indexing'

  return (
    <div className={s.container}>
      <div className={s.modeBar}>
        {MODES.map(m => (
          <button
            key={m.value}
            type="button"
            className={`${s.modeBtn} ${mode === m.value ? s.modeBtnActive : ''}`}
            title={m.title}
            onClick={() => setMode(m.value)}
          >
            {m.label}
          </button>
        ))}
      </div>
      <div className={s.controls}>
        <input
          className={s.input}
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="e.g. payments, auth, error handling…"
          onKeyDown={e => e.key === 'Enter' && runSearch()}
        />
        <button type="button" className={s.btn} onClick={runSearch} disabled={loading}>
          {loading ? '…' : 'Search'}
        </button>
      </div>

      {needsEmbed && (
        <div className={s.embedRow}>
          <div className={s.embedText}>
            {mode === 'semantic'
              ? 'Semantic search requires vector embeddings.'
              : 'Hybrid search merges keyword + vector scores.'}
          </div>
          <button
            type="button"
            className={s.embedBtn}
            onClick={runEmbed}
            disabled={embedBusy}
          >
            {embedState === 'checking'
              ? 'Checking…'
              : embedState === 'indexing'
                ? 'Indexing…'
                : 'Index Embeddings'}
          </button>
          {embedState && typeof embedState === 'object' && (
            embedState.error
              ? <div className={s.embedErr}>{embedState.error}</div>
              : embedState.info
                ? <div className={s.embedOk}>{embedState.info}</div>
                : <div className={s.embedOk}>
                    Done: {embedState.embedded} indexed
                    {embedState.skipped > 0 ? `, ${embedState.skipped} already up-to-date` : ''}
                    {' '}· {embedState.model}
                  </div>
          )}
        </div>
      )}
      {mode === 'keyword' && (
        <p className={s.hint}>Keyword search over names and stored intent text.</p>
      )}

      {err && <div className={s.error}>{err}</div>}

      {results && (
        <div className={s.meta}>
          {results.length === 0
            ? 'No matches.'
            : `${results.length} match${results.length === 1 ? '' : 'es'}`}
          {modeUsed && modeUsed !== mode && (
            <span className={s.modeTag}> · routed to {modeUsed}</span>
          )}
        </div>
      )}

      {results && results.length > 0 && (
        <ul className={s.list}>
          {results.map(r => (
            <li key={`${r.file}::${r.qualname}`}>
              <button
                type="button"
                className={s.hit}
                onClick={() => onSelect(r.qualname)}
              >
                <div className={s.hitHeader}>
                  <span className={s.name}>{r.qualname}</span>
                  {r.score != null && (
                    <span className={s.score}>{(r.score * 100).toFixed(0)}%</span>
                  )}
                </div>
                <span className={s.file}>{r.file}{r.lineno ? `:${r.lineno}` : ''}</span>
                {r.user_request && (
                  <span className={s.snip}>{r.user_request.slice(0, 120)}{r.user_request.length > 120 ? '…' : ''}</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
