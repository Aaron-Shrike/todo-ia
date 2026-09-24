# Phrase UI Specification

Capability: `phrase-ui` (new). Next.js + TypeScript frontend. Code, identifiers and tests are English; user-visible copy is neutral Spanish, defined in the copy table below. The UI owns display copy; it maps API error `code`s to copy and MUST NOT display the API `message` verbatim.

## ADDED Requirements

### Requirement: Explicit staged state machine

The phrase form MUST be driven by an explicit state machine with states `idle | validating | revalidating | duplicate | ok | saving | error`.

| From | Event | To |
| --- | --- | --- |
| idle | Validar pressed (valid text) | validating |
| validating | validate 200, `is_duplicate` false | ok |
| validating | validate 200, `is_duplicate` true | duplicate |
| validating / revalidating / saving | request fails | error |
| idle | Guardar pressed | validating, then revalidating (two real calls: validate, then the authoritative save) |
| ok | Guardar pressed | revalidating (one call: the authoritative save) |
| duplicate | Confirmar pressed | saving (with `confirm_duplicate: true`) |
| duplicate | Cancelar pressed | idle (text kept, nothing saved) |
| revalidating | 201 | idle (text cleared, "Frase guardada." announced; the list refresh runs in the background, see "Saved phrase list") |
| revalidating | 409 | duplicate (fresh data from the 409 payload) |
| saving | 201 | idle (same completion as above) |
| saving | 409 | duplicate (defensive: the server does not answer 409 to `confirm_duplicate: true` today, but the UI handles it deterministically) |
| any | text edited | idle |
| error | Reintentar / edit | idle (text kept) |

`saving` exists only while the confirming `POST /phrases` is in flight; there is no stage after the 201, so no label ever narrates work that already happened. A failure of the list refresh after a 201 is NOT a save failure and never enters `error` (see "Saved phrase list with status badge").

Invalid transitions (e.g. Confirmar while idle) MUST be impossible or ignored.

#### Scenario: Validate unique
- GIVEN state idle with text "Regar plantas" and the API returning `is_duplicate: false`
- WHEN Validar is pressed
- THEN the state passes through `validating` and ends in `ok`

#### Scenario: Unique but similar to an existing phrase
- GIVEN state idle with text and the API returns `is_duplicate: false` with a non-null `most_similar` and `score`
- WHEN Validar is pressed
- THEN the state ends in `ok` and the UI shows the closest match's text and score alongside "La frase es única. Puedes guardarla."

#### Scenario: Unique with no similar phrase
- GIVEN the API returns `is_duplicate: false` with `most_similar: null`
- WHEN Validar is pressed
- THEN only "La frase es única. Puedes guardarla." is shown, with no closest-match line

#### Scenario: Validate duplicate
- GIVEN the API returns `is_duplicate: true`
- WHEN Validar is pressed
- THEN the state ends in `duplicate` and the alert is shown

#### Scenario: Invalid transition ignored
- GIVEN state idle
- WHEN a confirm event is dispatched
- THEN the state is unchanged and no request is made

### Requirement: Staged progress narration

While a request is in flight the UI MUST display a progress message for the current stage: `validating` shows "Validando..." (the validate call); `revalidating` shows "Revalidando..." (the authoritative `POST /phrases`, which the server re-validates before inserting); `saving` shows "Guardando..." (the `POST /phrases` with `confirm_duplicate: true` sent from the duplicate alert). When Guardar is pressed without a prior successful validation, the UI MUST run the visible sequence Validando... -> Revalidando... (validation call, then the authoritative save call); the stages MUST NOT be collapsed into one generic spinner and no label may be shown after the 201 has arrived. The progress MUST be announced accessibly (`role="status"`, `aria-live="polite"`).

#### Scenario: Save directly, unique
- GIVEN idle state with unvalidated text and a unique result
- WHEN Guardar is pressed
- THEN "Validando..." is shown, then "Revalidando...", and after the 201 the phrase appears in the list with "Frase guardada." announced (no "Guardando..." is shown)

