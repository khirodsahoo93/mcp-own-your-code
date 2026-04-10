import s from './CoverageBar.module.css'

export default function CoverageBar({ total, annotated, coverage, features, unannotated, hookBacklog = [] }) {
  const pending = hookBacklog.length
  return (
    <>
      <div className={s.bar}>
        <div className={s.left}>
          <div className={s.track}>
            <div className={s.fill} style={{ width: `${coverage}%` }} />
          </div>
          <span className={s.label}>
            <strong>{coverage}%</strong> annotated — {annotated}/{total} functions
          </span>
        </div>
        <div className={s.right}>
          <Chip val={features} label="features" color="var(--blue)" />
          <Chip val={total - annotated} label="need intent" color="var(--amber)" />
          {pending > 0 && (
            <Chip val={pending} label="hook queue" color="var(--orange)" />
          )}
          {pending === 0 && unannotated?.length > 0 && (
            <span className={s.hint} title={unannotated.join('\n')}>
              {unannotated.slice(0, 2).join(', ')}{unannotated.length > 2 ? ` +${unannotated.length - 2}` : ''}
            </span>
          )}
        </div>
      </div>
      {pending > 0 && (
        <div className={s.alert} role="status">
          <span className={s.alertTitle}>Editor hook queue</span>
          <span className={s.alertBody}>
            {pending} file{pending === 1 ? '' : 's'} still need <code className={s.code}>record_intent</code> or{' '}
            <code className={s.code}>mark_file_reviewed</code> — drain the queue via MCP when appropriate.
          </span>
          <span className={s.alertFiles}>
            {hookBacklog.slice(0, 4).map(b => (
              <span key={b.file} className={s.fileChip} title={`${b.hook_events} writes · ${b.functions_without_intent} fn without intent`}>
                {b.file}
              </span>
            ))}
            {pending > 4 ? <span className={s.more}>+{pending - 4}</span> : null}
          </span>
        </div>
      )}
    </>
  )
}

function Chip({ val, label, color }) {
  return (
    <span style={{ display:'flex', gap:4, alignItems:'center', fontSize:11 }}>
      <strong style={{ color, fontFamily:'var(--mono)' }}>{val}</strong>
      <span style={{ color:'var(--text3)' }}>{label}</span>
    </span>
  )
}
