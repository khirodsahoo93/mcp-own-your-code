/** Optional API key for deployments with OWN_YOUR_CODE_API_KEY (sent as X-Api-Key). */
const STORAGE_KEY = 'ownYourCodeApiKey'

export function getApiKey() {
  if (typeof localStorage === 'undefined') return ''
  return localStorage.getItem(STORAGE_KEY) || ''
}

export function setApiKey(key) {
  if (typeof localStorage === 'undefined') return
  if (key && key.trim()) localStorage.setItem(STORAGE_KEY, key.trim())
  else localStorage.removeItem(STORAGE_KEY)
}

export function apiFetch(url, opts = {}) {
  const headers = new Headers(opts.headers || undefined)
  const k = getApiKey()
  if (k) headers.set('X-Api-Key', k)
  return fetch(url, { ...opts, headers })
}

/**
 * Fetch JSON from the FastAPI backend. Throws with a clear message if the body is HTML
 * (common when Vite proxies to the wrong port or only the SPA is running).
 */
export async function apiJson(url, opts = {}) {
  const res = await apiFetch(url, opts)
  const text = await res.text()

  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`
    try {
      const j = JSON.parse(text)
      if (j.detail != null) {
        msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
      }
    } catch {
      const t = text.trimStart()
      if (t.startsWith('<')) {
        msg =
          'Server returned an HTML error page. Check that FastAPI is running and Vite ' +
          'VITE_API_PROXY points at it (see README).'
      } else if (text) {
        msg = text.slice(0, 400)
      }
    }
    throw new Error(msg)
  }

  const trimmed = text.trimStart()
  if (trimmed.startsWith('<')) {
    throw new Error(
      'Server returned HTML instead of JSON (often the React index page). ' +
        'Start uvicorn from the repo root, then either use the same port as Vite’s default proxy ' +
        '(8002) or set VITE_API_PROXY in ui/.env.development to your API URL, e.g. http://127.0.0.1:8003'
    )
  }

  try {
    return JSON.parse(text)
  } catch (e) {
    throw new Error(`Invalid JSON from ${url}: ${e.message}`)
  }
}
