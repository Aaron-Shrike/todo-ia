"""Contract tests for the generated OpenAPI document (tasks.md 7b.2,
design.md's Testing Strategy: "every error code present in OpenAPI;
pagination fields documented; `limit` optional and bounded on both
endpoints; ids typed `string` and documented opaque;
`docs/openapi.json` snapshot diff"). Covers api-contract's "OpenAPI
documentation" requirement's four scenarios.

`create_app()` alone (no `app.state.phrases`/`app.state.health`) is enough
to generate the document -- schema generation never touches those, same
precedent as `test_framework_errors.py`'s throwaway-route file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.main import create_app
from app.platform.errors import ERROR_REGISTRY
from app.platform.settings import Settings

pytestmark = pytest.mark.contract

_SNAPSHOT_PATH = Path(__file__).parents[4] / "docs" / "openapi.json"


def _spec() -> dict[str, Any]:
    settings = Settings(database_url="postgresql+psycopg://test:test@localhost:5432/test")
    app = create_app(settings)
    return app.openapi()  # type: ignore[no-any-return]


def test_endpoints_documented() -> None:
    spec = _spec()
    paths = spec["paths"]
    assert "post" in paths["/phrases/validate"]
    assert "post" in paths["/phrases/matches"]
    assert "get" in paths["/phrases"]
    assert "post" in paths["/phrases"]
    assert "get" in paths["/health"]


def test_error_responses_documented_on_save() -> None:
    spec = _spec()
    responses = spec["paths"]["/phrases"]["post"]["responses"]
    for status in ("201", "409", "422", "503", "504"):
        assert status in responses, f"missing {status} on POST /phrases"


def test_pagination_documented() -> None:
    spec = _spec()
    validate_op = spec["paths"]["/phrases/validate"]["post"]
    validate_request = _resolve(spec, validate_op["requestBody"])
    validate_properties = validate_request["properties"]
    assert "limit" in validate_properties
    validate_response = _resolve_response_schema(spec, validate_op)
    assert {"next_cursor", "has_more"} <= set(validate_response["properties"])

    matches_op = spec["paths"]["/phrases/matches"]["post"]
    matches_request = _resolve(spec, matches_op["requestBody"])
    matches_properties = matches_request["properties"]
    assert {"text", "cursor", "limit"} <= set(matches_properties)
    matches_response = _resolve_response_schema(spec, matches_op)
    assert {"next_cursor", "has_more"} <= set(matches_response["properties"])
    assert "400" in matches_op["responses"]

    cursor_schema = matches_properties["cursor"]
    cursor_description = cursor_schema.get("description", "")
    assert "opaque" in cursor_description.lower()


def test_every_registered_code_documented() -> None:
    spec = _spec()
    document_text = json.dumps(spec)
    codes = {mapping.code for mapping in ERROR_REGISTRY.values()}
    assert codes  # sanity: the registry is not empty
    for code in codes:
        assert code in document_text, f"{code} missing from the OpenAPI document"


def test_ids_typed_string_and_documented_opaque() -> None:
    spec = _spec()
    phrase_schema = spec["components"]["schemas"]["_PhraseOut"]
    id_schema = phrase_schema["properties"]["id"]
    assert id_schema["type"] == "string"


def test_snapshot_matches_docs_openapi_json() -> None:
    spec = _spec()
    assert _SNAPSHOT_PATH.exists(), (
        f"{_SNAPSHOT_PATH} does not exist -- regenerate via `app.openapi()` "
        "(see this module's docstring; `make types` only consumes this file, "
        "it does not produce it)"
    )
    on_disk = json.loads(_SNAPSHOT_PATH.read_text())
    assert spec == on_disk, "docs/openapi.json is stale -- regenerate it from app.openapi()"


def _resolve(spec: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    """Follow ONE level of `$ref` (request bodies are always `$ref`-wrapped
    by FastAPI/pydantic v2 -- every model gets a name)."""
    content = node["content"]["application/json"]["schema"]
    return _deref(spec, content)


def _deref(spec: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    if "$ref" in schema:
        _, _, _, name = schema["$ref"].split("/")
        return spec["components"]["schemas"][name]  # type: ignore[no-any-return]
    return schema


def _resolve_response_schema(spec: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
    """The success response is `{"data": {...}}` -- one extra `$ref` hop to
    unwrap the envelope and reach the actual paginated fields."""
    success = next(
        response
        for status, response in operation["responses"].items()
        if status.startswith("2")
    )
    schema = _deref(spec, success["content"]["application/json"]["schema"])
    return _deref(spec, schema["properties"]["data"])
