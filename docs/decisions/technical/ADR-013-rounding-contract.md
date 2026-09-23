---
id: ADR-013
title: Rounding is the contract
type: technical
---

# ADR-013: Rounding is the contract

Scores are clamped to [0, 1] (a cosine can be negative) and then rounded to
4 decimals; that value decides the threshold (compared as `Decimal`, so
thresholds with more than 4 decimals are exact), populates every response
and is what gets stored. SQL filters on a bound widened by a full rounding
unit (`2.0` at `t = 0`) so it is a provable **superset**, and the
application applies the exact comparison, stopping at the first failing
row (the tail rule). Keyset ordering stays on raw distances, so rounding
never enters the cursor. Oracle equivalence against the domain cosine is
gated at **1e-5**, not 1e-6, because pgvector stores float32. Rejected:
rounding inside SQL, which would duplicate the rounding rule.
