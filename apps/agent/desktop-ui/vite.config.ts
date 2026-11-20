import { defineConfig } from 'vitest/config';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
  base: './',
  plugins: [vue()],
  build: { target: 'es2022' },
  test: { environment: 'jsdom', restoreMocks: true, include: ['tests/**/*.test.ts'] },
});
