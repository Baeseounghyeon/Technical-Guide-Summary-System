import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  server: {
    port: 5173,
    // 백엔드를 다른 포트로 띄웠다면 API_PROXY_TARGET=http://localhost:8001 처럼 지정한다.
    proxy: { "/api": loadEnv(mode, ".", "API_").API_PROXY_TARGET ?? "http://localhost:8000" },
  },
}));
