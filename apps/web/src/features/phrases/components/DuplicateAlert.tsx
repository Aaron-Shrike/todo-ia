"use client";

import type { PhraseApiClient } from "@/lib/api/client";
import { copy } from "@/i18n/copy.es";

import { matchesCounterLabel } from "../counterLabel";
import { useMatchesInfiniteScroll } from "../hooks/useMatchesInfiniteScroll";
import type { DuplicateDetails } from "../machine";
import { scoreLabel } from "../scoreLabel";
import styles from "./phrases.module.css";

export interface DuplicateAlertProps {
  client: Pick<PhraseApiClient, "listMatches">;
  /** The already-validated text the alert's matches belong to. */
  text: string;
  details: DuplicateDetails;
  /** True while `saving` (Confirmar in flight) — disables both actions. */
  disabled: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  onInvalidCursor: () => void;
}

/**
 * phrase-ui spec, "Duplicate alert" + "Infinite scroll over matches": the
 * 409/validate-shaped duplicate result, rendered as an `alertdialog` with
 * the most-similar phrase, the full (auto-paginating) match list, and the
 * Confirmar/Cancelar actions. Paging state lives in `useMatchesInfiniteScroll`;
 * this component only renders it and wires the three callback props.
 */
export function DuplicateAlert({
  client,
  text,
  details,
  disabled,
  onConfirm,
  onCancel,
  onInvalidCursor,
}: DuplicateAlertProps) {
  const { matches, total, hasMore, isLoadingMore, loadError, retry, sentinelRef, rootRef } =
    useMatchesInfiniteScroll({
      client,
      text,
      initialMatches: details.matches,
      initialCursor: details.nextCursor,
      initialHasMore: details.hasMore,
      initialTotal: details.total,
      disabled,
      onInvalidCursor,
    });

  return (
    <div className={styles.alert} role="alertdialog" aria-labelledby="duplicate-alert-title">
      <h2 id="duplicate-alert-title" className={styles.alertTitle}>
        {copy.duplicate.title}
      </h2>

      {details.mostSimilar && (
        <p className={styles.mostSimilar}>
          {copy.duplicate.mostSimilar}: <strong>{details.mostSimilar.text}</strong>
          {details.score !== null && <> ({scoreLabel(details.score)})</>}
        </p>
      )}

      <h3 className={styles.matchesTitle}>{copy.duplicate.matchesTitle}</h3>
      {matches.length > 0 && (
        <p className={styles.listCounter}>{matchesCounterLabel(matches.length, total)}</p>
      )}
      <ul className={styles.matchesList} ref={rootRef}>
        {matches.map((match) => (
          <li key={match.id} className={styles.matchItem}>
            <span>{match.text}</span>
            <span className={styles.matchScore}>{scoreLabel(match.score)}</span>
          </li>
        ))}
        {hasMore && (
          <li
            ref={sentinelRef}
            className={styles.sentinel}
            data-testid="matches-sentinel"
            aria-hidden="true"
          />
        )}
      </ul>

      {isLoadingMore && <p className={styles.loadingMore}>{copy.duplicate.loadingMore}</p>}
      {loadError && (
        <div className={styles.errorBox}>
          <p>{copy.duplicate.loadMoreError}</p>
          <button
            type="button"
            className={`${styles.button} ${styles.buttonGhost}`}
            onClick={retry}
          >
            {copy.button.retry}
          </button>
        </div>
      )}

      <div className={styles.alertActions}>
        <button
          type="button"
          className={`${styles.button} ${styles.buttonPrimary}`}
          onClick={onConfirm}
          disabled={disabled}
        >
          {copy.button.confirm}
        </button>
        <button
          type="button"
          className={`${styles.button} ${styles.buttonGhost}`}
          onClick={onCancel}
          disabled={disabled}
        >
          {copy.button.cancel}
        </button>
      </div>
    </div>
  );
}
