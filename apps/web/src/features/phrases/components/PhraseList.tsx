"use client";

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";

import type { ListPhrasesParams, PhraseApiClient } from "@/lib/api/client";
import type { components } from "@/types/api";
import { copy } from "@/i18n/copy.es";

import { LIST_FILTER_DEBOUNCE_MS } from "../constants";
import { counterLabel } from "../counterLabel";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import { scoreLabel } from "../scoreLabel";
import { PhraseListFilters, type StatusFilterValue } from "./PhraseListFilters";
import styles from "./phrases.module.css";

type PhraseOut = components["schemas"]["_PhraseOut"];
type PhraseListData = components["schemas"]["_PhraseListData"];

export interface PhraseListHandle {
  /**
   * Browser-side `GET /phrases` refetch (design.md: "no `router.refresh()`,
   * no reload"). Never rejects — a failure only flips the list's own
   * non-blocking error state, so a caller (e.g. `PhraseWorkspace`'s
   * `onSaved`) never needs a `.catch()`. Always re-fetches page 1, discarding
   * any pages loaded via scroll — the same reset a fresh mount would see.
   */
  refresh: () => Promise<void>;
}

export interface PhraseListProps {
  /** Injection seam for tests, matching the rest of the phrase feature's "MSW rejected" convention. */
  client: Pick<PhraseApiClient, "listPhrases">;
  /**
   * `null` means the Server Component's own first-paint fetch
   * (`app/page.tsx`) failed — rendered as the exact same load-error state a
   * later refresh failure produces, with no separate loading flash on
   * mount (design.md: "no client-side loading flash on first load").
   * Otherwise the first page, exactly as `GET /phrases` returned it — this
   * component continues paging from its `next_cursor`, never re-requesting
   * page 1 on mount.
   */
  initialPage: PhraseListData | null;
}

type ListStatus = "idle" | "loading" | "error";

/**
 * The generated API type widens `validation.status` to plain `string` (no
 * literal union exists anywhere in this client to narrow it against), so an
 * unrecognized value cannot be caught at compile time. The backend's DB
 * CHECK constraint (Unit 4) makes only `unique` and `duplicate_confirmed`
 * possible today, but this stays a defensive runtime guard rather than
 * silently mapping every non-`duplicate_confirmed` value to "Única" —
 * matching `errorCopy.ts`'s "never silently swallow an unmapped value"
 * convention, minus a dedicated fallback copy key since exactly two
 * statuses are contractually possible.
 */
function badgeLabel(status: string): string {
  if (status === "duplicate_confirmed") {
    return copy.badge.duplicate_confirmed;
  }
  if (status !== "unique") {
    console.warn(
      `PhraseList: unrecognized validation status "${status}", rendering as "${copy.badge.unique}"`,
    );
  }
  return copy.badge.unique;
}

function badgeClassName(status: string): string {
  return status === "duplicate_confirmed" ? styles.badgeConfirmed : styles.badgeUnique;
}

/** Appends `incoming` after `existing`, skipping any id already present (same "no duplicate items" rule `DuplicateAlert`'s match list follows). */
function appendDeduped(existing: PhraseOut[], incoming: PhraseOut[]): PhraseOut[] {
  const seen = new Set(existing.map((item) => item.id));
  const appended = incoming.filter((item) => !seen.has(item.id));
  return appended.length === 0 ? existing : [...existing, ...appended];
}

/**
 * phrase-ui spec, "Saved phrase list with status badge": renders `GET
 * /phrases` (newest first, per the API) with a status badge per item, its
 * own `list.loadError` + Reintentar state, and infinite scroll over
 * whatever the store holds beyond the first page — same
 * IntersectionObserver-sentinel pattern as `DuplicateAlert`'s match list
 * (`useMatchesInfiniteScroll`), inlined here since this list has no
 * text/threshold session to reset, just a cursor to walk.
 */
