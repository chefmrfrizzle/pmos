# Architecture

PMOS is one configurable core with a Next.js public-safe interface, FastAPI service, and Python research package. SQLite is the default local datastore; SQLAlchemy keeps a migration path to PostgreSQL. Research adapters create immutable evidence snapshots and claims. Vertical products configure views and scoring rather than forking the graph.

Private raw files and the operational database live outside the repository through `PMOS_PRIVATE_ROOT` and `PMOS_DB_URL`. The public demo is static synthetic data and never connects to the private store.

Private API authentication is provider-neutral OIDC at the resource-server boundary. Access tokens are validated against a configured same-issuer JWKS and fixed audience. Authorization combines a PMOS role, explicit action permission, allowed institutional universe, exact deployment tenant, and explicit business purpose; missing claims deny access. Local-token mode exists only for loopback development. Private reads generate tamper-evident audit events. The public web deployment has no route or environment configuration for this API.

Each private deployment is single-tenant. `PMOS_TENANT_ID` identifies the institution owning that service and datastore; the OIDC token must carry the same tenant claim. Every institutional request declares `X-PMOS-Purpose`, and the token must grant that purpose. Case-specific access also matches the active purpose to `DiligenceCase.permitted_use`. Multi-tenant operation requires separate datastores/services or a future row-level-security design with separate assurance; it must not be approximated by sharing this SQLite database.

Authenticated private routes expose case/check inspection, evidence attachment, and adjudication. Researchers may attach evidence and propose completion; reviewers/counsel/admin roles with `checks:approve` may approve. Object scope is enforced through tenant, purpose, the case entity’s universe, and action permission. Every access event records tenant and purpose in the hash-chained audit ledger.
