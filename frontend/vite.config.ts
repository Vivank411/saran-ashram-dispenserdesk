import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the API runs on :8000 (hospital). Set VITE_API_PROXY=http://localhost:8001 to use the cloud API.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.VITE_API_PROXY || "http://127.0.0.1:8000" } },
  },
  build: { outDir: "dist", sourcemap: false },
});