#### Scenario: Save after validating
- GIVEN state `ok`
- WHEN Guardar is pressed
- THEN "Revalidando..." is shown (the server still re-validates) and the phrase is saved on 201, with no "Validando..." and no "Guardando..." stage

#### Scenario: Save directly, duplicate
- GIVEN idle state and the validation reveals a duplicate
- WHEN Guardar is pressed
- THEN the flow stops in `duplicate` after "Validando..." and nothing is saved

#### Scenario: Live region
- GIVEN any in-flight stage
- WHEN the DOM is inspected
- THEN the progress element has `role="status"` and `aria-live="polite"`

### Requirement: Duplicate alert

In state `duplicate` the UI MUST show an alert with: the message "Posible duplicado", the most similar phrase text and its score (shown as a whole percentage FLOORED from the 4-decimal score, computed on integer basis points to avoid float error, e.g. 0.9312 shows "93%", 0.9950 and 0.9999 show "99%", and "100%" appears only for an exact 1.0), a `{loaded}/{total}` counter (e.g. "10/46"), the list of matches (see infinite scroll), and the actions Confirmar ("Guardar de todos modos") and Cancelar. The alert MUST use `role="alertdialog"` (or `role="alert"`) and be keyboard operable.

#### Scenario: Alert content
- GIVEN validation returned most_similar "Comprar leche" at 0.9312
- WHEN the alert renders
- THEN it shows "Posible duplicado", "Comprar leche" and "93%", plus both action buttons

#### Scenario: Percentage never overstates
- GIVEN scores 0.9950, 0.9999, 0.29 and 1.0
- WHEN each is rendered as a percentage
- THEN they show "99%", "99%", "29%" and "100%" respectively

#### Scenario: Confirm
- GIVEN the alert is shown
- WHEN "Guardar de todos modos" is pressed
- THEN a `POST /phrases` with `confirm_duplicate: true` is sent, "Guardando..." is shown, and on 201 the phrase appears in the list with the `Duplicado confirmado` badge

#### Scenario: Cancel
- GIVEN the alert is shown
- WHEN Cancelar is pressed
- THEN no save request is sent, the alert closes, the text remains, and the state is `idle`

#### Scenario: 409 during save
- GIVEN the state is `revalidating` (from a direct save or from `ok`) and the server answers 409
- WHEN the response arrives
- THEN the state becomes `duplicate` populated from the 409 `details` and "Guardando..." was never shown

#### Scenario: 409 while confirming (defensive)
- GIVEN the state is `saving` from Confirmar and the server answers 409
- WHEN the response arrives
- THEN the state becomes `duplicate` populated from the 409 `details`

### Requirement: Infinite scroll over matches

The alert's match list MUST show the first page returned by validate (or 409 `details`) and MUST load subsequent pages automatically as the user scrolls to the end of the list (sentinel/IntersectionObserver), by calling `POST /phrases/matches` with the same text, `limit: 10` and the last `next_cursor`, appending results in order — the UI requests page size 10 explicitly on both the initiating validate/save call and every subsequent page (`MATCHES_PAGE_SIZE`'s own configured default, e.g. 50, remains the server-side bound for any client that does not override `limit`; this UI always does). It MUST show a `{loaded}/{total}` counter next to the match list (e.g. "10/46", growing to "20/46" as more pages load), reading `total` from the same validate/matches/409 response. It MUST stop when `has_more` is false and MUST let the user reach every match. While loading a page it MUST show "Cargando más coincidencias..."; on failure it MUST show an inline error with a retry action and keep already loaded items. It MUST NOT request a page while one is in flight and MUST NOT duplicate items.

#### Scenario: Load next page on scroll
- GIVEN page 1 (10 items, `total` 46) with `has_more` true
- WHEN the end sentinel becomes visible
- THEN exactly one `POST /phrases/matches` with `cursor = next_cursor` and `limit: 10` is sent, its items are appended after the existing 10, and the counter reads "20/46"

