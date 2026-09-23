// Table-driven test over every (state x event) pair — phrase-ui spec
// "Explicit staged state machine": every state x event combination is
// exercised, `EDIT_TEXT` from every state resets to `idle`, and every
// transition not explicitly defined MUST be a no-op (the reducer returns
// the exact same state reference, never a new object).
import { describe, expect, it } from "vitest";

import {
  initialState,
  phraseMachineReducer,
  type DuplicateDetails,
  type ErrorInfo,
  type MachineEvent,
  type MachineState,
} from "./machine";

const SAMPLE_DETAILS: DuplicateDetails = {
  threshold: 0.8,
  score: 0.9312,
  mostSimilar: { id: "7", text: "Comprar leche", score: 0.9312 },
  matches: [{ id: "7", text: "Comprar leche", score: 0.9312 }],
  nextCursor: null,
  hasMore: false,
};

// Deliberately distinct from SAMPLE_DETAILS so a test asserting the
// *event's* payload was actually used (not some stale state.details) would
// fail if the reducer ever confused the two.
const FRESH_DETAILS: DuplicateDetails = {
  threshold: 0.8,
  score: 1,
  mostSimilar: { id: "9", text: "Ir a comprar leche", score: 1 },
  matches: [{ id: "9", text: "Ir a comprar leche", score: 1 }],
  nextCursor: "cursor-2",
  hasMore: true,
};

const SAMPLE_ERROR: ErrorInfo = {
  code: "EMBEDDING_UNAVAILABLE",
  message: "model down",
};

// One representative fixture per named status. `validating` uses
// intent "validate" as the table's representative row; the intent-driven
// branch (only VALIDATE_OK_UNIQUE cares) is covered separately below.
const STATES: Record<string, MachineState> = {
  idle: { status: "idle" },
  validating: { status: "validating", intent: "validate" },
  ok: { status: "ok" },
  duplicate: { status: "duplicate", details: SAMPLE_DETAILS },
  revalidating: { status: "revalidating" },
  saving: { status: "saving", details: SAMPLE_DETAILS },
  error: { status: "error", error: SAMPLE_ERROR },
};

const EVENTS: Record<string, MachineEvent> = {
  EDIT_TEXT: { type: "EDIT_TEXT" },
  VALIDATE: { type: "VALIDATE" },
  SAVE: { type: "SAVE" },
  VALIDATE_OK_UNIQUE: { type: "VALIDATE_OK_UNIQUE" },
  VALIDATE_OK_DUPLICATE: { type: "VALIDATE_OK_DUPLICATE", details: FRESH_DETAILS },
  SAVE_OK: { type: "SAVE_OK" },
  CONFLICT: { type: "CONFLICT", details: FRESH_DETAILS },
  FAIL: { type: "FAIL", error: SAMPLE_ERROR },
  CONFIRM: { type: "CONFIRM" },
  CANCEL: { type: "CANCEL" },
  RETRY: { type: "RETRY" },
};

const IGNORED = "IGNORED" as const;

