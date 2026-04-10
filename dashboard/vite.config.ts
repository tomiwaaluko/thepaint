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
    allowedHosts: ['thepaint-production.up.railway.app'],
  },
  server: {
    proxy: {
      '/v1': 'http://localhost:8000',
    },
  },
})
