# Public/private boundary

The public repository contains code, schemas, generic configuration, documentation, tests, public universe definitions, and synthetic demonstrations only. Private datasets, contacts, notes, introductions, outreach, scores, credentials, evidence, and databases live in a sibling private directory and must never enter Git, GitHub, Vercel, fixtures, screenshots, documentation, browser bundles, or public APIs.

Before every commit or deployment run `make public-check`. A failure is a release blocker, never something to bypass.
