// design.md "Spanish copy ownership": `errorCopy` MUST be exhaustive over
// the generated `ErrorCode` union (incl. `INVALID_CURSOR`) and every code's
// mapping must match the design table; an unmapped/unknown code falls back
// to `error.generic` (phrase-ui spec, "Unknown code").
import { describe, expect, it } from "vitest";

import type { ErrorCode } from "@/lib/api/errors";

import { copy } from "./copy.es";
import { copyForErrorCode, errorCopy } from "./errorCopy";

// Hand-kept in sync with `ErrorCode` (errors.ts) — same convention as that
// file's own "hand-maintained... not derived" comment. A code added there
// without a row here fails the exhaustiveness assertion below.
const ALL_ERROR_CODES: ErrorCode[] = [
  "INVALID_CURSOR",
  "NOT_FOUND",
  "PHRASE_NOT_FOUND",
  "METHOD_NOT_ALLOWED",
  "DUPLICATE_CONFIRMATION_REQUIRED",
  "PAYLOAD_TOO_LARGE",
  "VALIDATION_ERROR",
  "INTERNAL_ERROR",
  "EMBEDDING_UNAVAILABLE",
  "EMBEDDING_TIMEOUT",
  "NOT_READY",
  "NETWORK_ERROR",
];

describe("errorCopy", () => {
  it("is exhaustive over the full ErrorCode union", () => {
    expect(Object.keys(errorCopy).sort()).toEqual([...ALL_ERROR_CODES].sort());
  });

  it("maps every code to a defined, non-empty Spanish string", () => {
    for (const code of ALL_ERROR_CODES) {
      expect(copyForErrorCode(code)).toBeTruthy();
    }
  });

  it.each([
    ["EMBEDDING_UNAVAILABLE", copy.error.embeddingUnavailable],
    ["NOT_READY", copy.error.embeddingUnavailable],
    ["EMBEDDING_TIMEOUT", copy.error.timeout],
    ["NETWORK_ERROR", copy.error.network],
    ["INVALID_CURSOR", copy.error.invalidCursor],
  ])("%s maps to the spec's mapping table", (code, expected) => {
    expect(copyForErrorCode(code)).toBe(expected);
  });

  it("falls back to the generic message for an unmapped/unknown code", () => {
    expect(copyForErrorCode("SOME_FUTURE_CODE")).toBe(copy.error.generic);
  });
});
