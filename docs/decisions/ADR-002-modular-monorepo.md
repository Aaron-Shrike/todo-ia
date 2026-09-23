---
id: ADR-002
title: Modular monorepo with enforced import boundaries, not a folder-layered app
type: beyond-brief
---

# ADR-002: Modular monorepo with enforced import boundaries

**The brief asked for** a clean layered app (UI, business, data, AI).

**We decided** a monorepo of independently deployable services with modular
hexagonal modules and enforced import boundaries.

**Because** "layered" as a folder convention decays on contact with
deadlines; import-linter contracts make the boundary a build failure. The
embedding module can become a microservice by swapping one adapter — with
the honest caveat that vector *search* stays with the data.
