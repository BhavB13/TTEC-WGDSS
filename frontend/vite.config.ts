import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react({ jsxRuntime: "automatic" })],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules/leaflet") || id.includes("node_modules/react-leaflet")) {
            return "map-vendor";
          }
          if (id.includes("node_modules/chart.js") || id.includes("node_modules/react-chartjs-2")) {
            return "chart-vendor";
          }
          if (id.includes("node_modules/react") || id.includes("node_modules/react-dom")) {
            return "react-vendor";
          }
          return undefined;
        },
      },
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
