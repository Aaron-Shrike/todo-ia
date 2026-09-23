---
id: ADR-004
title: Next.js with TypeScript, not React or Vue directly
type: beyond-brief
---

# ADR-004: Next.js with TypeScript, not React or Vue directly

**The brief asked for** React or Vue.

**We decided** Next.js with TypeScript.

**Because** the saved-phrase list gets a real server-rendered first paint
(no spinner) via a Server Component (`force-dynamic` / `no-store`, so it is
never a stale build-time snapshot), while validation stays a client-side
state machine — we use Next for something, not as decoration. Cost:
`NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_PHRASE_MAX_LENGTH` are baked at
build time.
