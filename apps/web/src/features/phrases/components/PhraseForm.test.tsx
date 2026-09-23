// Component tests on a hand-rolled, deferred-promise fake `PhraseApiClient`
// (design.md: "MSW rejected") — each test controls exactly when the
// validate/save call resolves so the staged progress label can be asserted
// WHILE the request is genuinely in flight (design.md's "staged-progress
// honesty rule", ADR-005).
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApiError, type PhraseApiClient } from "@/lib/api/client";
import type { components } from "@/types/api";
import { copy } from "@/i18n/copy.es";

import { PhraseForm } from "./PhraseForm";

type ValidateData = components["schemas"]["_ValidateData"];
type PhraseOut = components["schemas"]["_PhraseOut"];

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function createFakeClient(overrides: Partial<PhraseApiClient> = {}): PhraseApiClient {
  return {
    validatePhrase: vi.fn(),
    listMatches: vi.fn(),
    savePhrase: vi.fn(),
    listPhrases: vi.fn(),
    ...overrides,
  };
}

const UNIQUE_RESULT: ValidateData = {
  threshold: 0.8,
  is_duplicate: false,
  score: 0.12,
  most_similar: null,
  matches: [],
  next_cursor: null,
  has_more: false,
  total: 0,
};

const DUPLICATE_RESULT: ValidateData = {
  threshold: 0.8,
  is_duplicate: true,
  score: 0.9312,
  most_similar: { id: "7", text: "Comprar leche", score: 0.9312 },
  matches: [{ id: "7", text: "Comprar leche", score: 0.9312 }],
  next_cursor: null,
  has_more: false,
  total: 1,
};

function fakePhrase(status: "unique" | "duplicate_confirmed" = "unique"): PhraseOut {
  return {
    id: "1",
    text: "Comprar leche",
    created_at: "2026-01-01T00:00:00Z",
    validation: {
      status,
      score: status === "unique" ? 0.12 : 0.9312,
      most_similar_phrase_id: status === "unique" ? null : "7",
      validated_at: "2026-01-01T00:00:00Z",
    },
  };
}

function typeText(text: string) {
  fireEvent.change(screen.getByLabelText(copy.input.label), {
    target: { value: text },
  });
}

