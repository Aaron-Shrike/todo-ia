import type { components } from "@/types/api";

import { ApiError, type ErrorCode } from "./errors";

type Schemas = components["schemas"];

const DEFAULT_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface ApiClientConfig {
  /** Defaults to `NEXT_PUBLIC_API_URL` (browser) — pass `API_INTERNAL_URL` explicitly for Server Component calls. */
  baseUrl?: string;
  /** Injection seam for tests (design.md: "MSW rejected"); defaults to the global `fetch`. */
  fetchImpl?: typeof fetch;
}

export interface ListPhrasesParams {
  /** Page size; server default (10) applies when omitted. */
  limit?: number;
  /** Opaque continuation from a previous page's `next_cursor`. */
  cursor?: string;
}

export interface PhraseApiClient {
  validatePhrase(
    body: Schemas["_ValidateRequest"],
  ): Promise<Schemas["_ValidateData"]>;
  listMatches(
    body: Schemas["_MatchesRequest"],
  ): Promise<Schemas["_MatchesData"]>;
  savePhrase(body: Schemas["_SaveRequest"]): Promise<Schemas["_PhraseOut"]>;
  listPhrases(params?: ListPhrasesParams): Promise<Schemas["_PhraseListData"]>;
}

interface DataEnvelope<T> {
  data: T;
}

// Derived from the generated `ErrorEnvelope`/`ErrorDetail` schemas (not
// hand-rolled) so a backend envelope-shape change that regenerates
// `types/api.ts` produces a compiler error here instead of a silent runtime
// mismatch. `Partial` on the inner shape stays defensive: `body` itself is
// `unknown` until validated below, and a malformed/non-conforming payload
// must not throw before the fallback-error-code logic can run.
type ErrorEnvelopeBody = {
  error?: Partial<Schemas["ErrorDetail"]>;
};

/**
 * A malformed/non-JSON error body is defensive-only: `platform/errors.py`
 * always emits the envelope, so this path is not expected to run against a
 * real backend — it exists so a client bug can never surface as an unhandled
 * rejection with no `code` at all.
 */
const FALLBACK_ERROR_CODE: ErrorCode = "INTERNAL_ERROR";

async function request<T>(
  path: string,
  init: RequestInit,
  config: Required<ApiClientConfig>,
): Promise<T> {
  let response: Response;
  try {
    response = await config.fetchImpl(`${config.baseUrl}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init.headers },
    });
  } catch {
    // fetch() rejects on a network failure (no response was ever received) —
    // phrase-ui spec "Network failure": "GIVEN fetch rejects". There is no
    // server-issued code to read here.
    throw new ApiError({
      code: "NETWORK_ERROR",
      status: 0,
      message: "Network request failed before a response was received.",
    });
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    body = undefined;
  }

  if (!response.ok) {
    const errorBody = (body as ErrorEnvelopeBody | undefined)?.error;
    throw new ApiError({
      // Assumed invariant, not structurally enforced: `ErrorCode` (errors.ts)
      // must be kept in sync by hand with the backend's actual emitted codes
      // (services/api/src/platform/errors.py, main.py, router.py, health.py).
      // A server-supplied string outside that union is accepted here at
      // compile time with no runtime check; it currently matches the
      // backend's real codes (verified), but nothing prevents future drift.
      code: (errorBody?.code as ErrorCode | undefined) ?? FALLBACK_ERROR_CODE,
      status: response.status,
      message: errorBody?.message ?? `Request failed with status ${response.status}`,
      details: errorBody?.details,
    });
  }

  // Mirrors the error path above: a 2xx response whose body failed to parse
  // (`body === undefined`, from the catch above) or whose parsed shape has no
  // `data` key (envelope-shape drift, or the wrong endpoint answered) must
  // throw the same typed ApiError, never an unhandled TypeError and never a
  // silent `undefined` returned as if it were valid data.
  if (
    body === null ||
    typeof body !== "object" ||
    !("data" in body)
  ) {
    throw new ApiError({
      code: FALLBACK_ERROR_CODE,
      status: response.status,
      message: "Response body was not a valid data envelope.",
    });
  }

  return (body as DataEnvelope<T>).data;
}

export function createApiClient(config: ApiClientConfig = {}): PhraseApiClient {
  const resolved: Required<ApiClientConfig> = {
    baseUrl: config.baseUrl ?? DEFAULT_BASE_URL,
    // Bound to `globalThis`: the Fetch spec requires `fetch` to be invoked
    // with `this` set to `Window` (or the worker scope); storing the bare
    // function reference and calling it later as `config.fetchImpl(...)`
    // invokes it with `this === config`, which throws "TypeError: Failed to
    // execute 'fetch' on 'Window': Illegal invocation" before any request is
    // ever dispatched.
    fetchImpl: config.fetchImpl ?? fetch.bind(globalThis),
  };

  return {
    validatePhrase: (body) =>
      request<Schemas["_ValidateData"]>(
        "/phrases/validate",
        { method: "POST", body: JSON.stringify(body) },
        resolved,
      ),
    listMatches: (body) =>
      request<Schemas["_MatchesData"]>(
        "/phrases/matches",
        { method: "POST", body: JSON.stringify(body) },
        resolved,
      ),
    savePhrase: (body) =>
      request<Schemas["_PhraseOut"]>(
        "/phrases",
        { method: "POST", body: JSON.stringify(body) },
        resolved,
      ),
    listPhrases: (params) => {
      const query = new URLSearchParams();
      if (params?.limit !== undefined) query.set("limit", String(params.limit));
      if (params?.cursor !== undefined) query.set("cursor", params.cursor);
      const qs = query.toString();
      return request<Schemas["_PhraseListData"]>(
        `/phrases${qs ? `?${qs}` : ""}`,
        { method: "GET" },
        resolved,
      );
    },
  };
}

/** Browser-facing singleton — `NEXT_PUBLIC_API_URL`-backed, per D5. */
export const apiClient = createApiClient();

export { ApiError };
export type { ErrorCode };
