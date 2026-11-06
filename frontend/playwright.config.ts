import { defineConfig } from '@playwright/test';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const baseURL = 'http://127.0.0.1:18082';
const python = process.platform === 'win32' ? '.venv\\Scripts\\python.exe' : '.venv/bin/python';

export default defineConfig({
  testDir: './e2e',
  workers: 1,
  outputDir: '../.cache/qa/task6/playwright',
  use: {
    baseURL,
    channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome',
    acceptDownloads: false,
    trace: 'retain-on-failure',
  },
  webServer: {
    command: `"${python}" frontend/e2e/serve_study.py`,
    cwd: root,
    url: baseURL + '/api/health',
    timeout: 30000,
    reuseExistingServer: process.env.PLAYWRIGHT_REUSE_FIXTURE === '1',
    env: { PYTHONDONTWRITEBYTECODE: '1' },
  },
});
