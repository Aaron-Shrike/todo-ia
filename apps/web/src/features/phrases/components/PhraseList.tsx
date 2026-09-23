"use client";

import { forwardRef, useImperativeHandle, useState } from "react";

import type { PhraseApiClient } from "@/lib/api/client";
import type { components } from "@/types/api";
import { copy } from "@/i18n/copy.es";

import { scoreLabel } from "../scoreLabel";

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

function badgeLabel(status: string): string {
  return status === "duplicate_confirmed"
    ? copy.badge.duplicate_confirmed
    : copy.badge.unique;
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
      <section aria-busy={status === "loading"}>
        {status === "error" && (
          <div>
            <p>{copy.list.loadError}</p>
            <button type="button" onClick={() => void refresh()}>
              {copy.button.retry}
            </button>
          </div>
        )}

        {items.length === 0 ? (
          status !== "error" && <p>{copy.list.empty}</p>
        ) : (
          <ul>
            {items.map((item) => (
              <li key={item.id}>
                {item.text} — {badgeLabel(item.validation.status)}
                {item.validation.score !== null && (
                  <> ({scoreLabel(item.validation.score)})</>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    );
  },
);
