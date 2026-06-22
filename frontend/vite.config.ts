import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      "/health": { target: "http://localhost:8000", changeOrigin: true },
      "/charts": { target: "http://localhost:8000", changeOrigin: true },
      "/reports": { target: "http://localhost:8000", changeOrigin: true },
      "/chat": { target: "http://localhost:8000", changeOrigin: true, ws: true },
    },
  },
});
