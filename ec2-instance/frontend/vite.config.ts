import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

export default defineConfig(({ mode }) => {
  const root = fileURLToPath(new URL(".", import.meta.url));
  const env = loadEnv(mode, root, "");
  const port = Number(env.DEV_PORT || 5173);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error("DEV_PORT must be a valid port.");
  }
  return {
    root,
    plugins: [react()],
    server: {
      port,
      strictPort: true,
      proxy: {
        "/api": { target: env.DEV_API_PROXY_TARGET || "http://127.0.0.1:3000" },
      },
    },
  };
});
