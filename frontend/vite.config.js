import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // So the frontend can call /api/... during dev without CORS pain.
      // Adjust the target if your FastAPI backend runs elsewhere.
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        ws: true, // required so the WebSocket stream endpoint proxies correctly too
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
