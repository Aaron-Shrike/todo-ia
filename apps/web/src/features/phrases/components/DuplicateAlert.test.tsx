// Component tests on a hand-rolled, deferred-promise fake `PhraseApiClient`
// (same pattern as `PhraseForm.test.tsx`, design.md's "MSW rejected") plus a
// fake `IntersectionObserver` (jsdom has none) whose captured callback is
// triggered manually to simulate the sentinel scrolling into view.
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, type PhraseApiClient } from "@/lib/api/client";
import type { components } from "@/types/api";
import { copy } from "@/i18n/copy.es";

import type { DuplicateDetails } from "../machine";
import { DuplicateAlert } from "./DuplicateAlert";

type MatchesData = components["schemas"]["_MatchesData"];

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

class FakeIntersectionObserver {
  static instances: FakeIntersectionObserver[] = [];
  callback: IntersectionObserverCallback;
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();

  constructor(callback: IntersectionObserverCallback) {
    this.callback = callback;
    FakeIntersectionObserver.instances.push(this);
  }

  trigger() {
    this.callback(
      [{ isIntersecting: true } as IntersectionObserverEntry],
      this as unknown as IntersectionObserver,
    );
  }
}

function latestObserver(): FakeIntersectionObserver {
  const observer = FakeIntersectionObserver.instances.at(-1);
  if (!observer) throw new Error("no IntersectionObserver was constructed — is the sentinel rendered?");
  return observer;
}

beforeEach(() => {
  FakeIntersectionObserver.instances = [];
  vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);
});

const BASE_DETAILS: DuplicateDetails = {
  threshold: 0.8,
  score: 0.9312,
  mostSimilar: { id: "7", text: "Comprar leche", score: 0.9312 },
  matches: [{ id: "7", text: "Comprar leche", score: 0.9312 }],
  nextCursor: "cursor-1",
  hasMore: true,
};

const SINGLE_PAGE_DETAILS: DuplicateDetails = {
  ...BASE_DETAILS,
  nextCursor: null,
  hasMore: false,
};

interface RenderOverrides {
  details?: DuplicateDetails;
  disabled?: boolean;
  client?: PhraseApiClient;
}

function renderAlert(overrides: RenderOverrides = {}) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  const onInvalidCursor = vi.fn();
  const client = overrides.client ?? createFakeClient();
  render(
    <DuplicateAlert
      client={client}
      text="Comprar leche"
      details={overrides.details ?? BASE_DETAILS}
      disabled={overrides.disabled ?? false}
      onConfirm={onConfirm}
      onCancel={onCancel}
      onInvalidCursor={onInvalidCursor}
    />,
  );
  return { onConfirm, onCancel, onInvalidCursor, client };
}

function fakePage(overrides: Partial<MatchesData>): MatchesData {
  return { matches: [], next_cursor: null, has_more: false, ...overrides };
}

