import { defineConfig } from 'vitest/config';
export default defineConfig({
  base: '/neuro-paper-radar/',
  test: { include: ['src/**/*.test.ts'] },
  build: { target: 'es2022' },
});
