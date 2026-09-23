"use client";

import { forwardRef, useImperativeHandle, useState } from "react";

import type { PhraseApiClient } from "@/lib/api/client";
import type { components } from "@/types/api";
import { copy } from "@/i18n/copy.es";

import { scoreLabel } from "../scoreLabel";
import styles from "./phrases.module.css";

type PhraseOut = components["schemas"]["_PhraseOut"];

export interface PhraseListHandle {
  /**
   * Browser-side `GET /phrases` refetch (design.md: "no `router.refresh()`,
   * no reload"). Never rejects — a failure only flips the list's own
   * non-blocking error state, so a caller (e.g. `PhraseWorkspace`'s
   * `onSaved`) never needs a `.catch()`.
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
   */
  initialItems: PhraseOut[] | null;
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

/**
 * phrase-ui spec, "Saved phrase list with status badge": renders `GET
 * /phrases` (newest first, per the API) with a status badge per item and
 * its own `list.loadError` + Reintentar state, entirely separate from
 * `PhraseForm`'s state machine — that separation is what guarantees a list
 * refresh failure after a save can never move the machine to `error` (the
 * phrase IS saved). `PhraseWorkspace` is what wires the two together
 * without letting either leak into the other.
 */
export const PhraseList = forwardRef<PhraseListHandle, PhraseListProps>(
  function PhraseList({ client, initialItems }, ref) {
    const [items, setItems] = useState<PhraseOut[]>(initialItems ?? []);
    const [status, setStatus] = useState<ListStatus>(
      initialItems === null ? "error" : "idle",
    );

    async function refresh() {
      setStatus("loading");
      try {
        const data = await client.listPhrases();
        setItems(data.items);
        setStatus("idle");
      } catch {
        // Loaded items remain untouched (phrase-ui spec, "Refresh fails
        // after a successful save": "loaded items remain") — only the
        // status flips, never the data.
        setStatus("error");
      }
    }

    useImperativeHandle(ref, () => ({ refresh }));

    return (
      <section className={styles.listSection} aria-busy={status === "loading"}>
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
          status === "idle" && <p className={styles.emptyState}>{copy.list.empty}</p>
        ) : (
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
        )}
      </section>
    );
  },
);
