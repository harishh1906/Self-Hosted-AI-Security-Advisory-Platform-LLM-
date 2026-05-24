import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Dev proxy — forward API calls to the advisory-api backend
    proxy: {
      '/health': 'http://localhost:8000',
      '/login': 'http://localhost:8000',
      '/analyze': 'http://localhost:8000',
      '/internal': 'http://localhost:8000',
      '/api': 'http://localhost:8000',
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    minify: true, // Vite 8: uses Oxc by default (no esbuild needed)
    // Chunk splitting for optimal caching
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/react') || id.includes('node_modules/react-dom') || id.includes('node_modules/react-router-dom')) {
            return 'vendor';
          }
          if (id.includes('node_modules/recharts')) {
            return 'charts';
          }
          if (id.includes('node_modules/@tanstack')) {
            return 'query';
          }
        },
      },
    },
  },
})
