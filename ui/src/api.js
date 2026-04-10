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
