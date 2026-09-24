"use client";

import { useEffect, useReducer, useRef, useState } from "react";

import { ApiError, type PhraseApiClient } from "@/lib/api/client";
import type { components } from "@/types/api";
import { copy } from "@/i18n/copy.es";
import { copyForErrorCode } from "@/i18n/errorCopy";

import { MATCHES_PAGE_SIZE } from "../constants";
import {
  initialState,
  phraseMachineReducer,
  type DuplicateDetails,
  type ErrorInfo,
  type MachineState,
} from "../machine";
import { scoreLabel } from "../scoreLabel";
import { DuplicateAlert } from "./DuplicateAlert";
import styles from "./phrases.module.css";

type ValidateData = components["schemas"]["_ValidateData"];
type PhraseOut = components["schemas"]["_PhraseOut"];

const DEFAULT_MAX_LENGTH = 280;

// Build-time inlined by Next.js (`NEXT_PUBLIC_*`), same pattern as
// `client.ts`'s `DEFAULT_BASE_URL`. Falls back to the phrase-ui spec's
// documented default (280, equal to the backend `PHRASE_MAX_LENGTH`) when
// unset or not a positive number.
const configuredMaxLength = Number(process.env.NEXT_PUBLIC_PHRASE_MAX_LENGTH);
const ENV_MAX_LENGTH =
  Number.isFinite(configuredMaxLength) && configuredMaxLength > 0
    ? configuredMaxLength
    : DEFAULT_MAX_LENGTH;

export interface PhraseFormProps {
  /** Injection seam for tests, matching `client.ts`'s own "MSW rejected" fake-client approach. */
  client: PhraseApiClient;
  /** Overridable for tests; defaults to `NEXT_PUBLIC_PHRASE_MAX_LENGTH` (build-time). */
  maxLength?: number;
  /** Fired after a successful 201 — the saved-list refresh (Unit 13) hooks in here. */
  onSaved?: (phrase: PhraseOut) => void;
}

/** Unicode code points of the trimmed text (phrase-ui spec: "not UTF-16 units, so an emoji counts once"). */
function codePointLength(value: string): number {
  return [...value.trim()].length;
}

/** Both a `validate` 200 (`is_duplicate: true`) and a save's 409 `details` are validate-shaped (duplicate-confirmation spec, "409 payload"). */
function toDuplicateDetails(data: {
  threshold: number;
  score: number | null;
  most_similar: ValidateData["most_similar"];
  matches: ValidateData["matches"];
  next_cursor: string | null;
  has_more: boolean;
  total: number;
}): DuplicateDetails {
  return {
    threshold: data.threshold,
    score: data.score,
    mostSimilar: data.most_similar,
    matches: data.matches,
    nextCursor: data.next_cursor,
    hasMore: data.has_more,
    total: data.total,
  };
}

// The 409 payload arrives as `ApiError.details` (`Record<string, unknown> |
// null | undefined` — the client has no way to type it further, same
// documented, unenforced-by-the-type-system invariant as `client.ts`'s
// `ErrorCode` cast). It is trusted to be validate-shaped per the
// duplicate-confirmation spec's "409 payload" requirement, not runtime
// validated here.
function detailsFromApiError(details: Record<string, unknown> | null | undefined): DuplicateDetails {
  const shaped = details as unknown as {
    threshold: number;
    score: number | null;
    most_similar: ValidateData["most_similar"];
    matches: ValidateData["matches"];
    next_cursor: string | null;
    has_more: boolean;
    total: number;
  };
  return toDuplicateDetails(shaped);
}

/** The code is looked up against `errorCopy` (i18n/errorCopy.ts) at render time — this only normalizes the shape. */
function toErrorInfo(err: unknown): ErrorInfo {
  if (err instanceof ApiError) {
    return { code: err.code, message: err.message };
  }
  return { code: "INTERNAL_ERROR", message: "Unexpected error" };
}

