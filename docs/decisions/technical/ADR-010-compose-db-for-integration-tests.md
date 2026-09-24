---
id: ADR-010
title: Compose DB for integration tests instead of testcontainers
type: technical
---

# ADR-010: Compose DB for integration tests

Compose DB (`docker compose up -d db migrate`, throwaway `phrases_test`
database) for integration tests instead of testcontainers.
