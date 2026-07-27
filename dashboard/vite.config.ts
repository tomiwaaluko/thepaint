import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-react': ['react', 'react-dom', 'react-router-dom'],
          'vendor-recharts': ['recharts'],
          'vendor-query': ['@tanstack/react-query'],
        },
      },
    },
  },
  preview: {
    // Explicit hosts only. `.up.railway.app` is a wildcard that accepts ANY
    // Railway subdomain as a Host header, including someone else's deployment.
    allowedHosts: [
      'thepaint-production.up.railway.app',
      'thepaint-staging.up.railway.app',
    ],
  },
  server: {
    // Explicit hosts only. `.up.railway.app` is a wildcard that accepts ANY
    // Railway subdomain as a Host header, including someone else's deployment.
    allowedHosts: [
      'thepaint-production.up.railway.app',
      'thepaint-staging.up.railway.app',
    ],
    proxy: {
      '/v1': 'http://localhost:8000',
    },
  },
})
