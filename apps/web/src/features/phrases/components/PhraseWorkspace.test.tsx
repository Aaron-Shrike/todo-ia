// phrase-ui spec, "Saved phrase list with status badge" — "Scenario: Refresh
// after save" and "Scenario: Refresh fails after a successful save". These
// exercise the `PhraseForm` -> `PhraseList` wiring itself (the `onSaved`
// callback triggering a browser-side refetch), not either component alone.
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { PhraseApiClient } from "@/lib/api/client";
import type { components } from "@/types/api";
import { copy } from "@/i18n/copy.es";

import { PhraseWorkspace } from "./PhraseWorkspace";

type ValidateData = components["schemas"]["_ValidateData"];
type PhraseOut = components["schemas"]["_PhraseOut"];
type PhraseListData = components["schemas"]["_PhraseListData"];

function fakePage(items: PhraseOut[], overrides: Partial<PhraseListData> = {}): PhraseListData {
  return { items, total: items.length, next_cursor: null, has_more: false, ...overrides };
}

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

function fakePhrase(overrides: Partial<PhraseOut> = {}): PhraseOut {
  return {
    id: "1",
    text: "Comprar leche",
    created_at: "2026-01-01T00:00:00Z",
    validation: {
      status: "unique",
      score: 0.12,
      most_similar_phrase_id: null,
      validated_at: "2026-01-01T00:00:00Z",
    },
    ...overrides,
  };
}

function typeText(text: string) {
  fireEvent.change(screen.getByLabelText(copy.input.label), {
    target: { value: text },
  });
}

describe("PhraseWorkspace", () => {
  it("Refresh after save: a successful 201 triggers a browser-side GET /phrases and the new phrase appears", async () => {
    const validateDeferred = createDeferred<ValidateData>();
    const saveDeferred = createDeferred<PhraseOut>();
    const savedPhrase = fakePhrase();
    const client = createFakeClient({
      validatePhrase: vi.fn(() => validateDeferred.promise),
      savePhrase: vi.fn(() => saveDeferred.promise),
      listPhrases: vi.fn(async () => fakePage([savedPhrase])),
    });
    render(<PhraseWorkspace client={client} initialPage={fakePage([])} />);

    typeText("Comprar leche");
    fireEvent.click(screen.getByRole("button", { name: copy.button.save }));
    await act(async () => {
      validateDeferred.resolve(UNIQUE_RESULT);
    });
    await act(async () => {
      saveDeferred.resolve(savedPhrase);
    });

    await waitFor(() => expect(client.listPhrases).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.getByRole("listitem")).toHaveTextContent("Comprar leche"),
    );
  });

  it("Refresh fails after a successful save: the machine stays idle, 'Frase guardada.' stays announced, and the list shows its own error (never the save error)", async () => {
    const validateDeferred = createDeferred<ValidateData>();
    const saveDeferred = createDeferred<PhraseOut>();
    const client = createFakeClient({
      validatePhrase: vi.fn(() => validateDeferred.promise),
      savePhrase: vi.fn(() => saveDeferred.promise),
      listPhrases: vi.fn(async () => {
        throw new Error("down");
      }),
    });
    render(<PhraseWorkspace client={client} initialPage={fakePage([])} />);

    typeText("Comprar leche");
    fireEvent.click(screen.getByRole("button", { name: copy.button.save }));
    await act(async () => {
      validateDeferred.resolve(UNIQUE_RESULT);
    });
    await act(async () => {
      saveDeferred.resolve(fakePhrase());
    });

    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(copy.saved.success),
    );
    await waitFor(() =>
      expect(screen.getByText(copy.list.loadError)).toBeInTheDocument(),
    );
    // Text was cleared (idle, not error) — the machine's own "Reintentar"
    // only renders in its `error` state, so exactly one "Reintentar" button
    // (the list's) proves the machine never entered `error` for this failure.
    expect(screen.getByLabelText(copy.input.label)).toHaveValue("");
    expect(screen.getAllByRole("button", { name: copy.button.retry })).toHaveLength(1);
  });
});
