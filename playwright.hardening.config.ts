import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  testMatch: 'import-lifecycle.spec.ts',
  workers: 1,
  retries: 0,
  timeout: 30_000,
  use: {
    baseURL: 'http://127.0.0.1:18765',
    channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
    trace: 'retain-on-failure',
  },
  webServer: {
    command: `${process.env.DEMO_PYTHON || '.venv-local/bin/python'} scripts/local_import_demo.py`,
    url: 'http://127.0.0.1:18765/api/workspaces',
    reuseExistingServer: false,
    timeout: 30_000,
    gracefulShutdown: { signal: 'SIGTERM', timeout: 10_000 },
  },
});
