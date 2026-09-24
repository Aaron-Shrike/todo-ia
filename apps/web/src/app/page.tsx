import { createApiClient } from "@/lib/api/client";
import { copy } from "@/i18n/copy.es";
import { PhraseWorkspace } from "@/features/phrases/components/PhraseWorkspace";
import { SiteFooter, SiteHeader } from "@/components/SiteChrome";
import type { components } from "@/types/api";

import styles from "./page.module.css";

type PhraseListData = components["schemas"]["_PhraseListData"];

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

async function fetchInitialPage(): Promise<PhraseListData | null> {
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
    // No `limit`/`cursor`: the server's own default page size applies, same
    // as any other first load — `PhraseList` continues paging from this
    // page's own `next_cursor` on scroll.
    return await client.listPhrases();
  } catch {
    // A first-paint fetch failure renders the exact same load-error state
    // `PhraseList` shows for a later refresh failure — no separate path,
    // and no client-side loading flash while this resolves (it runs on the
    // server before any HTML is sent).
    return null;
  }
}

export default async function HomePage() {
  const initialPage = await fetchInitialPage();

  return (
    <main className={styles.page}>
      <SiteHeader />
      <div className={styles.content}>
        <h1 className={styles.title}>{copy.title}</h1>
        <PhraseWorkspace initialPage={initialPage} />
      </div>
      <SiteFooter />
    </main>
  );
}
