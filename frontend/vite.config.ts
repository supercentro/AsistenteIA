/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Inside docker compose on Windows, bind-mounted files do not emit change events: poll instead.
const usePolling = process.env.CHOKIDAR_USEPOLLING === 'true'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    watch: usePolling ? { usePolling: true, interval: 300 } : undefined,
  },
  test: {
    environment: 'jsdom',
    // Same origin as the mocked API so jsdom does not run CORS preflights; CORS is verified against the real backend.
    environmentOptions: { jsdom: { url: 'http://localhost:8000/' } },
    globals: true,
    setupFiles: ['./src/tests/setup.ts'],
    env: { VITE_API_URL: 'http://localhost:8000/api/v1' },
    include: ['src/**/*.test.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      include: ['src/**'],
      exclude: [
        'src/tests/**',
        'src/types/api.generated.ts',
        'src/main.tsx',
        'src/**/*.test.{ts,tsx}',
      ],
      // Thresholds of docs/frontend-standards.md section 6 (components and hooks).
      thresholds: {
        'src/components/**': { lines: 70, statements: 70, functions: 70, branches: 70 },
        'src/hooks/**': { lines: 70, statements: 70, functions: 70, branches: 70 },
      },
    },
  },
})
