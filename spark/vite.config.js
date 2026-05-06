import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
// K2 dev-server config. The bridge runs on 127.0.0.1:8765 (ADR-0003 §1).
// We do NOT proxy the bridge through Vite — the Spark app calls the bridge
// directly so the auth + CORS contract surfaces in dev exactly as in
// production.
export default defineConfig({
    plugins: [react()],
    server: {
        host: '127.0.0.1',
        port: 5173,
        strictPort: true,
    },
    build: {
        target: 'es2022',
        sourcemap: true,
    },
});
