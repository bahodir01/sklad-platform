import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Ф-7 (архитектура §6): dev-прокси вместо кросс-оригинного VITE_API_URL.
// refresh-cookie имеет path=/api/v1/auth, Secure, SameSite=lax — прокси делает
// dev тем же одним origin, что и prod за nginx, и снимает вопросы SameSite/Secure.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
