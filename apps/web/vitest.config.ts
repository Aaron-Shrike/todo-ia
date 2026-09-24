import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    // Mirrors tsconfig.json's `paths: { "@/*": ["./src/*"] }` — Vite/vitest
    // do not read tsconfig `paths` on their own (no `vite-tsconfig-paths`
    // plugin installed; this one alias is simpler than adding a dependency
    // for it, per this project's own "MSW rejected: extra dep for no gain
    // at this size" precedent).
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    // jsdom (not "node") from Unit 11 onward: the first stateful UI
    // component (`PhraseForm.tsx`) needs `document`/`window` for
    // @testing-library/react. jsdom is a superset of what the existing
    // node-environment tests (`client.test.ts`, `smoke.test.ts`) need, so
    // this is a safe global switch rather than a per-file split.
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
});
