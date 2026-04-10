import { useState, useEffect, useCallback } from 'react'
import { apiFetch, getApiKey, setApiKey } from '../api.js'
import s from './ServerFooter.module.css'

export default function ServerFooter({ onApiKeySaved }) {
  const [info, setInfo] = useState(null)
  const [err, setErr] = useState(null)
  const [keyOpen, setKeyOpen] = useState(false)
  const [keyDraft, setKeyDraft] = useState('')

  const load = useCallback(async () => {
    setErr(null)
    try {
      const r = await apiFetch('/server-info')
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText)
      setInfo(await r.json())
    } catch (e) {
      setErr(e.message)
      setInfo(null)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (info?.api_auth_required && !getApiKey()) setKeyOpen(true)
  }, [info])

  function saveKey() {
    setApiKey(keyDraft)
    setKeyOpen(false)
    load()
    onApiKeySaved?.()
  }

  const ver = info?.version
  const sem = info?.semantic_stack_installed

  return (
    <footer className={s.footer}>
      <div className={s.row}>
        {err && <span className={s.err}>{err}</span>}
        {info && !err && (
          <>
            <span className={s.muted}>API</span>
            {ver && <span className={s.chip} title="Package version">v{ver}</span>}
            <span
              className={`${s.chip} ${sem ? s.ok : s.warn}`}
              title="sentence-transformers + numpy for semantic search"
            >
              {sem ? 'semantic' : 'keyword-only'}
            </span>
            {info.api_auth_required && (
              <span className={s.chip} title="Set X-Api-Key in footer">
                auth on
              </span>
            )}
            <a className={s.link} href="/docs" target="_blank" rel="noreferrer">
              Swagger
            </a>
            <a className={s.link} href="/redoc" target="_blank" rel="noreferrer">
              ReDoc
            </a>
            {info.api_auth_required && (
              <button type="button" className={s.keyBtn} onClick={() => { setKeyDraft(getApiKey()); setKeyOpen(o => !o) }}>
                API key…
              </button>
            )}
          </>
        )}
      </div>
      {keyOpen && (
        <div className={s.keyRow}>
          <input
            className={s.keyInput}
            type="password"
            autoComplete="off"
            placeholder="X-Api-Key (stored in this browser only)"
            value={keyDraft}
            onChange={e => setKeyDraft(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && saveKey()}
          />
          <button type="button" className={s.saveBtn} onClick={saveKey}>
            Save
          </button>
        </div>
      )}
    </footer>
  )
}