describe("DuplicateAlert", () => {
  it("Alert content: shows an alertdialog with the title, most similar phrase, its floored percentage, and both actions", () => {
    renderAlert({ details: SINGLE_PAGE_DETAILS });
    const dialog = screen.getByRole("alertdialog");
    expect(dialog).toHaveTextContent(copy.duplicate.title);
    expect(dialog).toHaveTextContent("Comprar leche");
    expect(dialog).toHaveTextContent("93%");
    expect(screen.getByRole("button", { name: copy.button.confirm })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: copy.button.cancel })).toBeInTheDocument();
  });

  it.each([
    [0.995, "99%"],
    [0.9999, "99%"],
    [0.29, "29%"],
    [1, "100%"],
  ])("Percentage never overstates: score %s renders %s, never rounded up", (score, expected) => {
    renderAlert({
      details: {
        ...SINGLE_PAGE_DETAILS,
        score,
        mostSimilar: { id: "7", text: "Comprar leche", score },
      },
    });
    expect(screen.getByRole("alertdialog")).toHaveTextContent(expected);
  });

  it("Confirm: pressing Guardar de todos modos calls onConfirm and sends no request itself", () => {
    const { onConfirm, client } = renderAlert({ details: SINGLE_PAGE_DETAILS });
    fireEvent.click(screen.getByRole("button", { name: copy.button.confirm }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(client.savePhrase).not.toHaveBeenCalled();
  });

  it("Cancel: pressing Cancelar calls onCancel and sends no request", () => {
    const { onCancel, client } = renderAlert({ details: SINGLE_PAGE_DETAILS });
    fireEvent.click(screen.getByRole("button", { name: copy.button.cancel }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(client.listMatches).not.toHaveBeenCalled();
  });

  it("Confirmar and Cancelar are disabled while saving", () => {
    renderAlert({ details: SINGLE_PAGE_DETAILS, disabled: true });
    expect(screen.getByRole("button", { name: copy.button.confirm })).toBeDisabled();
    expect(screen.getByRole("button", { name: copy.button.cancel })).toBeDisabled();
  });

  it("Single page: no sentinel and no loading copy when has_more is already false", () => {
    renderAlert({ details: SINGLE_PAGE_DETAILS });
    expect(screen.queryByTestId("matches-sentinel")).not.toBeInTheDocument();
    expect(screen.queryByText(copy.duplicate.loadingMore)).not.toBeInTheDocument();
  });

  it("Load next page on scroll: requests the next cursor exactly once, shows the loading copy meanwhile, and appends the results in order", async () => {
    const deferred = createDeferred<MatchesData>();
    const client = createFakeClient({ listMatches: vi.fn(() => deferred.promise) });
    const dialog_ = renderAlert({ client });
    const dialog = screen.getByRole("alertdialog");

    act(() => {
      latestObserver().trigger();
    });

    expect(dialog_.client.listMatches).toHaveBeenCalledTimes(1);
    expect(dialog_.client.listMatches).toHaveBeenCalledWith({
      text: "Comprar leche",
      cursor: "cursor-1",
    });
    await waitFor(() => expect(dialog).toHaveTextContent(copy.duplicate.loadingMore));

    await act(async () => {
      deferred.resolve(
        fakePage({ matches: [{ id: "9", text: "Ir a comprar leche", score: 0.85 }] }),
      );
    });

    expect(dialog).not.toHaveTextContent(copy.duplicate.loadingMore);
    expect(dialog).toHaveTextContent("Ir a comprar leche");
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("Reach the end: stops requesting and removes the sentinel once has_more is false", async () => {
    const client = createFakeClient({
      listMatches: vi.fn(() =>
        Promise.resolve(
          fakePage({ matches: [{ id: "9", text: "Ir a comprar leche", score: 0.85 }] }),
        ),
      ),
    });
    renderAlert({ client });

    await act(async () => {
      latestObserver().trigger();
    });

    expect(screen.queryByTestId("matches-sentinel")).not.toBeInTheDocument();
    expect(client.listMatches).toHaveBeenCalledTimes(1);
  });

  it("No concurrent page requests: a second intersection while one is in flight sends nothing", async () => {
    const deferred = createDeferred<MatchesData>();
    const client = createFakeClient({ listMatches: vi.fn(() => deferred.promise) });
    renderAlert({ client });

    act(() => {
      latestObserver().trigger();
      latestObserver().trigger();
    });

    expect(client.listMatches).toHaveBeenCalledTimes(1);

    await act(async () => {
      deferred.resolve(fakePage({}));
    });
  });

  it("Invalid cursor restarts validation: a 400 INVALID_CURSOR discards the loaded matches, calls onInvalidCursor, and never retries the same cursor", async () => {
    const client = createFakeClient({
      listMatches: vi.fn(() =>
        Promise.reject(
          new ApiError({ code: "INVALID_CURSOR", status: 400, message: "cursor invalid" }),
        ),
      ),
    });
    const { onInvalidCursor } = renderAlert({ client });
    const dialog = screen.getByRole("alertdialog");

    await act(async () => {
      latestObserver().trigger();
    });

    expect(onInvalidCursor).toHaveBeenCalledTimes(1);
    expect(client.listMatches).toHaveBeenCalledTimes(1);
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
    expect(dialog).not.toHaveTextContent(copy.duplicate.loadMoreError);
  });

  it("Page load failure: keeps loaded items, shows a retry action, and retry re-requests the same cursor", async () => {
    const client = createFakeClient({
      listMatches: vi
        .fn()
        .mockRejectedValueOnce(
          new ApiError({ code: "INTERNAL_ERROR", status: 500, message: "boom" }),
        )
        .mockResolvedValueOnce(
          fakePage({ matches: [{ id: "9", text: "Ir a comprar leche", score: 0.85 }] }),
        ),
    });
    renderAlert({ client });
    const dialog = screen.getByRole("alertdialog");

    await act(async () => {
      latestObserver().trigger();
    });

    expect(dialog).toHaveTextContent(copy.duplicate.loadMoreError);
    expect(screen.getAllByRole("listitem")).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: copy.button.retry }));

    await waitFor(() => expect(dialog).toHaveTextContent("Ir a comprar leche"));
    expect(client.listMatches).toHaveBeenNthCalledWith(2, {
      text: "Comprar leche",
      cursor: "cursor-1",
    });
  });

  it("Deduplicate on overlap: a repeated id already displayed is not shown twice", async () => {
    const client = createFakeClient({
      listMatches: vi.fn(() =>
        Promise.resolve(
          fakePage({
            matches: [
              { id: "7", text: "Comprar leche", score: 0.9312 },
              { id: "9", text: "Ir a comprar leche", score: 0.85 },
            ],
          }),
        ),
      ),
    });
    renderAlert({ client });

    await act(async () => {
      latestObserver().trigger();
    });

    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });
});
