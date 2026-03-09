import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  preview: {
    allowedHosts: ['thepaint-production.up.railway.app'],
  },
  server: {
    proxy: {
      '/v1': 'http://localhost:8000',
    },
  },
})
