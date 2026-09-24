import { describe, expect, it } from "vitest";

import { floorPercent } from "./percent";

// phrase-ui spec, "Percentage never overstates": 0.9950 and 0.9999 must both
// floor to 99%, never round up to 100%; only an exact 1.0 shows 100%.
describe("floorPercent", () => {
  it.each([
    [0.9312, 93],
    [0.995, 99],
    [0.9999, 99],
    [0.29, 29],
    [1.0, 100],
  ])("floors %s to %s%%", (score, expected) => {
    expect(floorPercent(score)).toBe(expected);
  });
});
