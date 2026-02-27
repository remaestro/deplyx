import { defineConfig, devices } from '@playwright/test'

/**
 * Deplyx end-to-end test configuration.
 *
 * Assumes the full stack is running locally:
 *   - Frontend  → http://localhost:5173
 *   - Backend   → http://localhost:8000
 *   - Lab API   → http://localhost:8001
 *   - Neo4j     → bolt://localhost:7687
 *   - Redis     → localhost:6379
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,          // tests are sequential (they share state)
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [['html', { open: 'never' }]],
  timeout: 120_000,              // generous – LLM analysis can be slow
  expect: { timeout: 30_000 },

  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 15_000,
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
