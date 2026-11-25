import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './acceptance',
  outputDir: '../private/playwright-results',
  timeout: 120_000,
  workers: 1,
  use: {
    baseURL: 'https://localhost:8443',
    ignoreHTTPSErrors: true,
    channel: process.env.CRM_ACCEPTANCE_BROWSER || undefined,
    reducedMotion: 'reduce',
    actionTimeout: 10_000,
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
})