export const PhraseList = forwardRef<PhraseListHandle, PhraseListProps>(
  function PhraseList({ client, initialPage }, ref) {
    const [items, setItems] = useState<PhraseOut[]>(initialPage?.items ?? []);
    const [total, setTotal] = useState(initialPage?.total ?? 0);
    const [cursor, setCursor] = useState<string | null>(initialPage?.next_cursor ?? null);
    const [hasMore, setHasMore] = useState(initialPage?.has_more ?? false);
    const [status, setStatus] = useState<ListStatus>(
      initialPage === null ? "error" : "idle",
    );
    const [isLoadingMore, setIsLoadingMore] = useState(false);
    const [loadMoreError, setLoadMoreError] = useState(false);

    // phrase-ui spec, "Filter controls over the saved list" / "Filtered
    // counter and empty state" — filter state lives here, in the container;
    // `PhraseListFilters` is purely presentational. `status`/`minScore`
    // refetch immediately on change; only `qDraft` is debounced.
    const [statusFilter, setStatusFilter] = useState<StatusFilterValue>("");
    const [qDraft, setQDraft] = useState("");
    const [minScore, setMinScore] = useState<number | null>(null);
    const debouncedQ = useDebouncedValue(qDraft, LIST_FILTER_DEBOUNCE_MS);
    // Clearing the text box applies at once; only non-blank typing waits for
    // the debounce (design.md: "clearing the text box applies immediately;
    // only typing waits").
    const appliedQ = qDraft.trim() === "" ? "" : debouncedQ;

    const applied: ListPhrasesParams = {
      ...(statusFilter !== "" ? { status: statusFilter } : {}),
      ...(appliedQ.trim() !== "" ? { q: appliedQ } : {}),
      ...(minScore !== null ? { minScore } : {}),
    };
    const appliedKey = JSON.stringify(applied);
    const hasActiveFilters = statusFilter !== "" || qDraft.trim() !== "" || minScore !== null;

    // Kept current on every render, not just at request time: `refresh()`
    // and `loadMore()` are called from callbacks (imperative handle,
    // IntersectionObserver) that must always read the CURRENTLY active
    // filters, never a value captured in a stale closure.
    const filtersRef = useRef(applied);
    filtersRef.current = applied;

    // Ref, not state: two intersection callbacks firing synchronously in the
    // same tick must not both pass the "already loading" guard before either
    // re-render could observe it (same reasoning as `useMatchesInfiniteScroll`).
    const inFlightMore = useRef(false);

    // Guards a `listPhrases()` response against overwriting state from a
    // NEWER request (design.md: "drops any response whose generation is
    // stale") — a filter change while an older request is still in flight
    // must never have its late response clobber the newer one's result.
    const generation = useRef(0);

    async function refresh() {
      const requestGeneration = ++generation.current;
      inFlightMore.current = false;
      setIsLoadingMore(false);
      setLoadMoreError(false);
      setStatus("loading");
      try {
        const page = await client.listPhrases(filtersRef.current);
        if (requestGeneration !== generation.current) return;
        setItems(page.items);
        setTotal(page.total);
        setCursor(page.next_cursor);
        setHasMore(page.has_more);
        setLoadMoreError(false);
        setStatus("idle");
      } catch {
        if (requestGeneration !== generation.current) return;
        // Loaded items remain untouched (phrase-ui spec, "Refresh fails
        // after a successful save": "loaded items remain") — only the
        // status flips, never the data.
        setStatus("error");
      }
    }

    useImperativeHandle(ref, () => ({ refresh }));

    // `appliedKey`'s initial value (no filters active) always stringifies to
    // the same key this ref starts with, so mount never fires a redundant
    // refetch of the SSR-provided `initialPage` — same "key compare, not a
    // first-run flag" approach design.md specifies (StrictMode-safe).
    const fetchedKey = useRef(appliedKey);

    useEffect(() => {
      if (fetchedKey.current === appliedKey) return;
      fetchedKey.current = appliedKey;
      void refresh();
      // eslint-disable-next-line react-hooks/exhaustive-deps -- refresh() always reads filtersRef.current/client via closure; appliedKey is the only value that should re-trigger it.
    }, [appliedKey]);

    function clearFilters() {
      setStatusFilter("");
      setQDraft("");
      setMinScore(null);
    }

    function loadMore() {
      if (inFlightMore.current || !hasMore || cursor === null) return;
      const requestGeneration = generation.current;
      inFlightMore.current = true;
      setIsLoadingMore(true);
      setLoadMoreError(false);
      client.listPhrases({ ...filtersRef.current, cursor }).then(
        (page) => {
          if (requestGeneration !== generation.current) return;
          inFlightMore.current = false;
          setIsLoadingMore(false);
          setItems((prev) => appendDeduped(prev, page.items));
          setTotal(page.total);
          setCursor(page.next_cursor);
          setHasMore(page.has_more);
        },
        () => {
          if (requestGeneration !== generation.current) return;
          inFlightMore.current = false;
          setIsLoadingMore(false);
          setLoadMoreError(true);
        },
      );
    }

    // Kept current on every render so the IntersectionObserver callback
    // (created once per sentinel node) always calls the latest closure
    // instead of one capturing a stale `cursor`/`hasMore`.
    const loadMoreRef = useRef(loadMore);
    loadMoreRef.current = loadMore;

    const [sentinelNode, setSentinelNode] = useState<Element | null>(null);

    useEffect(() => {
      if (!sentinelNode || typeof IntersectionObserver === "undefined") return;
      const observer = new IntersectionObserver((entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          loadMoreRef.current();
        }
      });
      observer.observe(sentinelNode);
      return () => observer.disconnect();
    }, [sentinelNode]);

    return (
      <section className={styles.listSection} aria-busy={status === "loading"}>
        {/* phrase-ui spec, "Filter controls over the saved list": the filter
            bar always renders — outside the items/error branches below. */}
        <PhraseListFilters
          status={statusFilter}
          onStatusChange={setStatusFilter}
          text={qDraft}
          onTextChange={setQDraft}
          minScore={minScore}
          onMinScoreChange={setMinScore}
        />

        {status === "error" && (
          <div className={styles.errorBox}>
            <p>{copy.list.loadError}</p>
            <button
              type="button"
              className={`${styles.button} ${styles.buttonGhost}`}
              onClick={() => void refresh()}
            >
              {copy.button.retry}
            </button>
          </div>
        )}

        {items.length === 0 ? (
          // Only render the empty state once the list is settled with zero
          // items — never while `loading` (a refresh/Reintentar in flight)
          // or `error`, both of which already have their own state above
          // (`aria-busy` / the load-error block). Previously this only
          // excluded `error`, so a Reintentar click briefly showed "Aún no
          // hay frases guardadas." while the refetch was still in flight.
          status === "idle" &&
          (hasActiveFilters ? (
            // phrase-ui spec, "Filtered counter and empty state": a distinct
            // message from the unfiltered empty state, with a one-click
            // action that clears every active filter and reloads page 1.
            <div className={styles.emptyStateFiltered}>
              <p className={styles.emptyState}>{copy.list.emptyFiltered}</p>
              <button
                type="button"
                className={`${styles.button} ${styles.buttonGhost}`}
                onClick={clearFilters}
              >
                {copy.button.clearFilters}
              </button>
            </div>
          ) : (
            <p className={styles.emptyState}>{copy.list.empty}</p>
          ))
        ) : (
          <>
            <p className={styles.listCounter}>{counterLabel(items.length, total)}</p>
            <ul className={styles.list}>
              {items.map((item) => (
                <li key={item.id} className={styles.listItem}>
                  <span className={styles.listItemText}>{item.text}</span>
                  <span className={styles.listItemMeta}>
                    {item.validation.score !== null && (
                      <span className={styles.score}>{scoreLabel(item.validation.score)}</span>
                    )}
                    <span className={`${styles.badge} ${badgeClassName(item.validation.status)}`}>
                      {badgeLabel(item.validation.status)}
                    </span>
                  </span>
                </li>
              ))}
            </ul>

            {hasMore && (
              <div
                ref={setSentinelNode}
                className={styles.sentinel}
                data-testid="phrase-list-sentinel"
                aria-hidden="true"
              />
            )}
            {isLoadingMore && <p className={styles.loadingMore}>{copy.list.loadingMore}</p>}
            {loadMoreError && (
              <div className={styles.errorBox}>
                <p>{copy.list.loadMoreError}</p>
                <button
                  type="button"
                  className={`${styles.button} ${styles.buttonGhost}`}
                  onClick={loadMore}
                >
                  {copy.button.retry}
                </button>
              </div>
            )}
          </>
        )}
      </section>
    );
  },
);
