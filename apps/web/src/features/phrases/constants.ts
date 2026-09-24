/**
 * Page size this UI requests for the duplicate alert's match list, on both
 * the initiating validate/save call and every subsequent
 * `POST /phrases/matches` page. Independent of the backend's own
 * `MATCHES_PAGE_SIZE` default (which stays whatever an operator configures
 * for clients that don't override `limit`) — this UI always overrides it.
 */
export const MATCHES_PAGE_SIZE = 10;
