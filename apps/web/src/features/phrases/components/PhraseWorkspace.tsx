"use client";

import { useRef } from "react";

import { apiClient, type PhraseApiClient } from "@/lib/api/client";
import type { components } from "@/types/api";

import { PhraseForm } from "./PhraseForm";
import { PhraseList, type PhraseListHandle } from "./PhraseList";

type PhraseOut = components["schemas"]["_PhraseOut"];

export interface PhraseWorkspaceProps {
  /** Server-computed first paint (`app/page.tsx`) — `null` if that fetch failed. */
  initialItems: PhraseOut[] | null;
  /** Injection seam for tests; defaults to the browser-facing singleton (D5). */
  client?: PhraseApiClient;
}

/**
 * The one client boundary tying `PhraseForm`'s save flow to `PhraseList`'s
 * own state (design.md "First paint and list refresh": "the list refresh
 * runs in the background... a failed refetch is a non-blocking list error,
 * never a save error"). Not a file design.md's own directory sketch names
 * explicitly — added because `app/page.tsx` is a Server Component and
 * cannot itself hold the client state needed to connect the two;
 * `onSaved`'s return value is deliberately ignored (`PhraseListHandle.refresh`
 * never rejects), which is what keeps a refresh failure from ever touching
 * `PhraseForm`'s machine.
 */
export function PhraseWorkspace({ initialItems, client = apiClient }: PhraseWorkspaceProps) {
  const listRef = useRef<PhraseListHandle>(null);

  return (
    <>
      <PhraseForm client={client} onSaved={() => void listRef.current?.refresh()} />
      <PhraseList ref={listRef} client={client} initialItems={initialItems} />
    </>
  );
}
