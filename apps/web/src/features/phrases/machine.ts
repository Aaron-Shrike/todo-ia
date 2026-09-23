// Pure reducer — no React, no `fetch`, 100% unit-testable (design.md's
// Frontend layout). Drives the phrase-ui spec's "Explicit staged state
// machine": states `idle | validating | ok | duplicate | revalidating |
// saving | error`. `PhraseForm` (Unit 11.2) owns the side effects (the
// actual API calls) keyed off `state.status`; this module only decides
// what the NEXT status is for a given event.

/** Shared shape of `most_similar` and each `matches[]` entry (api-contract's `_ScoredPhrase`). */
export interface ScoredPhrase {
  id: string;
  text: string;
  score: number;
}

/**
 * Everything the duplicate alert needs to render, normalized from either a
 * `validate` 200 (`is_duplicate: true`) or a `save` 409's `details` — both
 * are validate-shaped per the duplicate-confirmation spec's "409 payload".
 */
export interface DuplicateDetails {
  threshold: number;
  score: number | null;
  mostSimilar: ScoredPhrase | null;
  matches: ScoredPhrase[];
  nextCursor: string | null;
  hasMore: boolean;
}

export interface ErrorInfo {
  code: string;
  message: string;
}

/** Which button started the in-flight `validating` request — decides where VALIDATE_OK_UNIQUE goes. */
export type ValidateIntent = "validate" | "save";

export type MachineState =
  | { status: "idle" }
  | { status: "validating"; intent: ValidateIntent }
  | { status: "ok" }
  | { status: "duplicate"; details: DuplicateDetails }
  | { status: "revalidating" }
  | { status: "saving"; details: DuplicateDetails }
  | { status: "error"; error: ErrorInfo };

export type MachineEvent =
  | { type: "EDIT_TEXT" }
  | { type: "VALIDATE" }
  | { type: "SAVE" }
  | { type: "VALIDATE_OK_UNIQUE" }
  | { type: "VALIDATE_OK_DUPLICATE"; details: DuplicateDetails }
  | { type: "SAVE_OK" }
  | { type: "CONFLICT"; details: DuplicateDetails }
  | { type: "FAIL"; error: ErrorInfo }
  | { type: "CONFIRM" }
  | { type: "CANCEL" }
  | { type: "RETRY" }
  // A 400 INVALID_CURSOR on a `POST /phrases/matches` page request (phrase-ui
  // spec, "Invalid cursor restarts validation") — dispatched by
  // `useMatchesInfiniteScroll`'s `onInvalidCursor` callback via `DuplicateAlert`.
  | { type: "INVALID_CURSOR" };

export const initialState: MachineState = { status: "idle" };

/**
 * `idle` and `error` both start a fresh validate/save request the exact
 * same way (VALIDATE/SAVE -> `validating` carrying the pressed button's
 * intent) — one source of truth so that invariant can't drift between the
 * two cases.
 */
function startValidating(intent: ValidateIntent): MachineState {
  return { status: "validating", intent };
}

/**
 * `phraseMachineReducer` — one branch per (state, event) pair, mirroring
 * design.md's state table (not a literal lookup table). Any (state, event)
 * pair not handled below is an INVALID transition and MUST be a true no-op:
 * the exact same `state` reference is returned, never a new object — this
 * is also what proves, at the reducer level, that no request could ever be
 * triggered by an event the current state does not expect.
 */
export function phraseMachineReducer(
  state: MachineState,
  event: MachineEvent,
): MachineState {
  // "Reset on text edit" (phrase-ui spec): EDIT_TEXT resets to idle from
  // EVERY state, including in-flight ones — a stale response arriving
  // afterwards is discarded by the caller (PhraseForm), not by the machine.
  if (event.type === "EDIT_TEXT") {
    return { status: "idle" };
  }

  switch (state.status) {
    case "idle":
      if (event.type === "VALIDATE") {
        return startValidating("validate");
      }
      if (event.type === "SAVE") {
        return startValidating("save");
      }
      return state;

    case "validating":
      if (event.type === "VALIDATE_OK_UNIQUE") {
        // Blind save (Guardar from idle): the validate call was only the
        // first leg — proceed straight to the authoritative save call
        // ("Revalidando..."), never surfacing an intermediate "ok".
        return state.intent === "save"
          ? { status: "revalidating" }
          : { status: "ok" };
      }
      if (event.type === "VALIDATE_OK_DUPLICATE") {
        return { status: "duplicate", details: event.details };
      }
      if (event.type === "FAIL") {
        return { status: "error", error: event.error };
      }
      return state;

    case "ok":
      if (event.type === "SAVE") {
        // From `ok` the server still re-validates — one call, no
        // intermediate "Validando..." stage.
        return { status: "revalidating" };
      }
      return state;

    case "duplicate":
      if (event.type === "CONFIRM") {
        return { status: "saving", details: state.details };
      }
      if (event.type === "CANCEL") {
        return { status: "idle" };
      }
      if (event.type === "INVALID_CURSOR") {
        // Discards the loaded matches (they belonged to a now-invalid
        // cursor) and restarts the flow exactly like pressing Validar
        // again, rather than retrying the same cursor.
        return startValidating("validate");
      }
      return state;

    case "revalidating":
      if (event.type === "SAVE_OK") {
        // No state after the 201 — the list refresh is tracked separately
        // by the list component's own status, never by this machine.
        return { status: "idle" };
      }
      if (event.type === "CONFLICT") {
        return { status: "duplicate", details: event.details };
      }
      if (event.type === "FAIL") {
        return { status: "error", error: event.error };
      }
      return state;

    case "saving":
      if (event.type === "SAVE_OK") {
        return { status: "idle" };
      }
      if (event.type === "CONFLICT") {
        // Defensive: the server does not 409 a `confirm_duplicate: true`
        // save today, but the UI still handles it deterministically.
        return { status: "duplicate", details: event.details };
      }
      if (event.type === "FAIL") {
        return { status: "error", error: event.error };
      }
      return state;

    case "error":
      if (event.type === "RETRY") {
        return { status: "idle" };
      }
      // design.md's state table lists `error | VALIDATE/SAVE/EDIT_TEXT |
      // idle/retry` — ambiguous on its face. This implementation resolves
      // it as: pressing Validar/Guardar again from `error` re-validates or
      // re-saves DIRECTLY (skipping `idle`), while EDIT_TEXT/RETRY reset to
      // `idle` instead — matching the phrase-ui spec's canonical "Retry"
      // scenario (text preserved, Validar/Guardar re-run the flow).
      if (event.type === "VALIDATE") {
        return startValidating("validate");
      }
      if (event.type === "SAVE") {
        return startValidating("save");
      }
      return state;

    default:
      return state;
  }
}
