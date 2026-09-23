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
   * True while the machine is `saving` (Confirmar in flight, mirrors
   * `DuplicateAlert`'s own `disabled` prop). `duplicate.saving.INVALID_CURSOR`
   * is IGNORED by `phraseMachineReducer` (`machine.test.ts`), so a page
   * failure resolving as `INVALID_CURSOR` while this is true must not clear
   * `matches` or call `onInvalidCursor` — that would silently empty the
   * visible list under a save the machine is not going to restart.
   */
  disabled: boolean;
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
  disabled,
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

  // Guards `loadNextPage`'s async handlers against updating state that no
  // longer belongs to the current session (resilience: "stale-response race
  // with no unmount guard" — same `cancelled`-flag idea as PhraseForm.tsx's
  // own effect, adapted for a session that can change WITHOUT an unmount).
  //
  // Two separate refs, because a plain boolean is not enough: `text`/
  // `initialMatches` changing on a still-mounted instance runs the reset
  // effect's cleanup immediately followed by its own new setup in the same
  // commit, which would silently flip a single "cancelled" boolean back to
  // `false` before a still-pending stale request ever resolves.
  //
  // - `sessionId` is bumped every time the reset effect (re-)runs (mount AND
  //   every `text`/`initialMatches` change). `loadNextPage` captures the
  //   session it was sent under; the handler compares against the CURRENT
  //   session at resolution time.
  // - `unmounted` is set once, only by the true-unmount-only cleanup below,
  //   and never reset — it has no "new setup" to be undone by.
  const sessionId = useRef(0);
  const unmounted = useRef(false);

  useEffect(() => {
    // Reset on every setup, not just declare-and-forget: StrictMode's dev
    // double-invoke runs setup -> cleanup -> setup again on every mount, so
    // the second setup here is what undoes the synthetic cleanup's
    // `unmounted.current = true` and leaves the ref correctly `false` for
    // the component's real (StrictMode-remounted) lifetime. Without this
    // line the ref is permanently stuck `true` after the very first
    // StrictMode cycle, even though the component is genuinely mounted.
    unmounted.current = false;
    return () => {
      unmounted.current = true;
    };
  }, []);

  // Kept current on every render (not just at request time): a page request
  // can be sent while `disabled` is false and resolve after it flips true
  // (Confirmar pressed mid-flight) — the async handler must see the value
  // AT RESOLUTION TIME, not the one captured in its closure at call time.
  const disabledRef = useRef(disabled);
  disabledRef.current = disabled;

  // A new duplicate result for a new (or re-validated) text replaces ALL
  // local paging state. Depends on `initialMatches`'s identity (not just
  // `text`): a fresh duplicate result for the SAME text DOES happen (a 409
  // while confirming — `saving`/`CONFLICT` in machine.ts) and carries a new
  // `matches` array every time a real API response is parsed, while the
  // `saving` transition itself reuses the same `details` (and therefore the
  // same `matches` reference) unchanged — so this does not fire mid-confirm.
  // `initialCursor`/`initialHasMore` are intentionally left out: their VALUE
  // can coincidentally repeat (e.g. both `null`) across two different
  // results and would miss a reset that `initialMatches`'s identity always
  // catches.
  useEffect(() => {
    sessionId.current += 1;
    setMatches(initialMatches);
    setCursor(initialCursor);
    setHasMore(initialHasMore);
    setLoadError(false);
    inFlight.current = false;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- see comment above; onInvalidCursor is a stable callback prop, not session state to reset on.
  }, [text, initialMatches]);

  function loadNextPage() {
    if (inFlight.current || !hasMore || cursor === null) return;
    const requestSession = sessionId.current;
    inFlight.current = true;
    setIsLoadingMore(true);
    setLoadError(false);
    client.listMatches({ text, cursor }).then(
      (page) => {
        inFlight.current = false;
        if (unmounted.current || sessionId.current !== requestSession) return;
        setIsLoadingMore(false);
        setMatches((prev) => appendDeduped(prev, page.matches));
        setCursor(page.next_cursor);
        setHasMore(page.has_more);
      },
      (err: unknown) => {
        inFlight.current = false;
        if (unmounted.current || sessionId.current !== requestSession) return;
        setIsLoadingMore(false);
        if (err instanceof ApiError && err.code === "INVALID_CURSOR") {
          if (disabledRef.current) {
            // `duplicate.saving.INVALID_CURSOR` is IGNORED by the machine
            // (machine.test.ts) — restarting validation or wiping the list
            // here would contradict that and leave an unexplained empty
            // list under a save still in flight. Surface the existing
            // page-load-failure UI instead.
            setLoadError(true);
            return;
          }
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
