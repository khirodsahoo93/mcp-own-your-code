import { useMemo, useState, useEffect } from 'react'
import { apiFetch } from '../api.js'
import s from './FunctionDetail.module.css'

const REPO_URL = (() => { const u = import.meta.env.VITE_REPO_URL || ''; return u.endsWith('/') ? u.slice(0, -1) : u })()

function getHealth(latest, evolution) {
  return [
    !latest ? { label: 'No intent', tone: 'warn' } : null,
    latest && Number(latest.confidence || 0) > 0 && Number(latest.confidence || 0) <= 2 ? { label: 'Low confidence', tone: 'warn' } : null,
    (evolution || []).length === 0 ? { label: 'No evolution yet', tone: 'muted' } : null,
    (evolution || []).length >= 5 ? { label: 'High churn', tone: 'warn' } : null,
  ].filter(Boolean)
}

export default function FunctionDetail({ projectPath, functionName, onClose }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [order, setOrder] = useState('asc')

  useEffect(() => {
    if (!functionName) return
    setData(null)
    setErr(null)
    const q = new URLSearchParams({ project_path: projectPath, function_name: functionName })
    apiFetch(`/function?${q}`)
      .then(async r => {
        if (!r.ok) {
          const d = await r.json().catch(() => ({}))
          throw new Error(d.detail || r.statusText)
        }
        return r.json()
      })
      .then(setData)
      .catch(e => setErr(e.message))
  }, [projectPath, functionName])

  const intents = data?.intents || []
  const latest = intents[0]
  const older = intents.slice(1)
  const evolutionSorted = useMemo(() => {
    const arr = [...(data?.evolution || [])].sort((a, b) => String(a.changed_at || '').localeCompare(String(b.changed_at || '')) || (a.id ?? 0) - (b.id ?? 0))
    return order === 'asc' ? arr : arr.reverse()
  }, [data, order])
  const health = getHealth(latest, evolutionSorted)

  async function copyText(text) {
    if (!text) return
    try {
      await navigator.clipboard.writeText(text)
    } catch {}
  }

  async function copyIntentTemplate() {
    const payload = `record_intent\nproject_path=\"${projectPath}\"\nfile=\"${data?.file || ''}\"\nfunction_name=\"${data?.qualname || ''}\"\nuser_request=\"...\"\nreasoning=\"...\"\nimplementation_notes=\"...\"\nfeature=\"...\"\nconfidence=4`
    await copyText(payload)
  }

  async function copyEvolutionTemplate() {
    const payload = `record_evolution\nproject_path=\"${projectPath}\"\nfile=\"${data?.file || ''}\"\nfunction_name=\"${data?.qualname || ''}\"\nchange_summary=\"...\"\nreason=\"...\"\ntriggered_by=\"...\"`
    await copyText(payload)
  }

  if (err) {
    return (
      <div className={s.wrap}>
        <header className={s.header}>
          <button type="button" className={s.close} onClick={onClose} aria-label="Close">×</button>
          <span className={s.title}>Could not load function</span>
        </header>
        <p className={s.error}>{err}</p>
      </div>
    )
  }

  if (!data) {
    return (
      <div className={s.wrap}>
        <div className={s.loading}>Loading…</div>
      </div>
    )
  }

  return (
    <div className={s.wrap}>
      <header className={s.header}>
        <button type="button" className={s.close} onClick={onClose} aria-label="Close">×</button>
        <div className={s.headText}>
          <h1 className={s.fnTitle}>{data.qualname}</h1>
          <p className={s.meta}>
            <span className={s.file}>📄 {data.file}</span>
            {data.lineno ? <span className={s.line}>line {data.lineno}</span> : null}
          </p>
          {health.length > 0 && (
            <div className={s.health}>
              {health.map(h => <span key={h.label} className={`${s.badge} ${h.tone === 'warn' ? s.badgeWarn : s.badgeMuted}`}>{h.label}</span>)}
            </div>
          )}
        </div>
      </header>

      <div className={s.quickActions}>
        <button type="button" className={s.qaBtn} onClick={copyIntentTemplate}>Copy record_intent template</button>
        <button type="button" className={s.qaBtn} onClick={copyEvolutionTemplate}>Copy record_evolution template</button>
      </div>

      {data.signature && <pre className={s.sig}>{data.signature}</pre>}

      {!latest && (
        <section className={s.section}>
          <h2 className={s.h2}>Intent</h2>
          <p className={s.muted}>Not annotated yet. Use MCP <code className={s.code}>record_intent</code> or <code className={s.code}>annotate_existing</code>.</p>
        </section>
      )}

      {latest && (
        <section className={s.section}>
          <h2 className={s.h2}>Why it exists</h2>
          <p className={s.block}>{latest.user_request}</p>
          {(latest.agent_reasoning || latest.claude_reasoning) && (
            <>
              <h3 className={s.h3}>Agent reasoning</h3>
              <p className={s.block}>{latest.agent_reasoning || latest.claude_reasoning}</p>
            </>
          )}
          {latest.implementation_notes && (
            <>
              <h3 className={s.h3}>Implementation notes</h3>
              <p className={s.block}>{latest.implementation_notes}</p>
            </>
          )}
          <p className={s.confidence}>Confidence: {latest.confidence ?? '—'} / 5</p>
        </section>
      )}

      {(data.decisions || []).length > 0 && (
        <section className={s.section}>
          <h2 className={s.h2}>Decisions &amp; tradeoffs</h2>
          <ul className={s.list}>
            {(data.decisions || []).map(d => (
              <li key={d.id} className={s.card}>
                <div className={s.cardTitle}>{d.decision}</div>
                <p className={s.cardReason}>{d.reason}</p>
                {(d.alternatives || []).length > 0 && (
                  <p className={s.alt}><span className={s.altLabel}>Alternatives considered:</span> {(d.alternatives || []).join('; ')}</p>
                )}
                {d.constraint_ && <p className={s.alt}><span className={s.altLabel}>Constraint:</span> {d.constraint_}</p>}
                <span className={s.when}>{d.recorded_at}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {evolutionSorted.length > 0 && (
        <section className={s.section}>
          <div className={s.evHead}>
            <h2 className={s.h2}>Evolution</h2>
            <button type="button" className={s.orderBtn} onClick={() => setOrder(order === 'asc' ? 'desc' : 'asc')}>
              {order === 'asc' ? 'Oldest first' : 'Newest first'}
            </button>
          </div>
          <ul className={s.timeline}>
            {evolutionSorted.map(e => (
              <li key={e.id} className={s.evItem}>
                <span className={s.evWhen}>{e.changed_at}</span>
                <div className={s.evWhat}>{e.change_summary}</div>
                {e.reason && <div className={s.evWhy}>{e.reason}</div>}
                {e.triggered_by && <div className={s.evTrig}>Triggered by: {e.triggered_by}</div>}
                {e.git_hash && (
                  <div className={s.evActions}>
                    <span className={s.git}>{e.git_hash}</span>
                    <button type="button" className={s.inlineBtn} onClick={() => copyText(e.git_hash)}>Copy hash</button>
                    {REPO_URL ? <a className={s.inlineLink} href={`${REPO_URL}/commit/${e.git_hash}`} target="_blank" rel="noreferrer">View commit</a> : null}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {older.length > 0 && (
        <section className={s.section}>
          <h2 className={s.h2}>Earlier intent records</h2>
          <ul className={s.list}>
            {older.map(i => (
              <li key={i.id} className={s.card}>
                <span className={s.when}>{i.recorded_at}</span>
                <p className={s.block}>{i.user_request}</p>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
