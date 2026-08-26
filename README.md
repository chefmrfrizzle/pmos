# PMOS — Private Markets Operating System

PMOS is a local-first counterparty intelligence and private-asset operating system for mapping the institutions that control, advise, finance, insure, custody, transact, or introduce global private capital and high-value assets.

It is designed to answer five questions for every counterparty:

1. **Who are they?** — verified entity identity, mandate, geography, decision-makers and public sources.
2. **What do they control?** — capital, assets, relationships, transaction authority or distribution.
3. **Who are they connected to?** — co-investors, advisers, banks, fiduciaries, boards, clients and institutional relationships where publicly evidenced.
4. **How can PMOS be useful to them?** — an explicit product/service wedge tied to the counterparty's role.
5. **What should happen next?** — prioritized research, warm-intro path, outreach, pilot or archive.

## What PMOS covers

The default universe registry includes:

- Sovereign wealth funds and state investment companies
- Canadian and global pensions / superannuation
- Single-family offices and family-controlled investment companies
- Family-office and UHNW peer networks
- Private banks and UHNW / Global Family Office divisions
- Multi-family offices
- Trust, estate and fiduciary firms
- Foundations and endowments
- Auction houses and private-sales platforms
- Art fairs and collector networks
- Major galleries and dealers
- Insurance and reinsurance
- Brokers, custodians, fund administrators and asset servicers
- Professional private-client gatekeepers

The public repository contains **no private contact database**. Your local/private seed data belongs in `data/private/`, which is gitignored.

---

## Design principles

### No LLM credits by default

The research engine uses deterministic Python and public sources. It does **not** call OpenAI, Anthropic, Gemini or any other LLM unless you explicitly add an adapter later.

Default adapters:

- Official websites supplied in the universe registry
- `robots.txt`-aware page retrieval
- GLEIF LEI API for legal-entity identity where available
- SEC EDGAR public datasets for US registrants where relevant
- Wikidata SPARQL for public entity metadata and relationship candidates
- RSS / sitemap discovery when a site exposes them
- Local spreadsheet/CSV import

### Evidence before inference

Every material claim can carry:

- source URL
- source type
- retrieved timestamp
- content hash
- confidence
- verification state

PMOS never invents email addresses, beneficial owners, AUM or relationships.

### Public/private separation

`pmos-public` is designed to be safe to push to a public GitHub repo.

Do **not** commit:

- raw investor/contact lists
- personal outreach notes
- relationship intelligence
- non-public UBO information
- private client data
- credentials / API keys
- exports containing email/phone data unless you have a lawful basis to publish them

Those belong in the separate `pmos-private-seed` package or another private repository.

---

## Quick start on macOS

Requirements: macOS, Python 3.11+, Node 20+, Git.

```bash
unzip PMOS-public.zip
cd pmos-public
chmod +x scripts/bootstrap_mac.sh
./scripts/bootstrap_mac.sh
```

Then start both services:

```bash
make dev
```

Open:

- Web UI: http://localhost:3000
- API health: http://localhost:8000/health

Private entity routes are absent by default (`PMOS_AUTH_MODE=disabled`). Local development uses `PMOS_AUTH_MODE=local` plus a random `PMOS_DEV_API_TOKEN` of at least 24 characters and accepts loopback clients only.

Institutional deployments use `PMOS_AUTH_MODE=oidc` with `PMOS_OIDC_ISSUER`, `PMOS_OIDC_AUDIENCE`, and a same-issuer HTTPS `PMOS_OIDC_JWKS_URL`. The API requires short-lived signed RS256 access tokens with MFA, recent `auth_time`, unique `jti`, an approved PMOS role, action permissions, tenant/purpose binding, and universe-level object scope. Emergency revocation uses hashed token identifiers in private deployment configuration. Browser session/CSRF integration and enterprise IdP session revocation remain deployment-specific; the public Vercel demo contains no private API.

### Import your private databases

Keep the private seed ZIP outside the public repo, then:

```bash
unzip PMOS-private-seed.zip -d ~/PMOS-private
./.venv/bin/python scripts/import_private.py \
  --input-dir ~/PMOS-private/data/private/imports
```

Imported records go to the configured `PMOS_PRIVATE_ROOT` (by default `~/.local/share/pmos`) outside the public repository.

---

## Research workflow

Seed the global universe:

```bash
make seed
```

Run bounded official-domain identity research for public-registry institutions. Supported assertions receive source-document and exact-passage links; this command does not promote whole entities or research private imports:

```bash
make research
```

Run only one universe:

```bash
./.venv/bin/python scripts/research_universe.py --universe sovereign_wealth
./.venv/bin/python scripts/research_universe.py --universe private_banks
./.venv/bin/python scripts/research_universe.py --universe insurance
```

