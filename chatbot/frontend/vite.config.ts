import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const demoApiTarget = process.env.DEMO_API_URL;

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api/chatbot": {
        target: demoApiTarget || "http://127.0.0.1:8015",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/chatbot/, ""),
      },
      "/api/orchestration": {
        target: demoApiTarget || "http://127.0.0.1:8002",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/orchestration/, ""),
      },
      "/api/upload-service": {
        target: demoApiTarget || "http://127.0.0.1:8011",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/upload-service/, ""),
      },
    },
  },
});