#### Scenario: Invalid cursor restarts validation
- GIVEN the next-page request returns 400 `INVALID_CURSOR`
- WHEN handled
- THEN the UI discards the loaded matches and re-runs validation for the current text instead of retrying the same cursor

#### Scenario: Reach the end
- GIVEN 120 matches
- WHEN the user scrolls through all pages
- THEN 120 items are shown, no further request is sent after `has_more` is false, and no sentinel remains

#### Scenario: No concurrent page requests
- GIVEN a page request is in flight
- WHEN the sentinel intersects again
- THEN no second request is sent

#### Scenario: Page load failure
- GIVEN the next-page request fails
- WHEN the failure arrives
- THEN loaded items remain, "No se pudieron cargar más coincidencias." and a "Reintentar" action appear, and retry re-requests the same cursor

#### Scenario: Deduplicate on overlap
- GIVEN a later page repeats an id already displayed (phrase saved between pages)
- WHEN the page is appended
- THEN the repeated id is not shown twice

#### Scenario: Single page
- GIVEN 3 matches with `has_more` false
- WHEN the alert renders
- THEN no loading sentinel or "Cargando más coincidencias..." is shown

### Requirement: Reset on text edit

Editing the text MUST reset the machine to `idle`, discard any validation result, close the duplicate alert, and cancel or ignore any in-flight response for the previous text. A stale result MUST never be reusable.

#### Scenario: Edit after validating
- GIVEN state `ok`
- WHEN the user changes the text
- THEN state is `idle` and Guardar re-runs the full staged flow

#### Scenario: Edit while validating
- GIVEN state `validating`
- WHEN text is edited and the old response then arrives
- THEN the old response is ignored and the state stays `idle`

#### Scenario: Edit during duplicate
- GIVEN state `duplicate`
- WHEN text is edited
- THEN the alert closes and no confirmation is possible for the old text

### Requirement: Controls disabled in flight

