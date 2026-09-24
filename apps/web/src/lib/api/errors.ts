// Error model shared by `client.ts` and, from Unit 11 onward, the phrase
// feature's error → Spanish-copy mapping (`errorCopy`, design.md "Spanish
// copy ownership").
//
// The generated `types/api.ts` types `ErrorDetail.code` as a plain `string`
// (openapi-typescript has no way to know the FastAPI backend only ever emits
// one of a fixed set — the OpenAPI schema itself does not declare an enum
// for it). This union is therefore hand-maintained against the api-contract
// spec's error registry table, not derived from the generated file.
export type ErrorCode =
  | "INVALID_CURSOR"
  | "NOT_FOUND"
  | "PHRASE_NOT_FOUND"
  | "METHOD_NOT_ALLOWED"
  | "DUPLICATE_CONFIRMATION_REQUIRED"
  | "PAYLOAD_TOO_LARGE"
  | "VALIDATION_ERROR"
  | "INTERNAL_ERROR"
  | "EMBEDDING_UNAVAILABLE"
  | "EMBEDDING_TIMEOUT"
  | "NOT_READY"
  // Client-side only: fetch itself rejected (no HTTP response arrived at
  // all), so no server-issued `code` exists to report. phrase-ui spec's
  // "Network failure" scenario ("fetch rejects" → network copy) is the
  // scenario this exists to satisfy.
  | "NETWORK_ERROR";

export interface ApiErrorParams {
  code: ErrorCode;
  status: number;
  message: string;
  details?: Record<string, unknown> | null;
}

/**
 * Normalized shape every failure from the API client surfaces as, whether it
 * came from a server error envelope (`{"error":{code,message,details?}}`) or
 * from a network failure the browser never turned into a response. `message`
 * stays the API's short English developer text (design.md: "the UI owns
 * display copy") — callers map `code` to Spanish copy themselves.
 */
export class ApiError extends Error {
  readonly code: ErrorCode;
  readonly status: number;
  readonly details?: Record<string, unknown> | null;

  constructor({ code, status, message, details }: ApiErrorParams) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}
