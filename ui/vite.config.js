import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

const API_PATHS = [
  '/projects',
  '/register',
  '/map',
  '/features',
  '/function',
  '/search',
  '/stats',
  '/graph',
  '/evolution',
  '/embed',
  '/server-info',
  '/health',
  '/docs',
  '/openapi.json',
  '/redoc',
]

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '')
  const target = env.VITE_API_PROXY || 'http://127.0.0.1:8002'
  const proxy = {}
  for (const path of API_PATHS) {
    proxy[path] = { target, changeOrigin: true }
  }

  return {
    plugins: [react()],
    server: {
      port: 5175,
      proxy,
    },
  }
})
