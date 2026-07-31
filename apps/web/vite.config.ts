import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

// 개발 중에는 /api, /ws 를 FastAPI 로 프록시해서 동일 오리진처럼 쓴다.
// 컨테이너에서는 API_PROXY_TARGET=http://api:8000 으로 서비스 이름을 넘긴다.
const target = process.env.API_PROXY_TARGET ?? 'http://127.0.0.1:8000';
const wsTarget = target.replace(/^http/, 'ws');

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    port: Number(process.env.WEB_PORT ?? 5173),
    host: process.env.VITE_HOST ?? 'localhost',
    proxy: {
      '/api': { target, changeOrigin: true },
      '/ws': { target: wsTarget, ws: true },
    },
  },
});
