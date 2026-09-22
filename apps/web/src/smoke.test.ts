// Smoke test proving the frontend test runner (vitest) is wired.
//
// This is intentionally the first RED of Unit 0 (scaffold monorepo): at the moment this file is
// written, `apps/web/package.json` and `apps/web/vitest.config.ts` do not exist yet, so `vitest`
// cannot even run. Task 0.3 makes it GREEN.
import { describe, expect, it } from "vitest";

describe("test runner smoke test", () => {
  it("executes and evaluates a real assertion", () => {
    expect(1 + 1).toBe(2);
  });
});
