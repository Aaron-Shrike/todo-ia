"use client";

import { useEffect, useRef, useState } from "react";

import { ApiError, type PhraseApiClient } from "@/lib/api/client";

import type { ScoredPhrase } from "../machine";

export interface UseMatchesInfiniteScrollParams {
  client: Pick<PhraseApiClient, "listMatches">;
  /** The validated text the current page(s) belong to — a new value resets all paging state. */
  text: string;
  initialMatches: ScoredPhrase[];
  initialCursor: string | null;
  initialHasMore: boolean;
  /**
   * Fired once on a 400 `INVALID_CURSOR` page failure (phrase-ui spec,
   * "Invalid cursor restarts validation"). This hook only discards its own
   * state and reports the event; re-running validation is the caller's job
   * (`PhraseForm` dispatches `INVALID_CURSOR` on the machine).
   */
  onInvalidCursor: () => void;
}

export interface UseMatchesInfiniteScrollResult {
  matches: ScoredPhrase[];
  hasMore: boolean;
  isLoadingMore: boolean;
  loadError: boolean;
  /** Re-requests the same cursor after a page load failure. */
  retry: () => void;
  /** Attach to the sentinel element rendered at the end of the match list (omit the element entirely when `hasMore` is false). */
  sentinelRef: (node: Element | null) => void;
}

/** Appends `incoming` after `existing`, in order, skipping any id already present ("Deduplicate on overlap"). */
function appendDeduped(existing: ScoredPhrase[], incoming: ScoredPhrase[]): ScoredPhrase[] {
  const seen = new Set(existing.map((match) => match.id));
  const appended = incoming.filter((match) => !seen.has(match.id));
  return appended.length === 0 ? existing : [...existing, ...appended];
}

export function useMatchesInfiniteScroll({
  client,
  text,
  initialMatches,
  initialCursor,
  initialHasMore,
  onInvalidCursor,
}: UseMatchesInfiniteScrollParams): UseMatchesInfiniteScrollResult {
  const [matches, setMatches] = useState(initialMatches);
  const [cursor, setCursor] = useState(initialCursor);
  const [hasMore, setHasMore] = useState(initialHasMore);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [loadError, setLoadError] = useState(false);

  // A ref, not state: "No concurrent page requests" must hold even for two
  // intersection callbacks fired synchronously in the same tick, before any
  // re-render could observe a state update.
  const inFlight = useRef(false);

  // A new duplicate result for a new (or re-validated) text replaces ALL
  // local paging state — never merged with a previous text's matches.
  useEffect(() => {
    setMatches(initialMatches);
    setCursor(initialCursor);
    setHasMore(initialHasMore);
    setLoadError(false);
    inFlight.current = false;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- keyed on `text` only, by design: a fresh duplicate result for the SAME text is not expected mid-alert.
  }, [text]);

  function loadNextPage() {
    if (inFlight.current || !hasMore || cursor === null) return;
    inFlight.current = true;
    setIsLoadingMore(true);
    setLoadError(false);
    client.listMatches({ text, cursor }).then(
      (page) => {
        inFlight.current = false;
        setIsLoadingMore(false);
        setMatches((prev) => appendDeduped(prev, page.matches));
        setCursor(page.next_cursor);
        setHasMore(page.has_more);
      },
      (err: unknown) => {
        inFlight.current = false;
        setIsLoadingMore(false);
        if (err instanceof ApiError && err.code === "INVALID_CURSOR") {
          setMatches([]);
          setCursor(null);
          setHasMore(false);
          onInvalidCursor();
          return;
        }
        setLoadError(true);
      },
    );
  }

  // Kept current on every render so the IntersectionObserver callback
  // (created once per sentinel node, not per render) always calls the
  // latest closure instead of a stale one capturing an old `cursor`/`hasMore`.
  const loadNextPageRef = useRef(loadNextPage);
  loadNextPageRef.current = loadNextPage;

  const [sentinelNode, setSentinelNode] = useState<Element | null>(null);

  useEffect(() => {
    if (!sentinelNode || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        loadNextPageRef.current();
      }
    });
    observer.observe(sentinelNode);
    return () => observer.disconnect();
  }, [sentinelNode]);

  return {
    matches,
    hasMore,
    isLoadingMore,
    loadError,
    retry: loadNextPage,
    sentinelRef: setSentinelNode,
  };
}
