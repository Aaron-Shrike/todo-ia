import { createApiClient } from "@/lib/api/client";
import { copy } from "@/i18n/copy.es";
import { PhraseWorkspace } from "@/features/phrases/components/PhraseWorkspace";
import type { components } from "@/types/api";

type PhraseOut = components["schemas"]["_PhraseOut"];

// Server-side-only (never bundled to the browser) — the Server-Component
// counterpart of the browser-facing `NEXT_PUBLIC_API_URL` `client.ts`'s
// singleton uses (design.md D5 / env table: "API_INTERNAL_URL ...
// server-side fetch (Server Components) only").
const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

// Opts this route out of Next's default static rendering. Without this AND
// the `cache: "no-store"` fetch below, Next would render the list once at
// build time (no API exists yet) and serve that empty snapshot forever
// (design.md "First paint and list refresh").
export const dynamic = "force-dynamic";

async function fetchInitialItems(): Promise<PhraseOut[] | null> {
  const client = createApiClient({
    baseUrl: API_INTERNAL_URL,
    // `client.ts`'s own `request()` never sets `cache` (it is also used
    // browser-side, where the option is meaningless) — injected here via
    // its existing `fetchImpl` seam so this Server Component call gets the
    // required `no-store` semantics without duplicating the envelope
    // parsing/error handling `client.ts` already has its own tests for.
    fetchImpl: (input, init) => fetch(input, { ...init, cache: "no-store" }),
  });
  try {
    const { items } = await client.listPhrases();
    return items;
  } catch {
    // A first-paint fetch failure renders the exact same load-error state
    // `PhraseList` shows for a later refresh failure — no separate path,
    // and no client-side loading flash while this resolves (it runs on the
    // server before any HTML is sent).
    return null;
  }
}

export default async function HomePage() {
  const initialItems = await fetchInitialItems();

  return (
    <main>
      <h1>{copy.title}</h1>
      <PhraseWorkspace initialItems={initialItems} />
    </main>
  );
}
