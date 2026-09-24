// design.md "Spanish copy ownership": maps every `ErrorCode` this client can
// see — the backend's own registry (`errors.ts`) plus the client-only
// `NETWORK_ERROR` — to a `copy.error.*` key. `Record<ErrorCode, CopyKey>`
// makes this exhaustive at COMPILE time: adding a new code to `errors.ts`
// without adding a row here is a TS error, not a silent runtime gap.
// `errorCopy.test.ts` also walks the union at runtime so a value that is a
// syntactically valid `CopyKey` but the wrong one (e.g. swapping
// `error.timeout` and `error.embeddingUnavailable`) is still caught against
// the phrase-ui spec's mapping table.
//
// `VALIDATION_ERROR`'s reason-conditioned mapping (`error.tooLong` /
// `error.empty` by `details.fields[0].reason`, design.md's mapping table) is
// deliberately NOT implemented here: Unit 13's own Covers line lists only
// "Model unavailable, Timeout, Network failure, Unknown code" for Error
// handling. It falls back to `error.generic` below, the same as the design
// table's own "else" case, until a later unit needs the reason split.
import type { ErrorCode } from "@/lib/api/errors";

import { copy } from "./copy.es";

/** Keys into `copy.error.*` — every mapping below must resolve to one of these. */
export type CopyKey = `error.${keyof typeof copy.error}`;

export const errorCopy: Record<ErrorCode, CopyKey> = {
  VALIDATION_ERROR: "error.generic",
  INVALID_CURSOR: "error.invalidCursor",
  NOT_FOUND: "error.generic",
  PHRASE_NOT_FOUND: "error.generic",
  METHOD_NOT_ALLOWED: "error.generic",
  DUPLICATE_CONFIRMATION_REQUIRED: "error.generic",
  PAYLOAD_TOO_LARGE: "error.generic",
  INTERNAL_ERROR: "error.generic",
  EMBEDDING_UNAVAILABLE: "error.embeddingUnavailable",
  EMBEDDING_TIMEOUT: "error.timeout",
  NOT_READY: "error.embeddingUnavailable",
  NETWORK_ERROR: "error.network",
};

function resolveCopyKey(key: CopyKey): string {
  const [, subKey] = key.split(".") as [string, keyof typeof copy.error];
  return copy.error[subKey];
}

/**
 * The Spanish message for a given error code. Accepts a plain `string`, not
 * `ErrorCode`, because a real `ApiError.code` is only assumed — never
 * runtime-checked (see `client.ts`) — to be a member of the union: an
 * unmapped/unknown code falls back to `error.generic` (phrase-ui spec,
 * "Unknown code").
 */
export function copyForErrorCode(code: string): string {
  const key = (errorCopy as Record<string, CopyKey>)[code];
  return key ? resolveCopyKey(key) : copy.error.generic;
}
