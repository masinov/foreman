import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backendUrl = process.env.FOREMAN_DASHBOARD_BACKEND_URL || "http://127.0.0.1:8080";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: backendUrl,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "../foreman/dashboard_frontend_dist",
    emptyOutDir: true,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./vitest.setup.js",
  },
});
