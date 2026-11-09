import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
    // Above the 5 s findBy*/waitFor limit of src/test-setup.ts.
    testTimeout: 15_000,
  },
});
