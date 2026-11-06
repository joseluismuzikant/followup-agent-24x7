import { sentryVitePlugin } from "@sentry/vite-plugin";
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

  // Source maps exist only to go to Sentry (CI, with SENTRY_AUTH_TOKEN): uploaded for the
  // release, then deleted, so the served bundle has none. Without the token: no maps.
  const uploadSourceMaps = command === "build" && Boolean(process.env.SENTRY_AUTH_TOKEN);

  return {
    plugins: [
      react(),
      tailwindcss(),
      ...(uploadSourceMaps
        ? [
            sentryVitePlugin({
              org: process.env.SENTRY_ORG,
              project: process.env.SENTRY_PROJECT,
              authToken: process.env.SENTRY_AUTH_TOKEN,
              release: { name: env.VITE_RELEASE },
              sourcemaps: { filesToDeleteAfterUpload: ["./dist/**/*.map"] },
              telemetry: false,
            }),
          ]
        : []),
    ],
    build: {
      sourcemap: uploadSourceMaps ? "hidden" : false,
    },
    envDir,
    server: {
      port: 5176,
      strictPort: true,
    },
  };
});
