-- Runs once, automatically, on first `db` container start (mounted into
-- /docker-entrypoint-initdb.d/ by docker-compose.yml). Creates the throwaway
-- database used ONLY by the `integration`-marked pytest suite
-- (tests/integration/*), separate from POSTGRES_DB so integration test runs
-- never touch data used by a manual `docker compose up` session.
CREATE DATABASE phrases_test;
