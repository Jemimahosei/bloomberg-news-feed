import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In development the API runs on :8080 (go run ./cmd/server) and the
// dev server proxies /api and /healthz to it. Override the target with
// VITE_API_PROXY when the API runs on another port, e.g.:
// VITE_API_PROXY=http://localhost:18080 npm run dev
// In production the Go binary serves this build from the same origin, so
// no proxy is needed.
const apiTarget = process.env.VITE_API_PROXY ?? 'http://localhost:8080'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': apiTarget,
      '/healthz': apiTarget,
    },
  },
})
