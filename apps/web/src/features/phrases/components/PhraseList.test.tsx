// phrase-ui spec, "Saved phrase list with status badge" — component tests on
// a hand-rolled fake `listPhrases` (design.md: "MSW rejected"), same
// convention as `PhraseForm.test.tsx` / `DuplicateAlert.test.tsx`.
import { createRef } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { PhraseApiClient } from "@/lib/api/client";
import type { components } from "@/types/api";
import { copy } from "@/i18n/copy.es";

import { PhraseList, type PhraseListHandle } from "./PhraseList";

type PhraseOut = components["schemas"]["_PhraseOut"];

function fakePhrase(overrides: Partial<PhraseOut> = {}): PhraseOut {
  return {
    id: "1",
    text: "Comprar leche",
    created_at: "2026-01-01T00:00:00Z",
    validation: {
      status: "unique",
      score: null,
      most_similar_phrase_id: null,
      validated_at: "2026-01-01T00:00:00Z",
    },
    ...overrides,
  };
}

function createFakeClient(
  overrides: Partial<Pick<PhraseApiClient, "listPhrases">> = {},
): Pick<PhraseApiClient, "listPhrases"> {
  return { listPhrases: vi.fn(), ...overrides };
}

describe("PhraseList", () => {
  it("Badge unique: shows the Única badge and no similarity text when score is null", () => {
    render(<PhraseList client={createFakeClient()} initialItems={[fakePhrase()]} />);

    const item = screen.getByRole("listitem");
    expect(item).toHaveTextContent(copy.badge.unique);
    expect(item).not.toHaveTextContent(/Similitud/);
  });

  it("Badge duplicate confirmed: shows the badge and the floored similarity percentage", () => {
    render(
      <PhraseList
        client={createFakeClient()}
        initialItems={[
          fakePhrase({
            validation: {
              status: "duplicate_confirmed",
              score: 0.9312,
              most_similar_phrase_id: "7",
              validated_at: "2026-01-01T00:00:00Z",
            },
          }),
        ]}
      />,
    );

    const item = screen.getByRole("listitem");
    expect(item).toHaveTextContent(copy.badge.duplicate_confirmed);
    expect(item).toHaveTextContent("Similitud: 93%");
  });

  it("Empty list: shows the empty-state message", () => {
    render(<PhraseList client={createFakeClient()} initialItems={[]} />);

    expect(screen.getByText(copy.list.empty)).toBeInTheDocument();
  });

  it("List load failure: a null initialItems (the Server Component's own fetch failed) shows the error and a Reintentar action", () => {
    render(<PhraseList client={createFakeClient()} initialItems={null} />);

    expect(screen.getByText(copy.list.loadError)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: copy.button.retry }),
    ).toBeInTheDocument();
  });

  it("Reintentar re-fetches and, on success, replaces the error with the loaded items", async () => {
    const client = createFakeClient({
      listPhrases: vi.fn(async () => ({ items: [fakePhrase()] })),
    });
    render(<PhraseList client={client} initialItems={null} />);

    fireEvent.click(screen.getByRole("button", { name: copy.button.retry }));

    await waitFor(() =>
      expect(screen.getByRole("listitem")).toHaveTextContent(copy.badge.unique),
    );
    expect(screen.queryByText(copy.list.loadError)).not.toBeInTheDocument();
  });

  it("refresh() (imperative handle) re-fetches and updates the items without a page reload", async () => {
    const client = createFakeClient({
      listPhrases: vi.fn(async () => ({
        items: [fakePhrase({ id: "2", text: "Regar plantas" })],
      })),
    });
    const ref = createRef<PhraseListHandle>();
    render(<PhraseList ref={ref} client={client} initialItems={[fakePhrase()]} />);
    expect(screen.getByRole("listitem")).toHaveTextContent("Comprar leche");

    await act(async () => {
      await ref.current?.refresh();
    });

    expect(client.listPhrases).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("listitem")).toHaveTextContent("Regar plantas");
  });

  it("a failed refresh() shows the non-blocking list error and keeps the previously loaded item visible", async () => {
    const client = createFakeClient({
      listPhrases: vi.fn(async () => {
        throw new Error("network down");
      }),
    });
    const ref = createRef<PhraseListHandle>();
    render(<PhraseList ref={ref} client={client} initialItems={[fakePhrase()]} />);

    await act(async () => {
      await ref.current?.refresh();
    });

    expect(screen.getByText(copy.list.loadError)).toBeInTheDocument();
    // phrase-ui spec, "Page load failure" precedent applied to the phrase
    // list too: loaded items remain, they are not blanked by a failed refresh.
    expect(screen.getByRole("listitem")).toHaveTextContent("Comprar leche");
  });
});
