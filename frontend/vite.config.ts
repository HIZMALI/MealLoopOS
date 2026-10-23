import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { proxy: { "/api": "http://127.0.0.1:8080" } },
  preview: { proxy: { "/api": "http://127.0.0.1:8080" } },
  build: {
    rollupOptions: {
      output: {
        manualChunks: (id) =>
          /recharts|d3-|victory-vendor/.test(id) ? "charts" : undefined,
      },
    },
  },
});