// The full expectation table: EXPECTED[fromState][event] is either the
// resulting MachineState or the literal "IGNORED" for a no-op transition.
const EXPECTED: Record<string, Record<string, MachineState | typeof IGNORED>> = {
  idle: {
    EDIT_TEXT: { status: "idle" },
    VALIDATE: { status: "validating", intent: "validate" },
    SAVE: { status: "validating", intent: "save" },
    VALIDATE_OK_UNIQUE: IGNORED,
    VALIDATE_OK_DUPLICATE: IGNORED,
    SAVE_OK: IGNORED,
    CONFLICT: IGNORED,
    FAIL: IGNORED,
    CONFIRM: IGNORED,
    CANCEL: IGNORED,
    RETRY: IGNORED,
  },
  validating: {
    EDIT_TEXT: { status: "idle" },
    VALIDATE: IGNORED,
    SAVE: IGNORED,
    // Representative row: intent "validate" -> ok (see the intent-branching
    // describe block below for the intent "save" -> revalidating case).
    VALIDATE_OK_UNIQUE: { status: "ok" },
    VALIDATE_OK_DUPLICATE: { status: "duplicate", details: FRESH_DETAILS },
    SAVE_OK: IGNORED,
    CONFLICT: IGNORED,
    FAIL: { status: "error", error: SAMPLE_ERROR },
    CONFIRM: IGNORED,
    CANCEL: IGNORED,
    RETRY: IGNORED,
  },
  ok: {
    EDIT_TEXT: { status: "idle" },
    VALIDATE: IGNORED,
    SAVE: { status: "revalidating" },
    VALIDATE_OK_UNIQUE: IGNORED,
    VALIDATE_OK_DUPLICATE: IGNORED,
    SAVE_OK: IGNORED,
    CONFLICT: IGNORED,
    FAIL: IGNORED,
    CONFIRM: IGNORED,
    CANCEL: IGNORED,
    RETRY: IGNORED,
  },
  duplicate: {
    EDIT_TEXT: { status: "idle" },
    VALIDATE: IGNORED,
    SAVE: IGNORED,
    VALIDATE_OK_UNIQUE: IGNORED,
    VALIDATE_OK_DUPLICATE: IGNORED,
    SAVE_OK: IGNORED,
    CONFLICT: IGNORED,
    FAIL: IGNORED,
    CONFIRM: { status: "saving", details: SAMPLE_DETAILS },
    CANCEL: { status: "idle" },
    RETRY: IGNORED,
  },
  revalidating: {
    EDIT_TEXT: { status: "idle" },
    VALIDATE: IGNORED,
    SAVE: IGNORED,
    VALIDATE_OK_UNIQUE: IGNORED,
    VALIDATE_OK_DUPLICATE: IGNORED,
    SAVE_OK: { status: "idle" },
    CONFLICT: { status: "duplicate", details: FRESH_DETAILS },
    FAIL: { status: "error", error: SAMPLE_ERROR },
    CONFIRM: IGNORED,
    CANCEL: IGNORED,
    RETRY: IGNORED,
  },
  saving: {
    EDIT_TEXT: { status: "idle" },
    VALIDATE: IGNORED,
    SAVE: IGNORED,
    VALIDATE_OK_UNIQUE: IGNORED,
    VALIDATE_OK_DUPLICATE: IGNORED,
    SAVE_OK: { status: "idle" },
    CONFLICT: { status: "duplicate", details: FRESH_DETAILS },
    FAIL: { status: "error", error: SAMPLE_ERROR },
    CONFIRM: IGNORED,
    CANCEL: IGNORED,
    RETRY: IGNORED,
  },
  error: {
    EDIT_TEXT: { status: "idle" },
    // Pressing Validar/Guardar again after an error retries directly
    // (design.md's state table: "error | VALIDATE/SAVE/EDIT_TEXT | idle").
    VALIDATE: { status: "validating", intent: "validate" },
    SAVE: { status: "validating", intent: "save" },
    VALIDATE_OK_UNIQUE: IGNORED,
    VALIDATE_OK_DUPLICATE: IGNORED,
    SAVE_OK: IGNORED,
    CONFLICT: IGNORED,
    FAIL: IGNORED,
    CONFIRM: IGNORED,
    CANCEL: IGNORED,
    // "Reintentar" — phrase-ui spec's "Retry" scenario: returns to idle,
    // text preserved (text lives outside the machine; see PhraseForm).
    RETRY: { status: "idle" },
  },
};

describe("phraseMachineReducer", () => {
  for (const [stateName, state] of Object.entries(STATES)) {
    describe(`from ${stateName}`, () => {
      for (const [eventName, event] of Object.entries(EVENTS)) {
        const expected = EXPECTED[stateName][eventName];
        const label =
          expected === IGNORED ? "ignored (no-op)" : `-> ${expected.status}`;

        it(`${eventName} ${label}`, () => {
          const result = phraseMachineReducer(state, event);
          if (expected === IGNORED) {
            // Referential equality proves no new object was allocated and
            // no request-triggering effect could have run off this event.
            expect(result).toBe(state);
          } else {
            expect(result).toEqual(expected);
          }
        });
      }
    });
  }

  describe("intent branching on VALIDATE_OK_UNIQUE (triangulation)", () => {
    it("Validar-only intent lands on ok, not revalidating", () => {
      const state: MachineState = { status: "validating", intent: "validate" };
      expect(phraseMachineReducer(state, { type: "VALIDATE_OK_UNIQUE" })).toEqual(
        { status: "ok" },
      );
    });

    it("blind-save intent skips ok and goes straight to revalidating", () => {
      const state: MachineState = { status: "validating", intent: "save" };
      expect(phraseMachineReducer(state, { type: "VALIDATE_OK_UNIQUE" })).toEqual(
        { status: "revalidating" },
      );
    });
  });

  it("never introduces a state after the 201 — SAVE_OK always lands on idle", () => {
    expect(
      phraseMachineReducer({ status: "revalidating" }, { type: "SAVE_OK" }),
    ).toEqual({ status: "idle" });
    expect(
      phraseMachineReducer(
        { status: "saving", details: SAMPLE_DETAILS },
        { type: "SAVE_OK" },
      ),
    ).toEqual({ status: "idle" });
  });

  it("exposes a plain idle initialState", () => {
    expect(initialState).toEqual({ status: "idle" });
  });
});
