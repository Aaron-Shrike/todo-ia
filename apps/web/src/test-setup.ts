// Registers @testing-library/jest-dom's matchers (`toBeInTheDocument`,
// `toHaveTextContent`, ...) on vitest's `expect`. Loaded via
// `vitest.config.ts`'s `test.setupFiles` for every test file.
import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// @testing-library/react's own auto-cleanup only self-registers when it
// detects a Jest-style global `afterEach` (`test.globals` is NOT enabled in
// vitest.config.ts, by choice — see client.test.ts's explicit `vi` imports
// convention). Without this, every component test after the first would
// see the previous test's DOM still mounted.
afterEach(() => {
  cleanup();
});
