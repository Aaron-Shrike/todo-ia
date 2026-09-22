"""Smoke test proving the backend test runner (pytest) is wired and can import the app package.

This is intentionally the first RED of Unit 0 (scaffold monorepo): at the moment this file is
written, `services/api/pyproject.toml` and `services/api/src/app/__init__.py` do not exist yet, so
both `pytest` collection and the `import app` statement fail. Task 0.2 makes it GREEN.
"""


def test_app_package_is_importable() -> None:
    import app

    assert app.__name__ == "app"
