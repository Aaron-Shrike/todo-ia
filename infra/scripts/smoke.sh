#!/usr/bin/env bash
# Unit 14 (tasks.md 14.2): end-to-end smoke test against the REAL running
# compose stack (`docker compose up -d --build` first). Exercises the three
# core phrase endpoints in order: validate (no side effect) -> save
# (persists) -> list (the saved phrase must appear). Fails fast (`set -e`)
# on the first unexpected status code or missing field, printing the
# response body so a reviewer can see exactly what went wrong.
#
# No jq/python dependency on purpose -- curl + POSIX text tools only, so
# this runs on any reviewer machine with curl installed (Compose/Docker are
# already mandatory per design.md).
set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"
TEXT="smoke test phrase $(date +%s)"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

# `curl -w '\n%{http_code}'` appends the status code as its own trailing
# line, so the body/status split below is a plain "last line vs the rest".
split_status() {
  local body="$1"
  printf '%s' "${body##*$'\n'}"
}

split_body() {
  local body="$1"
  printf '%s' "${body%$'\n'*}"
}

echo "==> POST ${API_URL}/phrases/validate"
validate_raw=$(curl -sS -w '\n%{http_code}' -X POST "${API_URL}/phrases/validate" \
  -H 'Content-Type: application/json' \
  -d "{\"text\": \"${TEXT}\"}")
validate_status=$(split_status "$validate_raw")
validate_body=$(split_body "$validate_raw")
[ "$validate_status" = "200" ] || fail "validate returned ${validate_status}: ${validate_body}"
echo "$validate_body" | grep -q '"is_duplicate"' || fail "validate body missing \"is_duplicate\": ${validate_body}"
echo "OK: validate 200, is_duplicate present"

echo "==> POST ${API_URL}/phrases"
save_raw=$(curl -sS -w '\n%{http_code}' -X POST "${API_URL}/phrases" \
  -H 'Content-Type: application/json' \
  -d "{\"text\": \"${TEXT}\"}")
save_status=$(split_status "$save_raw")
save_body=$(split_body "$save_raw")
[ "$save_status" = "201" ] || fail "save returned ${save_status}: ${save_body}"
echo "$save_body" | grep -q "\"text\":\"${TEXT}\"" || fail "save body missing the saved text: ${save_body}"
echo "OK: save 201, saved phrase echoed back"

echo "==> GET ${API_URL}/phrases"
list_raw=$(curl -sS -w '\n%{http_code}' "${API_URL}/phrases")
list_status=$(split_status "$list_raw")
list_body=$(split_body "$list_raw")
[ "$list_status" = "200" ] || fail "list returned ${list_status}: ${list_body}"
echo "$list_body" | grep -q "${TEXT}" || fail "saved phrase not present in the list: ${list_body}"
echo "OK: list 200, saved phrase present"

echo "Smoke test passed: validate -> save -> list all succeeded end to end."
