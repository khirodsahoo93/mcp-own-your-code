import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5175,
    proxy: {
      '/projects': 'http://localhost:8002',
      '/register': 'http://localhost:8002',
      '/map':      'http://localhost:8002',
      '/features': 'http://localhost:8002',
      '/function': 'http://localhost:8002',
      '/search':   'http://localhost:8002',
      '/stats':    'http://localhost:8002',
      '/graph':    'http://localhost:8002',
    },
  },
})