export function PhraseForm({ client, maxLength = ENV_MAX_LENGTH, onSaved }: PhraseFormProps) {
  const [text, setText] = useState("");
  const [state, dispatch] = useReducer(phraseMachineReducer, initialState);
  // Only holds the transient post-201 "Frase guardada." announcement — the
  // three staged progress labels are derived straight from `state.status`
  // below (`progressMessage`), never set imperatively, so a label can never
  // outlive the state it belongs to.
  const [announcement, setAnnouncement] = useState("");
  // Captured at the moment Validar/Guardar/Confirmar is pressed — the
  // input is disabled for the whole in-flight duration, so this always
  // matches what the request was actually sent for.
  const submittedText = useRef("");

  const trimmedLength = codePointLength(text);
  const isEmpty = trimmedLength === 0;
  const isOverLength = trimmedLength > maxLength;
  const busy =
    state.status === "validating" ||
    state.status === "revalidating" ||
    state.status === "saving";
  const canSubmit = !busy && !isEmpty && !isOverLength;

  const progressMessage =
    state.status === "validating"
      ? copy.progress.validating
      : state.status === "revalidating"
        ? copy.progress.revalidating
        : state.status === "saving"
          ? copy.progress.saving
          : null;
  const liveMessage = progressMessage ?? announcement;

  // Side effects keyed off `state.status`, not off the event that produced
  // it — "revalidating" always means "the authoritative POST /phrases is
  // in flight" regardless of whether it was reached from a blind save or
  // from `ok` (design.md: "Every label boundary is a real observable event
  // of a real request").
  useEffect(() => {
    let cancelled = false;

    if (state.status === "validating") {
      client.validatePhrase({ text: submittedText.current, limit: MATCHES_PAGE_SIZE }).then(
        (data) => {
          if (cancelled) return;
          if (data.is_duplicate) {
            dispatch({ type: "VALIDATE_OK_DUPLICATE", details: toDuplicateDetails(data) });
          } else {
            dispatch({ type: "VALIDATE_OK_UNIQUE", mostSimilar: data.most_similar ?? null });
          }
        },
        (err: unknown) => {
          if (cancelled) return;
          dispatch({ type: "FAIL", error: toErrorInfo(err) });
        },
      );
    } else if (state.status === "revalidating" || state.status === "saving") {
      client
        .savePhrase({
          text: submittedText.current,
          confirm_duplicate: state.status === "saving",
        })
        .then(
          (phrase) => {
            if (cancelled) return;
            setAnnouncement(copy.saved.success);
            setText("");
            dispatch({ type: "SAVE_OK" });
            onSaved?.(phrase);
          },
          (err: unknown) => {
            if (cancelled) return;
            if (err instanceof ApiError && err.code === "DUPLICATE_CONFIRMATION_REQUIRED") {
              dispatch({ type: "CONFLICT", details: detailsFromApiError(err.details) });
            } else {
              dispatch({ type: "FAIL", error: toErrorInfo(err) });
            }
          },
        );
    }

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- effect is keyed on `state.status` only, by design.
  }, [state.status]);

  function handleChange(event: React.ChangeEvent<HTMLTextAreaElement>) {
    setAnnouncement("");
    setText(event.target.value);
    dispatch({ type: "EDIT_TEXT" });
  }

  function handleValidate() {
    if (!canSubmit) return;
    submittedText.current = text.trim();
    dispatch({ type: "VALIDATE" });
  }

  function handleSave() {
    if (!canSubmit) return;
    submittedText.current = text.trim();
    dispatch({ type: "SAVE" });
  }

  function handleConfirm() {
    dispatch({ type: "CONFIRM" });
  }

  function handleCancel() {
    setAnnouncement("");
    dispatch({ type: "CANCEL" });
  }

  function handleRetry() {
    setAnnouncement("");
    dispatch({ type: "RETRY" });
  }

  function handleInvalidCursor() {
    dispatch({ type: "INVALID_CURSOR" });
  }

  const duplicateDetails = duplicateDetailsOf(state);

  return (
    <section className={styles.formCard}>
      <label className={styles.label} htmlFor="phrase-text">
        {copy.input.label}
      </label>
      <textarea
        id="phrase-text"
        className={styles.textarea}
        placeholder={copy.input.placeholder}
        value={text}
        onChange={handleChange}
        disabled={busy}
        aria-describedby="phrase-counter"
      />
      <div className={styles.metaRow}>
        <span
          id="phrase-counter"
          className={`${styles.counter} ${isOverLength ? styles.counterOver : ""}`}
        >
          {trimmedLength}/{maxLength}
        </span>
      </div>
      {isOverLength && <p className={styles.errorText}>{copy.error.tooLong}</p>}

      <div className={styles.actions}>
        <button
          type="button"
          className={`${styles.button} ${styles.buttonGhost}`}
          onClick={handleValidate}
          disabled={!canSubmit}
        >
          {copy.button.validate}
        </button>
        <button
          type="button"
          className={`${styles.button} ${styles.buttonPrimary}`}
          onClick={handleSave}
          disabled={!canSubmit}
        >
          {copy.button.save}
        </button>
      </div>

      {state.status === "ok" && (
        <>
          <p className={styles.okMessage}>{copy.validation.ok}</p>
          {state.mostSimilar && (
            <p className={styles.mostSimilar}>
              {copy.validation.closestMatch}: <strong>{state.mostSimilar.text}</strong>{" "}
              ({scoreLabel(state.mostSimilar.score)})
            </p>
          )}
        </>
      )}

      {duplicateDetails && (
        <DuplicateAlert
          client={client}
          text={submittedText.current}
          details={duplicateDetails}
          disabled={state.status === "saving"}
          onConfirm={handleConfirm}
          onCancel={handleCancel}
          onInvalidCursor={handleInvalidCursor}
        />
      )}

      {state.status === "error" && (
        <div className={styles.errorBox}>
          <p>{copyForErrorCode(state.error.code)}</p>
          <button
            type="button"
            className={`${styles.button} ${styles.buttonGhost}`}
            onClick={handleRetry}
          >
            {copy.button.retry}
          </button>
        </div>
      )}

      <p className={styles.liveRegion} role="status" aria-live="polite">
        {liveMessage}
      </p>
    </section>
  );
}

/** The duplicate section stays visible (dimmed via the `saving` disabled buttons) through Confirmar, not just while `duplicate`. */
function duplicateDetailsOf(state: MachineState): DuplicateDetails | null {
  if (state.status === "duplicate" || state.status === "saving") {
    return state.details;
  }
  return null;
}
