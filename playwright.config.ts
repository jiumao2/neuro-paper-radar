import { defineConfig, devices } from '@playwright/test';
export default defineConfig({
  testDir:'./tests/browser',fullyParallel:true,retries:process.env.CI?1:0,
  reporter:[['list']],outputDir:'test-results',
  use:{baseURL:process.env.QA_BASE_URL||'http://127.0.0.1:4173/neuro-paper-radar/',
    screenshot:'only-on-failure',trace:'retain-on-failure',
    launchOptions:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE?{executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE}:{}},
  projects:[{name:'desktop',use:{...devices['Desktop Chrome']}},{name:'mobile',use:{...devices['iPhone 13'],defaultBrowserType:'chromium'}}],
  webServer:process.env.QA_BASE_URL?undefined:{command:'npm run dev -- --port 4173',url:'http://127.0.0.1:4173/neuro-paper-radar/',reuseExistingServer:!process.env.CI},
});
