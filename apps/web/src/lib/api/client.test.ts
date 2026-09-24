// Hand-rolled fake fetch (no MSW — see tasks.md 10.2 and design.md's testing
// strategy: "MSW rejected: extra dep for no gain at this size").
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "./errors";
import { createApiClient } from "./client";

interface FakeResponseInit {
  status: number;
  body: unknown;
  ok?: boolean;
}

function fakeResponse({ status, body, ok }: FakeResponseInit): Response {
  return {
    ok: ok ?? (status >= 200 && status < 300),
    status,
    json: async () => body,
  } as Response;
}

/** A 2xx response whose body is not valid JSON — `response.json()` rejects. */
function fakeUnparseableResponse(status: number): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async (): Promise<unknown> => {
      throw new SyntaxError("Unexpected end of JSON input");
    },
  } as Response;
}

describe("createApiClient", () => {
  describe("validatePhrase", () => {
    it("unwraps the data envelope and posts the JSON body to /phrases/validate", async () => {
      const validateData = {
        threshold: 0.8,
        is_duplicate: false,
        score: null,
        most_similar: null,
        matches: [],
        next_cursor: null,
        has_more: false,
      };
      const fetchImpl = vi.fn<typeof fetch>(async () =>
        fakeResponse({ status: 200, body: { data: validateData } }),
      );
      const client = createApiClient({ baseUrl: "http://api.test", fetchImpl });

      const result = await client.validatePhrase({ text: "Comprar leche" });

      expect(result).toEqual(validateData);
      expect(fetchImpl).toHaveBeenCalledTimes(1);
      const [url, init = {}] = fetchImpl.mock.calls[0];
      expect(url).toBe("http://api.test/phrases/validate");
      expect(init.method).toBe("POST");
      expect(init.body).toBe(JSON.stringify({ text: "Comprar leche" }));
      expect((init.headers as Record<string, string>)["Content-Type"]).toBe(
        "application/json",
      );
    });
  });

  describe("listPhrases", () => {
    it("sends a GET request with no body and unwraps the page envelope", async () => {
      const items = [
        {
          id: "1",
          text: "Comprar leche",
          created_at: "2026-01-01T00:00:00Z",
          validation: {
            status: "unique",
            score: null,
            most_similar_phrase_id: null,
            validated_at: "2026-01-01T00:00:00Z",
          },
        },
      ];
      const pageData = { items, total: 1, next_cursor: null, has_more: false };
      const fetchImpl = vi.fn<typeof fetch>(async () =>
        fakeResponse({ status: 200, body: { data: pageData } }),
      );
      const client = createApiClient({ baseUrl: "http://api.test", fetchImpl });

      const result = await client.listPhrases();

      expect(result).toEqual(pageData);
      const [url, init = {}] = fetchImpl.mock.calls[0];
      expect(url).toBe("http://api.test/phrases");
      expect(init.method).toBe("GET");
      expect(init.body).toBeUndefined();
    });

    it("encodes limit and cursor as a query string", async () => {
      const pageData = { items: [], total: 0, next_cursor: null, has_more: false };
      const fetchImpl = vi.fn<typeof fetch>(async () =>
        fakeResponse({ status: 200, body: { data: pageData } }),
      );
      const client = createApiClient({ baseUrl: "http://api.test", fetchImpl });

      await client.listPhrases({ limit: 10, cursor: "opaque-cursor" });

      const [url] = fetchImpl.mock.calls[0];
      expect(url).toBe("http://api.test/phrases?limit=10&cursor=opaque-cursor");
    });

    // design.md "Frontend": `ListPhrasesParams` gains `status`/`q`/`minScore`,
    // serialized as `status`/`q`/`min_score` — matching the exact param
    // names/shapes `GET /phrases` exposes (Unit 1/2's contract).
    it("encodes status, q and min_score as query params", async () => {
      const pageData = { items: [], total: 0, next_cursor: null, has_more: false };
      const fetchImpl = vi.fn<typeof fetch>(async () =>
        fakeResponse({ status: 200, body: { data: pageData } }),
      );
      const client = createApiClient({ baseUrl: "http://api.test", fetchImpl });

      await client.listPhrases({
        status: "duplicate_confirmed",
        q: "leche",
        minScore: 0.85,
      });

      const [url] = fetchImpl.mock.calls[0];
      expect(url).toBe(
        "http://api.test/phrases?status=duplicate_confirmed&q=leche&min_score=0.85",
      );
    });

    it("sends no filter params when status/q/minScore are undefined", async () => {
      const pageData = { items: [], total: 0, next_cursor: null, has_more: false };
      const fetchImpl = vi.fn<typeof fetch>(async () =>
        fakeResponse({ status: 200, body: { data: pageData } }),
      );
      const client = createApiClient({ baseUrl: "http://api.test", fetchImpl });

      await client.listPhrases({});

      const [url] = fetchImpl.mock.calls[0];
      expect(url).toBe("http://api.test/phrases");
    });
  });

  describe("listMatches", () => {
    it("unwraps the data envelope and posts the JSON body to /phrases/matches", async () => {
      const matchesData = {
        matches: [{ id: "7", text: "Comprar leche", score: 0.9312 }],
        next_cursor: "opaque-cursor",
        has_more: true,
      };
      const fetchImpl = vi.fn<typeof fetch>(async () =>
        fakeResponse({ status: 200, body: { data: matchesData } }),
      );
      const client = createApiClient({ baseUrl: "http://api.test", fetchImpl });

      const result = await client.listMatches({
        text: "Comprar leche",
        cursor: "opaque-cursor-0",
      });

      expect(result).toEqual(matchesData);
      expect(fetchImpl).toHaveBeenCalledTimes(1);
      const [url, init = {}] = fetchImpl.mock.calls[0];
      expect(url).toBe("http://api.test/phrases/matches");
      expect(init.method).toBe("POST");
      expect(init.body).toBe(
        JSON.stringify({ text: "Comprar leche", cursor: "opaque-cursor-0" }),
      );
    });
  });

  describe("savePhrase", () => {
    it("unwraps the data envelope and posts the JSON body to /phrases on a 201", async () => {
      const phrase = {
        id: "1",
        text: "Comprar leche",
        created_at: "2026-01-01T00:00:00Z",
        validation: {
          status: "unique",
          score: 0.12,
          most_similar_phrase_id: null,
          validated_at: "2026-01-01T00:00:00Z",
        },
      };
      const fetchImpl = vi.fn<typeof fetch>(async () =>
        fakeResponse({ status: 201, body: { data: phrase } }),
      );
      const client = createApiClient({ baseUrl: "http://api.test", fetchImpl });

      const result = await client.savePhrase({
        text: "Comprar leche",
        confirm_duplicate: false,
      });

      expect(result).toEqual(phrase);
      expect(fetchImpl).toHaveBeenCalledTimes(1);
      const [url, init = {}] = fetchImpl.mock.calls[0];
      expect(url).toBe("http://api.test/phrases");
      expect(init.method).toBe("POST");
      expect(init.body).toBe(
        JSON.stringify({ text: "Comprar leche", confirm_duplicate: false }),
      );
    });
  });

  describe("error envelope handling", () => {
    it("throws an ApiError built from a 422 VALIDATION_ERROR envelope", async () => {
      const fetchImpl = vi.fn(async () =>
        fakeResponse({
          status: 422,
          body: {
            error: {
              code: "VALIDATION_ERROR",
              message: "text: empty",
              details: { fields: [{ field: "text", reason: "empty" }] },
            },
          },
        }),
      );
      const client = createApiClient({ baseUrl: "http://api.test", fetchImpl });

      await expect(client.validatePhrase({ text: "" })).rejects.toMatchObject({
        name: "ApiError",
        code: "VALIDATION_ERROR",
        status: 422,
        message: "text: empty",
        details: { fields: [{ field: "text", reason: "empty" }] },
      });
    });

    // Triangulation: a different endpoint, a different status/code/details
    // shape — proves the mapping reads the envelope generically rather than
    // being hardcoded to the 422 case above.
    it("throws an ApiError built from a 409 DUPLICATE_CONFIRMATION_REQUIRED envelope on save", async () => {
      const details = {
        threshold: 0.8,
        score: 0.9312,
        most_similar: { id: "7", text: "Comprar leche", score: 0.9312 },
        matches: [{ id: "7", text: "Comprar leche", score: 0.9312 }],
        next_cursor: null,
        has_more: false,
      };
      const fetchImpl = vi.fn(async () =>
        fakeResponse({
          status: 409,
          body: {
            error: {
              code: "DUPLICATE_CONFIRMATION_REQUIRED",
              message: "duplicate requires confirmation",
              details,
            },
          },
        }),
      );
      const client = createApiClient({ baseUrl: "http://api.test", fetchImpl });

      const error = await client
        .savePhrase({ text: "Comprar leche", confirm_duplicate: false })
        .catch((caught: unknown) => caught);

      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).code).toBe("DUPLICATE_CONFIRMATION_REQUIRED");
      expect((error as ApiError).status).toBe(409);
      expect((error as ApiError).details).toEqual(details);
    });

    // Exercises FALLBACK_ERROR_CODE's actual trigger condition: a server
    // error envelope whose `error.code` field is absent (not merely a
    // malformed body — the envelope itself is well-formed JSON, just missing
    // the one field the fallback exists for).
    it("falls back to INTERNAL_ERROR when the error envelope's `code` field is missing", async () => {
      const fetchImpl = vi.fn(async () =>
        fakeResponse({
          status: 500,
          body: {
            error: {
              message: "something broke",
              details: null,
            },
          },
        }),
      );
      const client = createApiClient({ baseUrl: "http://api.test", fetchImpl });

      const error = await client
        .validatePhrase({ text: "Comprar leche" })
        .catch((caught: unknown) => caught);

      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).code).toBe("INTERNAL_ERROR");
      expect((error as ApiError).status).toBe(500);
      expect((error as ApiError).message).toBe("something broke");
    });
  });

  describe("default fetchImpl binding", () => {
    // Regression test for a real production bug: `fetchImpl: config.fetchImpl
    // ?? fetch` stored a *bare* reference to `fetch`. The Fetch spec requires
    // `fetch` to be invoked with `this === Window` (or the worker scope);
    // calling the bare reference later as `config.fetchImpl(...)` invokes it
    // with `this === config`, which real browsers reject with `TypeError:
    // Failed to execute 'fetch' on 'Window': Illegal invocation` — before any
    // request is ever dispatched, so `Validar`/`Guardar` failed instantly
    // with the generic network-error copy and zero network activity. Node's
    // own fetch (used by this jsdom-based suite) does not enforce that
    // receiver check, so this test asserts the binding directly rather than
    // reproducing the browser-only symptom; the real symptom was verified
    // end-to-end in a real browser.
    it("binds the default fetchImpl to globalThis instead of an unbound reference", async () => {
      let capturedThis: unknown;
      const spy = vi
        .spyOn(globalThis, "fetch")
        .mockImplementation(function (this: unknown) {
          capturedThis = this;
          return Promise.resolve(
            fakeResponse({ status: 200, body: { data: { items: [] } } }),
          );
        });

      const client = createApiClient({ baseUrl: "http://api.test" }); // no fetchImpl injected
      await client.listPhrases();

      expect(capturedThis).toBe(globalThis);
      spy.mockRestore();
    });
  });

  describe("network failure", () => {
    it("normalizes a rejected fetch to a NETWORK_ERROR ApiError", async () => {
      const fetchImpl = vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      });
      const client = createApiClient({ baseUrl: "http://api.test", fetchImpl });

      const error = await client
        .validatePhrase({ text: "Comprar leche" })
        .catch((caught: unknown) => caught);

      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).code).toBe("NETWORK_ERROR");
      expect((error as ApiError).status).toBe(0);
    });
  });

  describe("malformed success body handling", () => {
    // These mirror the error path's own defensiveness: a client bug on a 2xx
    // response must never surface as an unhandled TypeError or a silent
    // `undefined` return — it must throw the same typed ApiError shape as
    // every other failure this client produces.
    it("throws a typed ApiError when a 2xx response body fails to parse as JSON", async () => {
      const fetchImpl = vi.fn<typeof fetch>(async () =>
        fakeUnparseableResponse(200),
      );
      const client = createApiClient({ baseUrl: "http://api.test", fetchImpl });

      const error = await client
        .validatePhrase({ text: "Comprar leche" })
        .catch((caught: unknown) => caught);

      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).code).toBe("INTERNAL_ERROR");
      expect((error as ApiError).status).toBe(200);
    });

    // Triangulation: a different failure mode (valid JSON, wrong shape) that
    // must reach the same guard as the unparseable case above, not silently
    // return `undefined` as if it were valid data.
    it("throws a typed ApiError when a 2xx response body has no `data` key", async () => {
      const fetchImpl = vi.fn<typeof fetch>(async () =>
        fakeResponse({ status: 200, body: { unexpected: "shape" } }),
      );
      const client = createApiClient({ baseUrl: "http://api.test", fetchImpl });

      const error = await client
        .validatePhrase({ text: "Comprar leche" })
        .catch((caught: unknown) => caught);

      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).code).toBe("INTERNAL_ERROR");
      expect((error as ApiError).status).toBe(200);
    });
  });
});
