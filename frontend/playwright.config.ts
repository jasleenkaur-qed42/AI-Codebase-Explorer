import { defineConfig } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const venvPython = path.resolve(__dirname, '..', '.venv', 'bin', 'python3');

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  // All specs share one backend process (one repo, one in-memory session
  // EventBus) via the webServer below, so tests across files can't run
  // concurrently without leaking session/explain events between them.
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:5173',
  },
  webServer: [
    {
      command: `"${venvPython}" tests/fixtures/start_backend.py`,
      url: 'http://127.0.0.1:8420/api/repo/stats',
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
    {
      command: 'npm run dev -- --port 5173',
      url: 'http://localhost:5173',
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
  ],
});
