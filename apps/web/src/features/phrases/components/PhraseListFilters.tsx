"use client";

import type { ChangeEvent } from "react";

import { copy } from "@/i18n/copy.es";

import styles from "./phrases.module.css";

export type StatusFilterValue = "" | "unique" | "duplicate_confirmed";

const DEFAULT_MAX_LENGTH = 280;

// Same build-time-inlined pattern as `PhraseForm.tsx`'s own
// `ENV_MAX_LENGTH`: `q` is validated server-side against the same
// `PHRASE_MAX_LENGTH` a saved phrase's text is (design.md: "text input
// (maxLength = the phrase max)"). Not imported from `PhraseForm.tsx`
// because that constant isn't exported there — duplicating the small
// env-read keeps this component self-contained and independently testable.
const configuredMaxLength = Number(process.env.NEXT_PUBLIC_PHRASE_MAX_LENGTH);
const ENV_MAX_LENGTH =
  Number.isFinite(configuredMaxLength) && configuredMaxLength > 0
    ? configuredMaxLength
    : DEFAULT_MAX_LENGTH;

export interface PhraseListFiltersProps {
  status: StatusFilterValue;
  onStatusChange: (status: StatusFilterValue) => void;
  text: string;
  onTextChange: (text: string) => void;
  /** [0,1] fraction, matching `ListPhrasesParams.minScore`; `null` means the control is empty. */
  minScore: number | null;
  /** Fires with `percent / 100` (a [0,1] fraction), or `null` when cleared. */
  onMinScoreChange: (minScore: number | null) => void;
  /** Overridable for tests; defaults to `NEXT_PUBLIC_PHRASE_MAX_LENGTH` (build-time), same as `PhraseForm`. */
  maxLength?: number;
}

/** `floorPercent`'s display convention, inverted for a controlled input: an item showing "85%" passes a minimum of 85. */
function percentFromMinScore(minScore: number | null): number | "" {
  return minScore === null ? "" : Math.round(minScore * 100);
}

/**
 * phrase-ui spec, "Filter controls over the saved list": status is the most
 * prominent control (rendered first, per the confirmed UX decision), text
 * and a minimum-similarity percent input follow. Purely presentational —
 * `PhraseList.tsx` owns all filter state and decides debounce/refetch
 * timing; this component only reports raw input changes upward.
 */
export function PhraseListFilters({
  status,
  onStatusChange,
  text,
  onTextChange,
  minScore,
  onMinScoreChange,
  maxLength = ENV_MAX_LENGTH,
}: PhraseListFiltersProps) {
  function handleMinScoreChange(event: ChangeEvent<HTMLInputElement>) {
    const raw = event.target.value;
    if (raw === "") {
      onMinScoreChange(null);
      return;
    }
    const percent = Number(raw);
    if (!Number.isFinite(percent)) return;
    onMinScoreChange(percent / 100);
  }

  return (
    <div className={styles.filterBar}>
      <div className={styles.filterField}>
        <label className={styles.label} htmlFor="phrase-filter-status">
          {copy.filters.statusLabel}
        </label>
        <select
          id="phrase-filter-status"
          className={styles.filterSelect}
          value={status}
          onChange={(event) => onStatusChange(event.target.value as StatusFilterValue)}
        >
          <option value="">{copy.filters.statusAll}</option>
          <option value="unique">{copy.badge.unique}</option>
          <option value="duplicate_confirmed">{copy.badge.duplicate_confirmed}</option>
        </select>
      </div>

      <div className={styles.filterField}>
        <label className={styles.label} htmlFor="phrase-filter-text">
          {copy.filters.textLabel}
        </label>
        <input
          id="phrase-filter-text"
          type="text"
          className={styles.filterInput}
          value={text}
          maxLength={maxLength}
          placeholder={copy.filters.textPlaceholder}
          onChange={(event) => onTextChange(event.target.value)}
        />
      </div>

      <div className={styles.filterField}>
        <label className={styles.label} htmlFor="phrase-filter-min-score">
          {copy.filters.minScoreLabel}
        </label>
        <input
          id="phrase-filter-min-score"
          type="number"
          className={styles.filterInput}
          min={0}
          max={100}
          step={1}
          value={percentFromMinScore(minScore)}
          onChange={handleMinScoreChange}
        />
      </div>
    </div>
  );
}
