---
id: ADR-009
title: Browser calls the API directly, no BFF proxy
type: technical
---

# ADR-009: Browser calls the API directly, no BFF proxy

Browser→API direct calls, Server-Component first paint (`force-dynamic`,
browser-side refetch after a save), no BFF proxy; CORS (methods `GET,
POST, OPTIONS`, `Content-Type`, no credentials) as the accepted cost.
