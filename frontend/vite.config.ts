// Конфигурация Vite: React-плагин + прокси API к гейтвею на 8080
// (в dev-режиме фронт на 5173, запросы /api идут на гейтвей без CORS-проблем).
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8080',
    },
  },
});