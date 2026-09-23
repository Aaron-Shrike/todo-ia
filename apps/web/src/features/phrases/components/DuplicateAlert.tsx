"use client";

import type { PhraseApiClient } from "@/lib/api/client";
import { copy } from "@/i18n/copy.es";

import type { DuplicateDetails } from "../machine";
import { floorPercent } from "../percent";
import { useMatchesInfiniteScroll } from "../hooks/useMatchesInfiniteScroll";

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

/** `copy.duplicate.score`'s `{percent}` template, filled in — the one interpolated copy string in this module. */
function scoreLabel(score: number): string {
  return copy.duplicate.score.replace("{percent}", String(floorPercent(score)));
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
  const { matches, hasMore, isLoadingMore, loadError, retry, sentinelRef } =
    useMatchesInfiniteScroll({
      client,
      text,
      initialMatches: details.matches,
      initialCursor: details.nextCursor,
      initialHasMore: details.hasMore,
      onInvalidCursor,
    });

  return (
    <div role="alertdialog" aria-labelledby="duplicate-alert-title">
      <h2 id="duplicate-alert-title">{copy.duplicate.title}</h2>

      {details.mostSimilar && (
        <p>
          {copy.duplicate.mostSimilar}: {details.mostSimilar.text}
          {details.score !== null && <> ({scoreLabel(details.score)})</>}
        </p>
      )}

      <h3>{copy.duplicate.matchesTitle}</h3>
      <ul>
        {matches.map((match) => (
          <li key={match.id}>
            {match.text} — {scoreLabel(match.score)}
          </li>
        ))}
      </ul>

      {hasMore && <div ref={sentinelRef} data-testid="matches-sentinel" />}
      {isLoadingMore && <p>{copy.duplicate.loadingMore}</p>}
      {loadError && (
        <div>
          <p>{copy.duplicate.loadMoreError}</p>
          <button type="button" onClick={retry}>
            {copy.button.retry}
          </button>
        </div>
      )}

      <div>
        <button type="button" onClick={onConfirm} disabled={disabled}>
          {copy.button.confirm}
        </button>
        <button type="button" onClick={onCancel} disabled={disabled}>
          {copy.button.cancel}
        </button>
      </div>
    </div>
  );
}
