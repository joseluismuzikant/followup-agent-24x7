import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

const envDir = "../../..";

export default defineConfig(({ command, mode }) => {
  // A production bundle with the development sign-in must never be built.
  const env = { ...loadEnv(mode, envDir, "VITE_"), ...process.env };
  if (command === "build" && mode === "production" && env.VITE_AUTH_MODE?.trim() === "dev") {
    throw new Error("VITE_AUTH_MODE=dev cannot be used in a production build.");
  }

  return {
    plugins: [react(), tailwindcss()],
    envDir,
    server: {
      port: 5173,
      strictPort: true,
    },
  };
});
