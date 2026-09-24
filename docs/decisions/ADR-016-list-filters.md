---
id: ADR-016
title: Saved-phrase list filters, reversing the original out-of-scope call
type: beyond-brief
---

# ADR-016: Saved-phrase list filters, reversing the original out-of-scope call

**The brief asked for** a working validation flow; it never mentioned
filtering the saved-phrase list, and `phrase-management`'s "List phrases"
requirement went further and said explicitly that "search, filtering and
alternative sorting are out of scope."

**We decided** to add three optional, combinable query params to the
existing `GET /phrases` endpoint — `status` (`unique` or
`duplicate_confirmed`), `q` (case-insensitive substring match against
`normalized_text`, LIKE-wildcard-escaped, length-capped), and `min_score`
(float in `[0,1]`, NULL scores excluded) — instead of adding a new endpoint
or leaving filtering out. `total` reflects the active filter set, not the
whole table; the pagination cursor stays filter-agnostic, so the client
resends the same filter params on every page. A new partial index,
migration `0002`, serves the rare `status=duplicate_confirmed` case; the
common `status=unique` case keeps using the existing
`phrases_created_at_id_idx`.

**Because** once the list holds thousands of phrases, scrolling
newest-first cannot answer "which phrases did someone save despite the
duplicate warning?", "do we already have something about X?", or "what was
saved close to the threshold?" — the request came up in a live support
conversation, not from the original brief. This is additive UX in the same
spirit as ADR-005's staged progress labels: the precedent set there is that
deliberately going beyond the brief for a concrete, demonstrated user need
still counts as a `beyond-brief` decision, not a silent scope creep, so it
gets its own ADR and its own tests rather than being folded in quietly.

Accent-insensitive search stays out of scope — `q=cafe` does not match
"café", and that is a documented limitation, not a bug. A `pg_trgm`
trigram index for `q` is deferred: at 20,000 rows the measured filtered
query cost is 32 ms, well under a noticeable threshold, and adding the
extension now would slow every save for a index that does not even help
queries under three characters. Revisit `pg_trgm` if the list grows past
roughly 100k rows, or if filtered p95 latency exceeds 100 ms.
