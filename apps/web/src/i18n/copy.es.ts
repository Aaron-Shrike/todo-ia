// THE copy module (design.md: "Spanish copy ownership") — every
// user-visible string in the phrase UI MUST come from here, never a
// literal in a component (phrase-ui spec, "Single source of copy").
//
// Complete as of Unit 13: holds the phrase-ui spec's copy table verbatim
// (`copy.es.test.ts` compares every exported value against that table).
// Error rendering goes through `errorCopy.ts`'s exhaustive
// `Record<ErrorCode, CopyKey>` map, which reads its values from `error.*`
// below rather than duplicating them.
export const copy = {
  title: "Lista de frases",
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
    mostSimilar: "Frase más similar",
    score: "Similitud: {percent}%",
    matchesTitle: "Coincidencias",
    loadingMore: "Cargando más coincidencias...",
    loadMoreError: "No se pudieron cargar más coincidencias.",
  },
  badge: {
    unique: "Única",
    duplicate_confirmed: "Duplicado confirmado",
  },
  list: {
    empty: "Aún no hay frases guardadas.",
    loadError: "No se pudieron cargar las frases.",
  },
  saved: {
    success: "Frase guardada.",
  },
  error: {
    tooLong: "La frase no puede superar 280 caracteres.",
    empty: "Escribe una frase antes de continuar.",
    embeddingUnavailable:
      "El servicio de validación no está disponible. Inténtalo de nuevo.",
    timeout: "La validación tardó demasiado. Inténtalo de nuevo.",
    network: "No se pudo conectar con el servidor.",
    generic: "Ocurrió un error inesperado. Inténtalo de nuevo.",
    invalidCursor: "La lista de coincidencias cambió. Vuelve a validar.",
  },
} as const;

export type Copy = typeof copy;
