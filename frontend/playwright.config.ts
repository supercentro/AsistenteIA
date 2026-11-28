import { defineConfig, devices } from '@playwright/test'

const baseURL = process.env.E2E_BASE_URL ?? 'http://localhost:5173'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  reporter: [['list']],
  use: { baseURL, trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  // Reuses the docker compose frontend when it is already running; otherwise starts the dev server.
  webServer: {
    command: 'npm run dev',
    url: baseURL,
    reuseExistingServer: true,
    // The mocked suite stubs this origin with page.route; no backend is started.
    env: {
      VITE_API_URL: process.env.VITE_API_URL ?? 'http://localhost:8000/api/v1',
      // Only for this test server: the teacher activity page is hidden unless the flag is "true".
      VITE_TEACHER_ACTIVITY_ENABLED: 'true',
      VITE_TEACHER_TOPICS_ENABLED: 'true',
    },
  },
})
