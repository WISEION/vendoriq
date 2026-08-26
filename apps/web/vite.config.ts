import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// The web app never talks to a database or computes a score: every call goes to the API
// (brief §2). In dev, /api is proxied to the FastAPI process started by `make api`.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_URL ?? 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
