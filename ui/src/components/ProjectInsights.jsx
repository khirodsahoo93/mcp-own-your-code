import { useMemo } from 'react'
import s from './ProjectInsights.module.css'

function pct(a, b) {
  if (!b) return 0
  return Math.round((a / b) * 100)
}

function daysAgo(ts) {
  if (!ts) return Infinity
  const t = new Date(ts).getTime()
  if (!Number.isFinite(t)) return Infinity
  return (Date.now() - t) / (24 * 3600 * 1000)
}

export default function ProjectInsights({ map, onPickFunction }) {
  const { quality, files } = useMemo(() => {
    const all = []
    const files = Object.entries(map?.by_file || {}).map(([file, fns]) => {
      const total = fns.length
      const annotated = fns.filter(f => f.has_intent).length
      all.push(...fns)
      const withIntent = fns.filter(f => f.has_intent)
      const jumpTo = (withIntent[0] || fns[0])?.qualname ?? null
      return { file, total, annotated, coverage: pct(annotated, total), jumpTo }
    }).sort((a, b) => a.coverage - b.coverage || b.total - a.total)

    const annotatedFns = all.filter(f => f.has_intent && f.intent)
    const avgConfidence = annotatedFns.length
      ? (annotatedFns.reduce((s, f) => s + Number(f.intent?.confidence || 0), 0) / annotatedFns.length).toFixed(1)
      : '—'

    const lowConfidence = annotatedFns.filter(f => Number(f.intent?.confidence || 0) > 0 && Number(f.intent?.confidence || 0) <= 2).length
    const noDecisions = annotatedFns.filter(f => (f.decisions || []).length === 0).length
    const noEvolution = all.filter(f => (f.evolution || []).length === 0).length
    const stale = annotatedFns.filter(f => daysAgo(f.intent?.recorded_at) > 45).length

    return {
      quality: {
        total: all.length,
        annotated: annotatedFns.length,
        avgConfidence,
        lowConfidence,
        noDecisions,
        noEvolution,
        stale,
      },
      files,
    }
  }, [map])

  return (
    <section className={s.wrap}>
      <h3 className={s.title}>Project Insights</h3>
      <div className={s.metrics}>
        <Metric label="Avg confidence" value={quality.avgConfidence} />
        <Metric label="Low confidence" value={quality.lowConfidence} warn={quality.lowConfidence > 0} />
        <Metric label="No decisions" value={quality.noDecisions} warn={quality.noDecisions > 0} />
        <Metric label="No evolution" value={quality.noEvolution} />
        <Metric label="Stale intents" value={quality.stale} warn={quality.stale > 0} />
      </div>

      <h4 className={s.sub}>File coverage heatmap</h4>
      <ul className={s.fileList}>
        {files.slice(0, 12).map(f => (
          <li key={f.file}>
            <button
              type="button"
              className={s.fileRow}
              disabled={!f.jumpTo}
              onClick={() => f.jumpTo && onPickFunction(f.jumpTo)}
            >
              <span className={s.file}>{f.file}</span>
              <span className={s.val}>{f.annotated}/{f.total} ({f.coverage}%)</span>
              <span className={s.track}><span className={s.fill} style={{ width: `${f.coverage}%` }} /></span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

function Metric({ label, value, warn = false }) {
  return (
    <span className={s.metric}>
      <strong className={warn ? s.warn : undefined}>{value}</strong>
      <span>{label}</span>
    </span>
  )
}