describe("PhraseForm", () => {
  it("renders the live region with role=status and aria-live=polite", () => {
    render(<PhraseForm client={createFakeClient()} />);
    const region = screen.getByRole("status");
    expect(region).toHaveAttribute("aria-live", "polite");
  });

  describe("progress label order", () => {
    it("blind save (unique): Validando -> Revalidando -> no label after the 201", async () => {
      const validateDeferred = createDeferred<ValidateData>();
      const saveDeferred = createDeferred<PhraseOut>();
      const client = createFakeClient({
        validatePhrase: vi.fn(() => validateDeferred.promise),
        savePhrase: vi.fn(() => saveDeferred.promise),
      });
      render(<PhraseForm client={client} />);
      const region = screen.getByRole("status");

      typeText("Regar plantas");
      fireEvent.click(screen.getByRole("button", { name: copy.button.save }));

      await waitFor(() => expect(region).toHaveTextContent(copy.progress.validating));
      expect(region).not.toHaveTextContent(copy.progress.revalidating);
      expect(region).not.toHaveTextContent(copy.progress.saving);

      await act(async () => {
        validateDeferred.resolve(UNIQUE_RESULT);
      });

      await waitFor(() => expect(region).toHaveTextContent(copy.progress.revalidating));
      expect(region).not.toHaveTextContent(copy.progress.saving);
      expect(client.savePhrase).toHaveBeenCalledWith({
        text: "Regar plantas",
        confirm_duplicate: false,
      });

      await act(async () => {
        saveDeferred.resolve(fakePhrase());
      });

      await waitFor(() =>
        expect(region).not.toHaveTextContent(copy.progress.revalidating),
      );
      expect(region).not.toHaveTextContent(copy.progress.validating);
      expect(region).not.toHaveTextContent(copy.progress.saving);
      expect(region).toHaveTextContent(copy.saved.success);
    });

    it("save from ok: only Revalidando is shown (no repeated Validando)", async () => {
      const validateDeferred = createDeferred<ValidateData>();
      const saveDeferred = createDeferred<PhraseOut>();
      const client = createFakeClient({
        validatePhrase: vi.fn(() => validateDeferred.promise),
        savePhrase: vi.fn(() => saveDeferred.promise),
      });
      render(<PhraseForm client={client} />);
      const region = screen.getByRole("status");

      typeText("Regar plantas");
      fireEvent.click(screen.getByRole("button", { name: copy.button.validate }));
      await waitFor(() => expect(region).toHaveTextContent(copy.progress.validating));

      await act(async () => {
        validateDeferred.resolve(UNIQUE_RESULT);
      });
      await waitFor(() =>
        expect(screen.getByText(copy.validation.ok)).toBeInTheDocument(),
      );
      expect(region).not.toHaveTextContent(copy.progress.validating);

      fireEvent.click(screen.getByRole("button", { name: copy.button.save }));

      await waitFor(() => expect(region).toHaveTextContent(copy.progress.revalidating));
      expect(region).not.toHaveTextContent(copy.progress.saving);
      expect(client.validatePhrase).toHaveBeenCalledTimes(1);

      await act(async () => {
        saveDeferred.resolve(fakePhrase());
      });
      await waitFor(() =>
        expect(region).not.toHaveTextContent(copy.progress.revalidating),
      );
    });

    it("confirm from duplicate: only Guardando is shown", async () => {
      const validateDeferred = createDeferred<ValidateData>();
      const saveDeferred = createDeferred<PhraseOut>();
      const client = createFakeClient({
        validatePhrase: vi.fn(() => validateDeferred.promise),
        savePhrase: vi.fn(() => saveDeferred.promise),
      });
      render(<PhraseForm client={client} />);
      const region = screen.getByRole("status");

      typeText("Comprar leche");
      fireEvent.click(screen.getByRole("button", { name: copy.button.validate }));
      await waitFor(() => expect(region).toHaveTextContent(copy.progress.validating));

      await act(async () => {
        validateDeferred.resolve(DUPLICATE_RESULT);
      });
      await waitFor(() =>
        expect(screen.getByText(copy.duplicate.title)).toBeInTheDocument(),
      );
      expect(region).not.toHaveTextContent(copy.progress.validating);

      fireEvent.click(screen.getByRole("button", { name: copy.button.confirm }));

      await waitFor(() => expect(region).toHaveTextContent(copy.progress.saving));
      expect(region).not.toHaveTextContent(copy.progress.validating);
      expect(region).not.toHaveTextContent(copy.progress.revalidating);
      expect(client.savePhrase).toHaveBeenCalledWith({
        text: "Comprar leche",
        confirm_duplicate: true,
      });

      await act(async () => {
        saveDeferred.resolve(fakePhrase("duplicate_confirmed"));
      });
      await waitFor(() => expect(region).not.toHaveTextContent(copy.progress.saving));
    });

    it("409 during revalidating never renders Guardando", async () => {
      const validateDeferred = createDeferred<ValidateData>();
      const saveDeferred = createDeferred<PhraseOut>();
      const client = createFakeClient({
        validatePhrase: vi.fn(() => validateDeferred.promise),
        savePhrase: vi.fn(() => saveDeferred.promise),
      });
      render(<PhraseForm client={client} />);
      const region = screen.getByRole("status");

      typeText("Comprar leche");
      fireEvent.click(screen.getByRole("button", { name: copy.button.save }));
      await waitFor(() => expect(region).toHaveTextContent(copy.progress.validating));

      await act(async () => {
        validateDeferred.resolve(UNIQUE_RESULT);
      });
      await waitFor(() => expect(region).toHaveTextContent(copy.progress.revalidating));
      expect(region).not.toHaveTextContent(copy.progress.saving);

      await act(async () => {
        saveDeferred.reject(
          new ApiError({
            code: "DUPLICATE_CONFIRMATION_REQUIRED",
            status: 409,
            message: "duplicate requires confirmation",
            details: {
              threshold: 0.8,
              score: 0.9312,
              most_similar: { id: "7", text: "Comprar leche", score: 0.9312 },
              matches: [{ id: "7", text: "Comprar leche", score: 0.9312 }],
              next_cursor: null,
              has_more: false,
            },
          }),
        );
      });

      await waitFor(() =>
        expect(screen.getByText(copy.duplicate.title)).toBeInTheDocument(),
      );
      expect(region).not.toHaveTextContent(copy.progress.saving);
      expect(region).not.toHaveTextContent(copy.progress.revalidating);
      expect(region).not.toHaveTextContent(copy.progress.validating);
    });

    it("409 while confirming (defensive): a 409 from Confirmar returns to duplicate populated from the fresh details", async () => {
      const validateDeferred = createDeferred<ValidateData>();
      const saveDeferred = createDeferred<PhraseOut>();
      const client = createFakeClient({
        validatePhrase: vi.fn(() => validateDeferred.promise),
        savePhrase: vi.fn(() => saveDeferred.promise),
      });
      render(<PhraseForm client={client} />);

      typeText("Comprar leche");
      fireEvent.click(screen.getByRole("button", { name: copy.button.validate }));
      await act(async () => {
        validateDeferred.resolve(DUPLICATE_RESULT);
      });
      await waitFor(() =>
        expect(screen.getByText(copy.duplicate.title)).toBeInTheDocument(),
      );

      fireEvent.click(screen.getByRole("button", { name: copy.button.confirm }));
      await waitFor(() =>
        expect(screen.getByRole("status")).toHaveTextContent(copy.progress.saving),
      );

      await act(async () => {
        saveDeferred.reject(
          new ApiError({
            code: "DUPLICATE_CONFIRMATION_REQUIRED",
            status: 409,
            message: "duplicate requires confirmation",
            details: {
              threshold: 0.8,
              score: 1,
              most_similar: { id: "8", text: "Comprar leche fresca", score: 1 },
              matches: [{ id: "8", text: "Comprar leche fresca", score: 1 }],
              next_cursor: null,
              has_more: false,
            },
          }),
        );
      });

      await waitFor(() =>
        expect(screen.getByRole("alertdialog")).toHaveTextContent(
          "Comprar leche fresca",
        ),
      );
      expect(
        screen.getByRole("button", { name: copy.button.confirm }),
      ).not.toBeDisabled();

      // The paginated match list itself (not just the "most similar" summary
      // line) must resync to the fresh 409 details — a stale pre-confirm
      // list here means `useMatchesInfiniteScroll` did not reset.
      const listItems = screen.getAllByRole("listitem");
      expect(listItems).toHaveLength(1);
      expect(listItems[0]).toHaveTextContent("Comprar leche fresca");
    });
  });

  describe("duplicate alert: Cancelar", () => {
    it("cancelling the duplicate alert sends no save request, closes the alert, keeps the text, and returns to idle", async () => {
      const validateDeferred = createDeferred<ValidateData>();
      const client = createFakeClient({
        validatePhrase: vi.fn(() => validateDeferred.promise),
      });
      render(<PhraseForm client={client} />);

      typeText("Comprar leche");
      fireEvent.click(screen.getByRole("button", { name: copy.button.validate }));
      await act(async () => {
        validateDeferred.resolve(DUPLICATE_RESULT);
      });
      await waitFor(() =>
        expect(screen.getByText(copy.duplicate.title)).toBeInTheDocument(),
      );

      fireEvent.click(screen.getByRole("button", { name: copy.button.cancel }));

      expect(client.savePhrase).not.toHaveBeenCalled();
      expect(screen.queryByText(copy.duplicate.title)).not.toBeInTheDocument();
      expect(screen.getByLabelText(copy.input.label)).toHaveValue("Comprar leche");
      expect(
        screen.getByRole("button", { name: copy.button.validate }),
      ).not.toBeDisabled();
      expect(
        screen.getByRole("button", { name: copy.button.save }),
      ).not.toBeDisabled();
    });
  });

  describe("reset on text edit", () => {
    it("clears the ok confirmation when the text is edited afterwards", async () => {
      const validateDeferred = createDeferred<ValidateData>();
      const client = createFakeClient({
        validatePhrase: vi.fn(() => validateDeferred.promise),
      });
      render(<PhraseForm client={client} />);

      typeText("Comprar leche");
      fireEvent.click(screen.getByRole("button", { name: copy.button.validate }));
      await act(async () => {
        validateDeferred.resolve(UNIQUE_RESULT);
      });
      await waitFor(() =>
        expect(screen.getByText(copy.validation.ok)).toBeInTheDocument(),
      );

      typeText("Comprar leche y pan");
      expect(screen.queryByText(copy.validation.ok)).not.toBeInTheDocument();
    });

    it("discards a stale validate response that arrives after an edit (Edit while validating)", async () => {
      const validateDeferred = createDeferred<ValidateData>();
      const client = createFakeClient({
        validatePhrase: vi.fn(() => validateDeferred.promise),
      });
      render(<PhraseForm client={client} />);
      const region = screen.getByRole("status");

      typeText("Comprar leche");
      fireEvent.click(screen.getByRole("button", { name: copy.button.validate }));
      await waitFor(() => expect(region).toHaveTextContent(copy.progress.validating));

      typeText("Comprar leche fresca");
      expect(region).not.toHaveTextContent(copy.progress.validating);

      await act(async () => {
        validateDeferred.resolve(DUPLICATE_RESULT);
      });

      expect(screen.queryByText(copy.duplicate.title)).not.toBeInTheDocument();
      expect(screen.queryByText(copy.validation.ok)).not.toBeInTheDocument();
      expect(region).not.toHaveTextContent(copy.progress.validating);
      expect(region).not.toHaveTextContent(copy.progress.revalidating);
      expect(region).not.toHaveTextContent(copy.progress.saving);
      expect(screen.getByLabelText(copy.input.label)).toHaveValue("Comprar leche fresca");
    });

    it("closes the duplicate section when the text is edited during duplicate", async () => {
      const validateDeferred = createDeferred<ValidateData>();
      const client = createFakeClient({
        validatePhrase: vi.fn(() => validateDeferred.promise),
      });
      render(<PhraseForm client={client} />);

      typeText("Comprar leche");
      fireEvent.click(screen.getByRole("button", { name: copy.button.validate }));
      await act(async () => {
        validateDeferred.resolve(DUPLICATE_RESULT);
      });
      await waitFor(() =>
        expect(screen.getByText(copy.duplicate.title)).toBeInTheDocument(),
      );

      typeText("Comprar leche fresca");
      expect(screen.queryByText(copy.duplicate.title)).not.toBeInTheDocument();
    });
  });

  describe("controls disabled in flight", () => {
    it("disables the input and buttons while validating and ignores a second click", async () => {
      const validateDeferred = createDeferred<ValidateData>();
      const client = createFakeClient({
        validatePhrase: vi.fn(() => validateDeferred.promise),
      });
      render(<PhraseForm client={client} />);

      typeText("Comprar leche");
      const validateButton = screen.getByRole("button", { name: copy.button.validate });
      fireEvent.click(validateButton);

      await waitFor(() => expect(validateButton).toBeDisabled());
      expect(screen.getByLabelText(copy.input.label)).toBeDisabled();
      expect(screen.getByRole("button", { name: copy.button.save })).toBeDisabled();

      fireEvent.click(validateButton);
      expect(client.validatePhrase).toHaveBeenCalledTimes(1);

      await act(async () => {
        validateDeferred.resolve(UNIQUE_RESULT);
      });
    });

    it("disables the alert's Confirmar and Cancelar while saving, and re-enables them once the save settles", async () => {
      const validateDeferred = createDeferred<ValidateData>();
      const saveDeferred = createDeferred<PhraseOut>();
      const client = createFakeClient({
        validatePhrase: vi.fn(() => validateDeferred.promise),
        savePhrase: vi.fn(() => saveDeferred.promise),
      });
      render(<PhraseForm client={client} />);

      typeText("Comprar leche");
      fireEvent.click(screen.getByRole("button", { name: copy.button.validate }));
      await act(async () => {
        validateDeferred.resolve(DUPLICATE_RESULT);
      });
      await waitFor(() =>
        expect(screen.getByText(copy.duplicate.title)).toBeInTheDocument(),
      );

      const confirmButton = screen.getByRole("button", { name: copy.button.confirm });
      const cancelButton = screen.getByRole("button", { name: copy.button.cancel });
      expect(confirmButton).not.toBeDisabled();
      expect(cancelButton).not.toBeDisabled();

      fireEvent.click(confirmButton);

      await waitFor(() => expect(confirmButton).toBeDisabled());
      expect(cancelButton).toBeDisabled();

      await act(async () => {
        saveDeferred.resolve(fakePhrase("duplicate_confirmed"));
      });
    });

    it("re-enables input and buttons after an error, with text preserved", async () => {
      const validateDeferred = createDeferred<ValidateData>();
      const client = createFakeClient({
        validatePhrase: vi.fn(() => validateDeferred.promise),
      });
      render(<PhraseForm client={client} />);

      typeText("Comprar leche");
      fireEvent.click(screen.getByRole("button", { name: copy.button.validate }));

      await act(async () => {
        validateDeferred.reject(
          new ApiError({ code: "EMBEDDING_UNAVAILABLE", status: 503, message: "down" }),
        );
      });

      await waitFor(() =>
        expect(
          screen.getByRole("button", { name: copy.button.retry }),
        ).toBeInTheDocument(),
      );
      expect(screen.getByLabelText(copy.input.label)).not.toBeDisabled();
      expect(screen.getByLabelText(copy.input.label)).toHaveValue("Comprar leche");
      expect(
        screen.getByRole("button", { name: copy.button.validate }),
      ).not.toBeDisabled();

      fireEvent.click(screen.getByRole("button", { name: copy.button.retry }));
      expect(screen.getByLabelText(copy.input.label)).toHaveValue("Comprar leche");
      expect(
        screen.queryByRole("button", { name: copy.button.retry }),
      ).not.toBeInTheDocument();
    });
  });

  // phrase-ui spec, "Error handling": the `error` state MUST render the
  // code-specific Spanish message via `errorCopy` (i18n/errorCopy.ts), not a
  // single generic string for every failure.
  describe("error handling copy (per-code Spanish messages)", () => {
    it("Model unavailable: 503 EMBEDDING_UNAVAILABLE shows the embedding-unavailable message", async () => {
      const validateDeferred = createDeferred<ValidateData>();
      const client = createFakeClient({
        validatePhrase: vi.fn(() => validateDeferred.promise),
      });
      render(<PhraseForm client={client} />);

      typeText("Comprar leche");
      fireEvent.click(screen.getByRole("button", { name: copy.button.validate }));
      await act(async () => {
        validateDeferred.reject(
          new ApiError({ code: "EMBEDDING_UNAVAILABLE", status: 503, message: "model down" }),
        );
      });

      await waitFor(() =>
        expect(screen.getByText(copy.error.embeddingUnavailable)).toBeInTheDocument(),
      );
    });

    it("Timeout: 504 EMBEDDING_TIMEOUT shows the timeout message", async () => {
      const validateDeferred = createDeferred<ValidateData>();
      const client = createFakeClient({
        validatePhrase: vi.fn(() => validateDeferred.promise),
      });
      render(<PhraseForm client={client} />);

      typeText("Comprar leche");
      fireEvent.click(screen.getByRole("button", { name: copy.button.validate }));
      await act(async () => {
        validateDeferred.reject(
          new ApiError({ code: "EMBEDDING_TIMEOUT", status: 504, message: "timed out" }),
        );
      });

      await waitFor(() =>
        expect(screen.getByText(copy.error.timeout)).toBeInTheDocument(),
      );
    });

    it("Network failure: a rejected fetch (NETWORK_ERROR) shows the network message", async () => {
      const validateDeferred = createDeferred<ValidateData>();
      const client = createFakeClient({
        validatePhrase: vi.fn(() => validateDeferred.promise),
      });
      render(<PhraseForm client={client} />);

      typeText("Comprar leche");
      fireEvent.click(screen.getByRole("button", { name: copy.button.validate }));
      await act(async () => {
        validateDeferred.reject(
          new ApiError({ code: "NETWORK_ERROR", status: 0, message: "Network request failed" }),
        );
      });

      await waitFor(() =>
        expect(screen.getByText(copy.error.network)).toBeInTheDocument(),
      );
    });

    it("Unknown code: an unmapped code falls back to the generic message", async () => {
      const validateDeferred = createDeferred<ValidateData>();
      const client = createFakeClient({
        validatePhrase: vi.fn(() => validateDeferred.promise),
      });
      render(<PhraseForm client={client} />);

      typeText("Comprar leche");
      fireEvent.click(screen.getByRole("button", { name: copy.button.validate }));
      await act(async () => {
        validateDeferred.reject(
          // Simulates future backend drift: a code outside the hand-maintained
          // `ErrorCode` union (client.ts's own documented, unenforced invariant).
          new ApiError({
            code: "SOME_FUTURE_CODE" as unknown as ApiError["code"],
            status: 500,
            message: "unmapped",
          }),
        );
      });

      await waitFor(() =>
        expect(screen.getByText(copy.error.generic)).toBeInTheDocument(),
      );
    });
  });

  describe("unmount mid-request", () => {
    it("discards a late-arriving validate response after unmount without a React state-update warning", async () => {
      const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
      const validateDeferred = createDeferred<ValidateData>();
      const client = createFakeClient({
        validatePhrase: vi.fn(() => validateDeferred.promise),
      });
      const { unmount } = render(<PhraseForm client={client} />);

      typeText("Comprar leche");
      fireEvent.click(screen.getByRole("button", { name: copy.button.validate }));
      await waitFor(() =>
        expect(screen.getByRole("status")).toHaveTextContent(copy.progress.validating),
      );

      unmount();

      // The same `cancelled` closure flag guards every in-flight branch of
      // the effect (validating, revalidating, saving) — this exercises it
      // via the validate call, the simplest deterministic repro.
      await act(async () => {
        validateDeferred.resolve(UNIQUE_RESULT);
      });

      expect(consoleError).not.toHaveBeenCalled();
      consoleError.mockRestore();
    });
  });

  describe("client-side input checks", () => {
    it("disables Validar and Guardar for empty/whitespace-only text", () => {
      render(<PhraseForm client={createFakeClient()} />);
      expect(
        screen.getByRole("button", { name: copy.button.validate }),
      ).toBeDisabled();
      expect(screen.getByRole("button", { name: copy.button.save })).toBeDisabled();

      typeText("   ");
      expect(
        screen.getByRole("button", { name: copy.button.validate }),
      ).toBeDisabled();
    });

    it("shows the over-length message and disables submission past the limit", () => {
      render(<PhraseForm client={createFakeClient()} maxLength={5} />);
      typeText("123456");
      expect(screen.getByText(copy.error.tooLong)).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: copy.button.validate }),
      ).toBeDisabled();
    });

    it("counts Unicode code points, not UTF-16 units, against the limit", () => {
      render(<PhraseForm client={createFakeClient()} maxLength={3} />);
      typeText("😀😀😀");
      expect(screen.queryByText(copy.error.tooLong)).not.toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: copy.button.validate }),
      ).not.toBeDisabled();
      expect(screen.getByLabelText(copy.input.label)).toHaveAccessibleDescription(
        "3/3",
      );
    });
  });
});
