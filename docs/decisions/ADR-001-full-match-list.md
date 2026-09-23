---
id: ADR-001
title: Return the full match list, not just the top result
type: beyond-brief
---

# ADR-001: Return the full match list, not just the top result

**The brief asked for** the most similar phrase and its score.

**We decided** to also return `matches` — every phrase at or above the
threshold, score-ordered, cursor-paginated, with infinite scroll.
`most_similar` is still returned verbatim.

**Because** a single match hides how *crowded* the neighbourhood is; a user
deciding whether to confirm a duplicate deserves the full picture, and a
fixed top-N would be a silent truncation disguised as an answer.
