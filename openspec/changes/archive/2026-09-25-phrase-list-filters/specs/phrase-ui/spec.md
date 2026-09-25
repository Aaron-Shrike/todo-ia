# Delta for phrase-ui

## ADDED Requirements

### Requirement: Filter controls over the saved list

The saved-phrase list MUST offer three optional, combinable filter controls: a status select (`Todas` / `Única` / `Duplicado confirmado`, default `Todas` = no filter), a text input (`q`), and a minimum-score numeric input (`min_score`, `[0,1]`). The status and minimum-score controls MUST apply immediately on change and refetch the list (no separate "Aplicar" button). The text input MUST debounce: the list refetches only after the user stops typing for a few hundred milliseconds, not on every keystroke. Changing ANY filter (status, `q` after its debounce, or min-score) MUST reset pagination to page 1, reusing the existing `refresh()` pattern in `PhraseList.tsx`, and MUST send all currently active filter values together.

#### Scenario: Typing in the text filter debounces the request
- GIVEN the list is showing unfiltered results
- WHEN the user types several characters in the text filter within a short span
- THEN only one `GET /phrases?q=...` request is sent, after the user stops typing, not one request per keystroke

#### Scenario: Changing the status filter refetches immediately and resets pagination
- GIVEN the list has scrolled past page 1
- WHEN the user selects a status value
- THEN a `GET /phrases?status=...` request is sent immediately, pagination restarts at page 1, and no "Aplicar" action is needed

#### Scenario: Changing the minimum score refetches immediately and resets pagination
- GIVEN the list has scrolled past page 1
- WHEN the user changes the minimum-score input
- THEN a `GET /phrases?min_score=...` request is sent immediately and pagination restarts at page 1

#### Scenario: Active filters combine in one request
- GIVEN a status and a minimum score are both set
- WHEN the text filter's debounce elapses after the user also types a query
- THEN one request carries `status`, `q`, and `min_score` together

#### Scenario: Clearing a filter returns to the broader result set
- GIVEN a status filter is active
- WHEN the user resets it to `Todas`
- THEN the list refetches immediately without `status`, from page 1

### Requirement: Filtered counter and empty state

The `{loaded}/{total}` counter MUST reflect the ACTIVE filter set's `total`, not the unfiltered store size. When a filter combination matches zero phrases, the list MUST show a distinct empty-state message (not the "no phrases saved yet" message) and MUST offer a one-click action that clears all active filters and reloads the unfiltered list from page 1.

#### Scenario: Counter reflects the filtered total
- GIVEN a filter matching 20 of 20004 stored phrases
- WHEN the list renders
- THEN the counter reads "0/20" before any page loads and grows toward "20/20" as pages load, never referencing 20004

#### Scenario: Empty state for a filter with no matches
- GIVEN a filter combination that matches no phrases
- WHEN the list renders
- THEN a "no results for these filters" message is shown, distinct from the empty-store message, with a clear-filters action

#### Scenario: Clear-filters action restores the unfiltered list
- GIVEN the filtered empty state is shown
- WHEN the clear-filters action is pressed
- THEN all filter controls reset, the list refetches unfiltered from page 1, and the ordinary empty/loaded state applies

### Requirement: Filter copy keys

New user-visible strings introduced by the filter controls MUST be added to the existing single copy module (see "Spanish copy table"), in neutral Spanish: a status select label, its three option labels (`Todas`, `Única`, `Duplicado confirmado`), a text-filter label/placeholder, a minimum-score label, the filtered empty-state message, and the clear-filters action label.

#### Scenario: Filter copy comes from the copy module
- GIVEN the frontend source
- WHEN searched for the filter controls' visible strings
- THEN none are hardcoded outside the copy module
