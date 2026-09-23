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

// Same deferred-promise pattern as `DuplicateAlert.test.tsx` / `PhraseForm.test.tsx`.
function createDeferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
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

  it("Loading state: does not show the empty-state message while a refresh (e.g. Reintentar) is in flight with zero items, and keeps aria-busy as the loading signal", async () => {
    const deferred = createDeferred<{ items: PhraseOut[] }>();
    const client = createFakeClient({ listPhrases: vi.fn(() => deferred.promise) });
    const ref = createRef<PhraseListHandle>();
    const { container } = render(
      <PhraseList ref={ref} client={client} initialItems={[]} />,
    );
    expect(screen.getByText(copy.list.empty)).toBeInTheDocument();

    act(() => {
      void ref.current?.refresh();
    });

    // phrase-ui spec, "Saved phrase list with status badge": "MUST show ...
    // a loading state" — while the refetch is in flight the empty message
    // must NOT be shown, only the existing `aria-busy` loading signal.
    expect(screen.queryByText(copy.list.empty)).not.toBeInTheDocument();
    expect(container.querySelector("section")).toHaveAttribute("aria-busy", "true");

    await act(async () => {
      deferred.resolve({ items: [] });
    });
    expect(screen.getByText(copy.list.empty)).toBeInTheDocument();
  });

  it("Unrecognized status: an unknown validation status does not silently render as the Única badge without a dev-visible signal", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined);

    render(
      <PhraseList
        client={createFakeClient()}
        initialItems={[
          fakePhrase({
            validation: {
              status: "some_future_status",
              score: null,
              most_similar_phrase_id: null,
              validated_at: "2026-01-01T00:00:00Z",
            },
          }),
        ]}
      />,
    );

    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining("some_future_status"));
    warnSpy.mockRestore();
  });
});
