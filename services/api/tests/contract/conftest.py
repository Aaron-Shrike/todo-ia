"""`app.main` builds `Settings()` (no default for `DATABASE_URL`) at IMPORT
time (design.md's fail-fast intent). Supplies one harmless value before any
contract test imports `app.main`, scoped to this directory only -- it can
never shadow `tests/integration/*`'s real `DATABASE_URL`.
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://contract:contract@localhost:5432/contract")
