// phrase-ui spec, "Saved phrase list with status badge" plus this project's
// own extension of "Infinite scroll over matches" to the saved list itself
// (page size 10, `{loaded}/{total}` counter) — component tests on a
// hand-rolled fake `listPhrases` (design.md: "MSW rejected"), same
// convention as `PhraseForm.test.tsx` / `DuplicateAlert.test.tsx`.
import { createRef } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PhraseApiClient } from "@/lib/api/client";
import type { components } from "@/types/api";
import { copy } from "@/i18n/copy.es";

import { PhraseList, type PhraseListHandle } from "./PhraseList";

type PhraseOut = components["schemas"]["_PhraseOut"];
type PhraseListData = components["schemas"]["_PhraseListData"];

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

function fakePage(items: PhraseOut[], overrides: Partial<PhraseListData> = {}): PhraseListData {
  return { items, total: items.length, next_cursor: null, has_more: false, ...overrides };
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

// jsdom has no real IntersectionObserver — same fake-and-capture-the-callback
// approach as `DuplicateAlert.test.tsx`'s own sentinel tests, so a test can
// simulate the sentinel intersecting without a real layout/viewport.
function stubIntersectionObserver() {
  let capturedCallback: IntersectionObserverCallback | null = null;
  class FakeIntersectionObserver {
    constructor(callback: IntersectionObserverCallback) {
      capturedCallback = callback;
    }
    observe() {}
    disconnect() {}
  }
  vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);
  return {
    intersect: () => {
      capturedCallback?.([{ isIntersecting: true }] as IntersectionObserverEntry[], {} as IntersectionObserver);
    },
  };
}

