import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const backendUrl = process.env.YV_BACKEND_URL ?? "http://127.0.0.1:8100";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: { "/api": backendUrl },
  },
});
