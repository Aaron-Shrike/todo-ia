---
id: ADR-005
title: Staged progress labels instead of one opaque spinner
type: beyond-brief
---

# ADR-005: Staged progress labels instead of one opaque spinner

**The brief asked for** a validation button before saving.

**We decided** a staged UX with three distinct labels — "Validando..." (the
validate request), "Revalidando..." (the authoritative save request, while
the server re-validates) and "Guardando..." (the confirming save from the
duplicate alert) — instead of one opaque spinner or a merged "Revalidando y
guardando...". Pressing Guardar without validating shows "Validando..."
then "Revalidando..."; from a validated state only "Revalidando...".

**Because** the server always re-validates, and the interface should tell
the truth about that work. Every label spans a request that is really in
flight; nothing is faked on a timer, and **no label is shown after the
201** — the machine returns to `idle`, clears the text, announces "Frase
guardada." and refreshes the list in the background (a failed refresh is a
non-blocking list error, never a save error). A 409 routes to the duplicate
alert from `revalidating` (or, defensively, `saving`) without
"Guardando..." ever narrating a save that did not happen.