describe("PhraseList", () => {
  it("Badge unique: shows the Única badge and no similarity text when score is null", () => {
    render(<PhraseList client={createFakeClient()} initialPage={fakePage([fakePhrase()])} />);

    const item = screen.getByRole("listitem");
    expect(item).toHaveTextContent(copy.badge.unique);
    expect(item).not.toHaveTextContent(/Similitud/);
  });

  it("Badge duplicate confirmed: shows the badge and the floored similarity percentage", () => {
    render(
      <PhraseList
        client={createFakeClient()}
        initialPage={fakePage([
          fakePhrase({
            validation: {
              status: "duplicate_confirmed",
              score: 0.9312,
              most_similar_phrase_id: "7",
              validated_at: "2026-01-01T00:00:00Z",
            },
          }),
        ])}
      />,
    );

    const item = screen.getByRole("listitem");
    expect(item).toHaveTextContent(copy.badge.duplicate_confirmed);
    expect(item).toHaveTextContent("Similitud: 93%");
  });

  it("Empty list: shows the empty-state message", () => {
    render(<PhraseList client={createFakeClient()} initialPage={fakePage([])} />);

    expect(screen.getByText(copy.list.empty)).toBeInTheDocument();
  });

  it("List load failure: a null initialPage (the Server Component's own fetch failed) shows the error and a Reintentar action", () => {
    render(<PhraseList client={createFakeClient()} initialPage={null} />);

    expect(screen.getByText(copy.list.loadError)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: copy.button.retry }),
    ).toBeInTheDocument();
  });

  it("Reintentar re-fetches and, on success, replaces the error with the loaded items", async () => {
    const client = createFakeClient({
      listPhrases: vi.fn(async () => fakePage([fakePhrase()])),
    });
    render(<PhraseList client={client} initialPage={null} />);

    fireEvent.click(screen.getByRole("button", { name: copy.button.retry }));

    await waitFor(() =>
      expect(screen.getByRole("listitem")).toHaveTextContent(copy.badge.unique),
    );
    expect(screen.queryByText(copy.list.loadError)).not.toBeInTheDocument();
  });

  it("refresh() (imperative handle) re-fetches and updates the items without a page reload", async () => {
    const client = createFakeClient({
      listPhrases: vi.fn(async () =>
        fakePage([fakePhrase({ id: "2", text: "Regar plantas" })]),
      ),
    });
    const ref = createRef<PhraseListHandle>();
    render(<PhraseList ref={ref} client={client} initialPage={fakePage([fakePhrase()])} />);
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
    render(<PhraseList ref={ref} client={client} initialPage={fakePage([fakePhrase()])} />);

    await act(async () => {
      await ref.current?.refresh();
    });

    expect(screen.getByText(copy.list.loadError)).toBeInTheDocument();
    // phrase-ui spec, "Page load failure" precedent applied to the phrase
    // list too: loaded items remain, they are not blanked by a failed refresh.
    expect(screen.getByRole("listitem")).toHaveTextContent("Comprar leche");
  });

  it("Loading state: does not show the empty-state message while a refresh (e.g. Reintentar) is in flight with zero items, and keeps aria-busy as the loading signal", async () => {
    const deferred = createDeferred<PhraseListData>();
    const client = createFakeClient({ listPhrases: vi.fn(() => deferred.promise) });
    const ref = createRef<PhraseListHandle>();
    const { container } = render(
      <PhraseList ref={ref} client={client} initialPage={fakePage([])} />,
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
      deferred.resolve(fakePage([]));
    });
    expect(screen.getByText(copy.list.empty)).toBeInTheDocument();
  });

  it("Unrecognized status: an unknown validation status does not silently render as the Única badge without a dev-visible signal", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined);

    render(
      <PhraseList
        client={createFakeClient()}
        initialPage={fakePage([
          fakePhrase({
            validation: {
              status: "some_future_status",
              score: null,
              most_similar_phrase_id: null,
              validated_at: "2026-01-01T00:00:00Z",
            },
          }),
        ])}
      />,
    );

    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining("some_future_status"));
    warnSpy.mockRestore();
  });

  describe("counter", () => {
    it("shows {loaded}/{total} next to the list", () => {
      render(
        <PhraseList
          client={createFakeClient()}
          initialPage={fakePage([fakePhrase()], { total: 60, has_more: true, next_cursor: "c1" })}
        />,
      );

      expect(screen.getByText("1/60")).toBeInTheDocument();
    });

    it("is absent when the list is empty", () => {
      render(<PhraseList client={createFakeClient()} initialPage={fakePage([])} />);
      expect(screen.queryByText(/\/\d/)).not.toBeInTheDocument();
    });
  });

  describe("infinite scroll", () => {
    it("loads the next page when the sentinel intersects, appends items, and updates the counter", async () => {
      const io = stubIntersectionObserver();
      const page1 = fakePage([fakePhrase({ id: "1", text: "p1" })], {
        total: 3,
        has_more: true,
        next_cursor: "c1",
      });
      const page2 = fakePage([fakePhrase({ id: "2", text: "p2" }), fakePhrase({ id: "3", text: "p3" })], {
        total: 3,
        has_more: false,
        next_cursor: null,
      });
      const client = createFakeClient({ listPhrases: vi.fn(async () => page2) });
      render(<PhraseList client={client} initialPage={page1} />);

      expect(screen.getByText("1/3")).toBeInTheDocument();
      expect(screen.getByTestId("phrase-list-sentinel")).toBeInTheDocument();

      await act(async () => {
        io.intersect();
      });

      expect(client.listPhrases).toHaveBeenCalledWith({ cursor: "c1" });
      await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(3));
      expect(screen.getByText("3/3")).toBeInTheDocument();
      expect(screen.queryByTestId("phrase-list-sentinel")).not.toBeInTheDocument();
    });

    it("does not send a second request while one is already in flight", async () => {
      const io = stubIntersectionObserver();
      const deferred = createDeferred<PhraseListData>();
      const page1 = fakePage([fakePhrase()], { total: 5, has_more: true, next_cursor: "c1" });
      const client = createFakeClient({ listPhrases: vi.fn(() => deferred.promise) });
      render(<PhraseList client={client} initialPage={page1} />);

      act(() => {
        io.intersect();
        io.intersect();
      });

      expect(client.listPhrases).toHaveBeenCalledTimes(1);
      await act(async () => {
        deferred.resolve(fakePage([fakePhrase({ id: "2" })], { total: 5, has_more: false }));
      });
    });

    it("a failed page load shows an inline error with Reintentar and keeps the loaded items", async () => {
      const io = stubIntersectionObserver();
      const page1 = fakePage([fakePhrase()], { total: 3, has_more: true, next_cursor: "c1" });
      const client = createFakeClient({
        listPhrases: vi.fn(async () => {
          throw new Error("down");
        }),
      });
      render(<PhraseList client={client} initialPage={page1} />);

      await act(async () => {
        io.intersect();
      });

      expect(screen.getByText(copy.list.loadMoreError)).toBeInTheDocument();
      expect(screen.getByRole("listitem")).toHaveTextContent("Comprar leche");
    });

    it("does not append a page 2 item whose id already appeared on page 1", async () => {
      const io = stubIntersectionObserver();
      const shared = fakePhrase({ id: "1", text: "p1" });
      const page1 = fakePage([shared], { total: 2, has_more: true, next_cursor: "c1" });
      const page2 = fakePage([shared, fakePhrase({ id: "2", text: "p2" })], {
        total: 2,
        has_more: false,
      });
      const client = createFakeClient({ listPhrases: vi.fn(async () => page2) });
      render(<PhraseList client={client} initialPage={page1} />);

      await act(async () => {
        io.intersect();
      });

      await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(2));
    });
  });

  // phrase-ui spec, "Filter controls over the saved list" / "Filtered
  // counter and empty state" — design.md's `PhraseList.tsx` section: filter
  // state lives here, `refresh()` keeps its public signature and reads
  // `filtersRef.current`, a `generation` ref guards against a stale
  // response overwriting a newer one.
  describe("filters", () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it("changing the status filter refetches immediately, resets pagination, and sends the new status", async () => {
      const page1 = fakePage([fakePhrase({ id: "1", text: "p1" })], {
        total: 3,
        has_more: true,
        next_cursor: "c1",
      });
      const filteredPage = fakePage([fakePhrase({ id: "9", text: "dup" })], {
        total: 1,
        has_more: false,
      });
      const client = createFakeClient({ listPhrases: vi.fn(async () => filteredPage) });
      render(<PhraseList client={client} initialPage={page1} />);

      fireEvent.change(screen.getByLabelText(copy.filters.statusLabel), {
        target: { value: "duplicate_confirmed" },
      });

      await act(async () => {
        await Promise.resolve();
      });

      expect(client.listPhrases).toHaveBeenCalledWith({ status: "duplicate_confirmed" });
      expect(screen.getByText("1/1")).toBeInTheDocument();
      expect(screen.queryByTestId("phrase-list-sentinel")).not.toBeInTheDocument();
    });

    it("changing the minimum score refetches immediately with the percent/100 fraction and resets pagination", async () => {
      const page1 = fakePage([fakePhrase()], { total: 3, has_more: true, next_cursor: "c1" });
      const filteredPage = fakePage([fakePhrase({ id: "9" })], { total: 1, has_more: false });
      const client = createFakeClient({ listPhrases: vi.fn(async () => filteredPage) });
      render(<PhraseList client={client} initialPage={page1} />);

      fireEvent.change(screen.getByLabelText(copy.filters.minScoreLabel), {
        target: { value: "85" },
      });

      await act(async () => {
        await Promise.resolve();
      });

      expect(client.listPhrases).toHaveBeenCalledWith({ minScore: 0.85 });
    });

    it("debounces the text filter: only one request is sent after the user stops typing", async () => {
      const client = createFakeClient({ listPhrases: vi.fn(async () => fakePage([])) });
      render(<PhraseList client={client} initialPage={fakePage([fakePhrase()])} />);
      const input = screen.getByLabelText(copy.filters.textLabel);

      fireEvent.change(input, { target: { value: "l" } });
      fireEvent.change(input, { target: { value: "le" } });
      fireEvent.change(input, { target: { value: "lec" } });

      act(() => {
        vi.advanceTimersByTime(299);
      });
      expect(client.listPhrases).not.toHaveBeenCalled();

      await act(async () => {
        vi.advanceTimersByTime(1);
        await Promise.resolve();
      });

      expect(client.listPhrases).toHaveBeenCalledTimes(1);
      expect(client.listPhrases).toHaveBeenCalledWith({ q: "lec" });
    });

    it("clearing the text filter applies immediately, without waiting for the debounce", async () => {
      const listPhrases = vi.fn<PhraseApiClient["listPhrases"]>(async () => fakePage([]));
      const client = createFakeClient({ listPhrases });
      render(<PhraseList client={client} initialPage={fakePage([fakePhrase()])} />);
      const input = screen.getByLabelText(copy.filters.textLabel);

      fireEvent.change(input, { target: { value: "leche" } });
      act(() => {
        vi.advanceTimersByTime(300);
      });
      await act(async () => {
        await Promise.resolve();
      });
      listPhrases.mockClear();

      fireEvent.change(input, { target: { value: "" } });
      await act(async () => {
        await Promise.resolve();
      });

      expect(listPhrases).toHaveBeenCalledWith({});
    });

    it("combines active filters (status, min-score, debounced text) into one request", async () => {
      const client = createFakeClient({ listPhrases: vi.fn(async () => fakePage([])) });
      render(<PhraseList client={client} initialPage={fakePage([fakePhrase()])} />);

      fireEvent.change(screen.getByLabelText(copy.filters.statusLabel), {
        target: { value: "unique" },
      });
      fireEvent.change(screen.getByLabelText(copy.filters.minScoreLabel), {
        target: { value: "50" },
      });
      fireEvent.change(screen.getByLabelText(copy.filters.textLabel), {
        target: { value: "leche" },
      });

      act(() => {
        vi.advanceTimersByTime(300);
      });
      await act(async () => {
        await Promise.resolve();
      });

      expect(client.listPhrases).toHaveBeenLastCalledWith({
        status: "unique",
        minScore: 0.5,
        q: "leche",
      });
    });

    it("drops a stale response when a newer filter change already resolved (generation guard)", async () => {
      const first = createDeferred<PhraseListData>();
      const second = fakePage([fakePhrase({ id: "9", text: "second" })], { total: 1 });
      const listPhrases = vi
        .fn<PhraseApiClient["listPhrases"]>()
        .mockImplementationOnce(() => first.promise)
        .mockImplementationOnce(async () => second);
      const client = createFakeClient({ listPhrases });
      render(<PhraseList client={client} initialPage={fakePage([fakePhrase()])} />);

      fireEvent.change(screen.getByLabelText(copy.filters.statusLabel), {
        target: { value: "unique" },
      });
      await act(async () => {
        await Promise.resolve();
      });
      expect(listPhrases).toHaveBeenCalledTimes(1);

      fireEvent.change(screen.getByLabelText(copy.filters.statusLabel), {
        target: { value: "duplicate_confirmed" },
      });
      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });
      expect(listPhrases).toHaveBeenCalledTimes(2);
      expect(screen.getByText("second")).toBeInTheDocument();

      await act(async () => {
        first.resolve(fakePage([fakePhrase({ id: "1", text: "stale" })], { total: 99 }));
        await Promise.resolve();
      });

      expect(screen.getByText("second")).toBeInTheDocument();
      expect(screen.queryByText("stale")).not.toBeInTheDocument();
      expect(screen.getByText("1/1")).toBeInTheDocument();
    });

    it("refresh() (the post-save/Reintentar call site) keeps the currently active filters", async () => {
      const listPhrases = vi.fn<PhraseApiClient["listPhrases"]>(async () =>
        fakePage([fakePhrase({ id: "2" })]),
      );
      const client = createFakeClient({ listPhrases });
      const ref = createRef<PhraseListHandle>();
      render(<PhraseList ref={ref} client={client} initialPage={fakePage([fakePhrase()])} />);

      fireEvent.change(screen.getByLabelText(copy.filters.statusLabel), {
        target: { value: "unique" },
      });
      await act(async () => {
        await Promise.resolve();
      });
      expect(listPhrases).toHaveBeenCalledWith({ status: "unique" });
      listPhrases.mockClear();

      await act(async () => {
        await ref.current?.refresh();
      });

      expect(listPhrases).toHaveBeenCalledWith({ status: "unique" });
    });

    it("shows a distinct filtered-empty-state message with a clear-filters action, not the unfiltered empty message", async () => {
      const client = createFakeClient({ listPhrases: vi.fn(async () => fakePage([])) });
      render(<PhraseList client={client} initialPage={fakePage([fakePhrase()])} />);

      fireEvent.change(screen.getByLabelText(copy.filters.statusLabel), {
        target: { value: "duplicate_confirmed" },
      });
      await act(async () => {
        await Promise.resolve();
      });
      expect(screen.getByText(copy.list.emptyFiltered)).toBeInTheDocument();
      expect(screen.queryByText(copy.list.empty)).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: copy.button.clearFilters })).toBeInTheDocument();
    });

    it("clear-filters resets all three controls and refetches the unfiltered list from page 1", async () => {
      const emptyFilteredPage = fakePage([]);
      const unfilteredPage = fakePage([fakePhrase()]);
      const listPhrases = vi
        .fn<PhraseApiClient["listPhrases"]>()
        .mockImplementationOnce(async () => emptyFilteredPage)
        .mockImplementationOnce(async () => unfilteredPage);
      const client = createFakeClient({ listPhrases });
      render(<PhraseList client={client} initialPage={fakePage([fakePhrase()])} />);

      fireEvent.change(screen.getByLabelText(copy.filters.statusLabel), {
        target: { value: "duplicate_confirmed" },
      });
      await act(async () => {
        await Promise.resolve();
      });
      expect(screen.getByText(copy.list.emptyFiltered)).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: copy.button.clearFilters }));

      await act(async () => {
        await Promise.resolve();
      });
      expect(listPhrases).toHaveBeenLastCalledWith({});
      expect(screen.getByRole("listitem")).toBeInTheDocument();
      expect(screen.getByLabelText(copy.filters.statusLabel)).toHaveValue("");
      expect(screen.getByLabelText(copy.filters.textLabel)).toHaveValue("");
    });
  });
});
