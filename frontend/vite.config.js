import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'
import { readFileSync } from 'fs'

const { version } = JSON.parse(readFileSync('./package.json', 'utf-8'))

export default defineConfig(({ command }) => ({
  define: {
    __APP_VERSION__: JSON.stringify(version),
    // npm run dev (serve) always goes through this file's own proxy below,
    // same-origin — overrides whatever VITE_API_URL is set to in .env.dev.
    // npm run build:dev keeps the absolute dev-api.edgevest.in URL from .env.dev.
    ...(command === 'serve' ? { 'import.meta.env.VITE_API_URL': JSON.stringify('/api') } : {}),
  },
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.ico', 'icons/*.png'],
      manifest: {
        name: 'EdgeVest',
        short_name: 'EdgeVest',
        description: 'Advisory-first market intelligence',
        theme_color: '#0f172a',
        background_color: '#0f172a',
        display: 'standalone',
        orientation: 'portrait',
        start_url: '/',
        icons: [
          { src: 'icons/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
          { src: 'icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
          { src: 'icons/icon-512-maskable.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg}'],
        runtimeCaching: [
          {
            // Function form so this matches regardless of origin — VITE_API_URL
            // is an absolute cross-origin URL in every real build (only the
            // npm run dev proxy path is same-origin), so a path-only regex
            // never matched a real deployed build before this fix.
            urlPattern: ({ url }) => url.pathname.startsWith('/api/'),
            handler: 'NetworkFirst',
            options: { cacheName: 'api-cache', networkTimeoutSeconds: 5 },
          },
        ],
      },
    }),
  ],
  server: {
    port: 5173,
    host: true,   // bind to LAN too, not just localhost — lets a phone on the same Wi-Fi reach npm run dev
    proxy: {
      '/api': { target: 'http://localhost:5555', changeOrigin: true },
      '/auth': { target: 'http://localhost:5555', changeOrigin: true },
      '/logout': { target: 'http://localhost:5555', changeOrigin: true },
    },
  },
}))
