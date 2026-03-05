/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { existsSync, readFileSync } from 'fs'
import { resolve } from 'path'

const versionPath = resolve(__dirname, '../VERSION')
const versionPathAlt = resolve(__dirname, 'VERSION')
const version = readFileSync(existsSync(versionPath) ? versionPath : versionPathAlt, 'utf-8').trim()
const buildNumber = process.env.BUILD_NUMBER ?? 'dev'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(version),
    __BUILD_NUMBER__: JSON.stringify(buildNumber),
  },
  base: '/static/',
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/setupTests.ts',
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '')
      }
    }
  }
})
