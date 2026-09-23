// phrase-ui spec, "Spanish copy table" — "Scenario: Copy values": the copy
// module's exported values MUST equal the spec's table exactly. This is a
// full deep-equality comparison against the table transcribed verbatim
// (chosen over `toMatchSnapshot()` so a typo fails against the spec itself,
// not against a locally-accepted snapshot baseline).
import { describe, expect, it } from "vitest";

import { copy } from "./copy.es";

describe("copy (phrase-ui spec's copy table)", () => {
  it("matches the spec's copy table verbatim", () => {
    expect(copy).toEqual({
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
    });
  });
});