While the state is `validating`, `revalidating` or `saving`, the text input, Validar and Guardar buttons MUST be disabled (and the alert's Confirmar and Cancelar disabled while `saving`) so no duplicate submissions occur. Controls MUST be re-enabled on `idle`, `ok`, `duplicate` and `error`.

#### Scenario: Double click
- GIVEN state `validating`
- WHEN Validar is clicked again
- THEN no second request is sent

#### Scenario: Re-enabled after error
- GIVEN state `error`
- WHEN it renders
- THEN input and buttons are enabled

### Requirement: Client-side input checks

Before any request the UI MUST prevent empty/whitespace-only submissions (Validar and Guardar disabled, or a message shown) and MUST show a character counter against the limit with the message "La frase no puede superar 280 caracteres." when exceeded; no request is sent in that case. The counter counts Unicode code points of the trimmed text (`[...text.trim()].length`, not UTF-16 units, so an emoji counts once), and the limit comes from `NEXT_PUBLIC_PHRASE_MAX_LENGTH` (build-time, default 280, kept equal to the backend `PHRASE_MAX_LENGTH`). The client count is an approximation of the server rule (which also strips control characters); the server remains authoritative.

#### Scenario: Empty text
- GIVEN empty or whitespace-only text
- WHEN the form renders
- THEN Validar and Guardar are disabled

#### Scenario: Over length
- GIVEN 281 characters
- WHEN Validar is pressed (or attempted)
- THEN the message "La frase no puede superar 280 caracteres." is shown and no request is made

#### Scenario: Counter counts code points
- GIVEN 280 emoji (each one code point, two UTF-16 units)
- WHEN the form renders
- THEN the counter shows 280/280 and no over-length message appears

#### Scenario: Server-enforced limit
- GIVEN the server returns 422 `VALIDATION_ERROR` with `reason: too_long`
- WHEN the response arrives
- THEN the same over-length message is shown

### Requirement: Error handling

The UI MUST map API error codes to Spanish copy and enter `error`; it MUST never show a success indication for a failed save and MUST never claim a phrase was saved unless a 201 was received. Network failures (no response) map to the network copy. The user MUST be able to retry.

#### Scenario: Model unavailable
- GIVEN the API returns 503 `EMBEDDING_UNAVAILABLE`
- WHEN handled
- THEN the state is `error` with "El servicio de validación no está disponible. Inténtalo de nuevo." and the list is unchanged

#### Scenario: Timeout
- GIVEN the API returns 504
- WHEN handled
- THEN the message "La validación tardó demasiado. Inténtalo de nuevo." is shown

#### Scenario: Network failure
- GIVEN fetch rejects
- WHEN handled
- THEN "No se pudo conectar con el servidor." is shown

#### Scenario: Unknown code
- GIVEN an unmapped error code
- WHEN handled
- THEN the generic message "Ocurrió un error inesperado. Inténtalo de nuevo." is shown

#### Scenario: Retry
- GIVEN state `error`
- WHEN the user presses Reintentar
- THEN the state returns to `idle` with the text preserved

### Requirement: Saved phrase list with status badge

The UI MUST render saved phrases (from `GET /phrases`, newest first) with a status badge per item: `unique` shows "Única", `duplicate_confirmed` shows "Duplicado confirmado". When a score exists it MUST be displayed as a percentage (e.g. "Similitud: 93%"). The list MUST refresh after a successful save (a browser-side `GET /phrases`, not a page reload), and MUST show an empty state and a loading state. If that refresh fails after a 201, the phrase IS saved: the UI keeps the machine in `idle`, keeps "Frase guardada." and shows the non-blocking list error ("No se pudieron cargar las frases." with Reintentar); it MUST NOT enter `error` for the save.

#### Scenario: Badge unique
- GIVEN an item with status `unique` and score null
- WHEN rendered
- THEN badge "Única" is shown and no similarity text

#### Scenario: Badge duplicate confirmed
- GIVEN an item with status `duplicate_confirmed` and score 0.9312
- WHEN rendered
- THEN badge "Duplicado confirmado" and "Similitud: 93%" are shown

#### Scenario: Empty list
- GIVEN `items: []`
- WHEN rendered
- THEN "Aún no hay frases guardadas." is shown

#### Scenario: Refresh after save
- GIVEN a successful 201
- WHEN the save completes
- THEN the new phrase appears at the top of the list with its badge

#### Scenario: Refresh fails after a successful save
- GIVEN a 201 was received and the follow-up `GET /phrases` fails
- WHEN the failure arrives
- THEN the machine is `idle`, "Frase guardada." stays announced, "No se pudieron cargar las frases." with Reintentar is shown in the list area, and no save error is shown

#### Scenario: List load failure
- GIVEN `GET /phrases` fails
- WHEN handled
- THEN "No se pudieron cargar las frases." and a Reintentar action are shown

### Requirement: Infinite scroll over the saved list

The saved-phrase list loads one page at a time (`GET /phrases`'s `limit`/`cursor`, server default page size 10) and MUST load subsequent pages automatically as the user scrolls to the end of the list (sentinel/IntersectionObserver), appending results in order — same mechanism as "Infinite scroll over matches", applied to this list. It MUST show a `{loaded}/{total}` counter next to the list (e.g. "10/60", growing to "20/60" as more pages load) and MUST stop requesting once `has_more` is false. While loading a page it MUST show "Cargando más frases..."; on failure it MUST show an inline error with a retry action and keep already loaded items. It MUST NOT request a page while one is in flight and MUST NOT duplicate items. A `refresh()` (after a save, or Reintentar on a full load failure) always restarts from page 1, discarding any pages loaded via scroll.

#### Scenario: Load next page on scroll
- GIVEN page 1 (10 items, `total` 60) with `has_more` true
- WHEN the end sentinel becomes visible
- THEN exactly one `GET /phrases?cursor=<next_cursor>` is sent, its items are appended after the existing 10, and the counter reads "20/60"

#### Scenario: Reach the end
- GIVEN 25 stored phrases
- WHEN the user scrolls through all pages
- THEN 25 items are shown, the counter reads "25/25", no further request is sent after `has_more` is false, and no sentinel remains

#### Scenario: No concurrent page requests
- GIVEN a page request is in flight
- WHEN the sentinel intersects again
- THEN no second request is sent

#### Scenario: Page load failure
- GIVEN the next-page request fails
- WHEN the failure arrives
- THEN loaded items remain, "No se pudieron cargar más frases." and a "Reintentar" action appear

#### Scenario: Deduplicate on overlap
- GIVEN a later page repeats an id already displayed (a phrase saved between pages)
- WHEN the page is appended
- THEN the repeated id is not shown twice

### Requirement: Spanish copy table

All user-visible strings MUST come from a single copy module using exactly these values (neutral Spanish, no regional slang):

| Key | Spanish copy |
| --- | --- |
| `title` | Lista de frases |
| `input.label` | Nueva frase |
| `input.placeholder` | Escribe una frase |
| `button.validate` | Validar |
| `button.save` | Guardar |
| `button.confirm` | Guardar de todos modos |
| `button.cancel` | Cancelar |
| `button.retry` | Reintentar |
| `progress.validating` | Validando... |
| `progress.revalidating` | Revalidando... |
| `progress.saving` | Guardando... |
| `validation.ok` | La frase es única. Puedes guardarla. |
| `validation.closestMatch` | Aunque es única, se parece a |
| `duplicate.title` | Posible duplicado |
| `duplicate.mostSimilar` | Frase más similar |
| `duplicate.score` | Similitud: {percent}% |
| `duplicate.matchesTitle` | Coincidencias |
| `duplicate.matchesCounter` | {loaded}/{total} |
| `duplicate.loadingMore` | Cargando más coincidencias... |
| `duplicate.loadMoreError` | No se pudieron cargar más coincidencias. |
| `badge.unique` | Única |
| `badge.duplicate_confirmed` | Duplicado confirmado |
| `list.empty` | Aún no hay frases guardadas. |
| `list.loadError` | No se pudieron cargar las frases. |
| `list.counter` | {loaded}/{total} |
| `list.loadingMore` | Cargando más frases... |
| `list.loadMoreError` | No se pudieron cargar más frases. |
| `saved.success` | Frase guardada. |
| `error.tooLong` | La frase no puede superar 280 caracteres. |
| `error.empty` | Escribe una frase antes de continuar. |
| `error.embeddingUnavailable` | El servicio de validación no está disponible. Inténtalo de nuevo. |
| `error.timeout` | La validación tardó demasiado. Inténtalo de nuevo. |
| `error.network` | No se pudo conectar con el servidor. |
| `error.generic` | Ocurrió un error inesperado. Inténtalo de nuevo. |
| `error.invalidCursor` | La lista de coincidencias cambió. Vuelve a validar. |

`error.invalidCursor` (API `INVALID_CURSOR`) is a fallback string only, present so the error-code map is exhaustive; the UI still silently restarts validation on 400 `INVALID_CURSOR` (see "Invalid cursor restarts validation") and does not normally display it.

The limit in `error.tooLong` MUST reflect `NEXT_PUBLIC_PHRASE_MAX_LENGTH` when it differs from the default 280. Every backend error code has a mapped copy key so the map is exhaustive: `PAYLOAD_TOO_LARGE` maps to `error.generic`.

#### Scenario: Single source of copy
- GIVEN the frontend source
- WHEN searched for user-visible string literals outside the copy module and tests
- THEN none exist

#### Scenario: Copy values
- GIVEN the copy module
- WHEN its exported values are compared with the table above
- THEN they match exactly

#### Scenario: Success message
- GIVEN a 201 response
- WHEN the save completes
- THEN "Frase guardada." is announced in a status region

#### Scenario: English code, Spanish UI
- GIVEN the frontend
- WHEN inspected
- THEN identifiers, comments, tests and API field names are English and only rendered copy is Spanish
