import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Fixed rather than "whatever's free" — the backend's CORS allowlist
    // and the Google OAuth Client ID's authorized origins are both pinned
    // to this exact port. strictPort fails fast instead of silently
    // drifting to 5175+ if something else is still holding 5174.
    port: 5174,
    strictPort: true,
  },
})
