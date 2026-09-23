// THE copy module (design.md: "Spanish copy ownership") — every
// user-visible string in the phrase UI MUST come from here, never a
// literal in a component (phrase-ui spec, "Single source of copy").
//
// Unit 11 seeded the keys `PhraseForm` needs (form controls, the three
// staged progress labels, the `ok`/`saved` announcements, and the
// client-side over-length message); Unit 12 adds the `duplicate.*` keys
// `DuplicateAlert` needs (most-similar label, the `{percent}` score
// template, and the infinite-scroll loading/error copy). The REST of the
// phrase-ui spec's copy table (`badge.*`, `list.*`, the other `error.*`
// codes) is completed in Unit 13 (`copy.es.ts` task 13.1), which also adds
// the snapshot test asserting every value against the spec's table
// verbatim — this file's shape (nested objects mirroring the table's
// dotted keys) is chosen so Unit 13 only ADDS keys, never restructures.
export const copy = {
  input: {
    label: "Nueva frase",
    placeholder: "Escribe una frase",
  },
  button: {
    validate: "Validar",
    save: "Guardar",
    confirm: "Guardar de todos modos",
    cancel: "Cancelar",
    retry: "Reintentar",
  },
  progress: {
    validating: "Validando...",
    revalidating: "Revalidando...",
    saving: "Guardando...",
  },
  validation: {
    ok: "La frase es única. Puedes guardarla.",
  },
  duplicate: {
    title: "Posible duplicado",
    // Added in Unit 12 (DuplicateAlert's match list needs them); the
    // remaining `duplicate.*`/`badge.*`/`list.*`/`error.*` keys from the
    // phrase-ui copy table still land in Unit 13's snapshot-tested pass.
    mostSimilar: "Frase más similar",
    score: "Similitud: {percent}%",
    matchesTitle: "Coincidencias",
    loadingMore: "Cargando más coincidencias...",
    loadMoreError: "No se pudieron cargar más coincidencias.",
  },
  saved: {
    success: "Frase guardada.",
  },
  error: {
    tooLong: "La frase no puede superar 280 caracteres.",
    generic: "Ocurrió un error inesperado. Inténtalo de nuevo.",
  },
} as const;

export type Copy = typeof copy;
