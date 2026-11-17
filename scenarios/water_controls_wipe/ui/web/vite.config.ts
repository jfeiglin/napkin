// The page's build. In development (`npm run dev`, which the helper's `dev` starts), the requests to /api go to
// the engine's server at VIEW_API.
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': process.env.VIEW_API ?? 'http://127.0.0.1:8765' } },
  build: { outDir: 'dist', emptyOutDir: true },
});