Broad direct exports are disabled. Request a single-case dossier through the authenticated private API, obtain independent `EXPORTER`/`ADMIN` approval after a passing control-assurance run, then execute the approved request locally on encrypted private storage:

```bash
./.venv/bin/python scripts/execute_approved_export.py --request-id 123 --actor export-operations
```

The requester cannot approve or execute their own request. Approval expires, output is JSON only, and the owner-only artifact and manifest remain beneath `PMOS_PRIVATE_ROOT/exports`. No private export is served by the public application.

The engine records snapshots and diffs. A changed title, page, legal name, domain or mandate creates a review item instead of silently overwriting the previous fact.

---

## Self-learning without LLMs

PMOS has two learning loops.

### 1. Research reinforcement

Each source and claim receives reliability signals based on:

- official domain vs secondary source
- repeated corroboration
- recency
- consistency across snapshots
- human acceptance/rejection

Accepted facts raise source confidence. Rejected or contradicted facts reduce it.

### 2. Relationship/outreach reinforcement

Record outcomes such as:

- replied
- meeting
- warm introduction
- pilot
- client
- investor
- no fit

Once enough outcomes exist, run:

```bash
make train
```

PMOS trains a local logistic-regression model using only your own outcomes and re-ranks counterparties. No data leaves the Mac and no LLM credits are consumed.

---

## Counterparty scoring

PMOS intentionally keeps several scores separate:

- **Capital Access** — capital controlled/influenced
- **Asset Access** — valuable assets, portfolios or transaction inventory
- **Network Leverage** — ability to open other credible relationships
- **Private Asset Fit** — relevance to private markets / high-value physical assets
- **Engagement Probability** — realistic chance of a conversation
- **Immediate Value Fit** — strength of your useful wedge
- **Evidence Confidence** — quality and freshness of supporting sources

A giant institution is not automatically the highest priority. A smaller professional gatekeeper with direct access and a solvable problem can outrank a trillion-dollar allocator.

---

## PMOS product wedges

The same core graph can support multiple products without duplicating infrastructure:

1. **Private Sales OS** — transaction readiness, provenance/evidence, buyer fit, private-sale deal room.
2. **Family Office Acquisition OS** — illiquid assets, acquisition pipeline, evidence, counterparties.
3. **Private Bank Alternative Asset OS** — collection/asset intelligence, controls, lending evidence.
4. **Trust & Estate Asset Intelligence** — inventory, ownership evidence, succession and exceptions.
5. **Insurance / Reinsurance Evidence OS** — underwriting evidence, claims/reconciliation, custody chain.
6. **Capital Relationship Intelligence** — investor/allocator graph, warm intros, mandate fit and outreach.

---

## Repository structure

```text
pmos-public/
├── apps/
│   ├── api/                 FastAPI API
│   └── web/                 responsive Next.js interface
├── config/
│   ├── universes.yaml       global institutional universe
│   └── scoring.yaml         deterministic score weights
├── packages/research/
│   └── pmos_research/       crawler, adapters, entity resolution, evidence
├── scripts/
│   ├── bootstrap_mac.sh
│   ├── seed_universe.py
│   ├── research_universe.py
│   ├── import_private.py
│   ├── execute_approved_export.py
│   └── train_priority_model.py
├── data/
│   └── public/              public-safe seeds only
├── docs/
│   ├── DUE_DILIGENCE_STANDARD.md
│   ├── PUBLIC_PRIVATE_BOUNDARY.md
│   ├── DAVID_ROTHSCHILD_DEMO.md
│   └── VERCEL.md
└── .github/workflows/
```

---

## Public GitHub setup

```bash
git init
git add .
git commit -m "Initial PMOS public release"
git branch -M main
gh repo create ChefMrFrizzle/pmos --public --source=. --remote=origin --push
```

If the name is unavailable, use `private-markets-os` or `pmos-network`.

The private seed data should be stored in a **separate private repo** only if you want Git synchronization at all. Local encrypted storage is safer for relationship intelligence.

---

## Vercel

The web app is Vercel-ready. PMOS's local/private database should **not** be deployed to Vercel.

Recommended architecture:

- Vercel: public/demo Next.js UI
- Local Mac or private cloud: API + private database
- Demo dataset: synthetic/public-safe only

See `docs/VERCEL.md`.

---

## What to build for David Rothschild

Start with one synthetic private-sale transaction, not the entire global graph.

The demo should show:

`Asset → Evidence → Provenance → Exceptions → Transaction Readiness → Buyer Fit → Exhibition Opportunity → Deal Room → Close`

Then PMOS demonstrates that the same infrastructure can extend across family offices, private banks, insurers, fiduciaries and institutional capital.

See `docs/DAVID_ROTHSCHILD_DEMO.md`.

---

## Security

Before publishing:

```bash
make public-check
```

This fails if obvious private-data paths, spreadsheets, secrets or database files are present in the public repository.

**Never commit the private seed ZIP into the public repo.**
