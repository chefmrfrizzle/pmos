# Architecture

PMOS is one configurable core with a Next.js public-safe interface, FastAPI service, and Python research package. SQLite is the default local datastore; SQLAlchemy keeps a migration path to PostgreSQL. Research adapters create immutable evidence snapshots and claims. Vertical products configure views and scoring rather than forking the graph.

Private raw files and the operational database live outside the repository through `PMOS_PRIVATE_ROOT` and `PMOS_DB_URL`. The public demo is static synthetic data and never connects to the private store.
