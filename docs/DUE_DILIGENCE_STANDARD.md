# PMOS Institutional Due-Diligence Standard

PMOS applies documented, repeatable institutional research procedures. It is not affiliated with a Big Four firm, does not provide an audit opinion, and does not label a counterparty KYC/AML-cleared or legally approved. Human specialists and counsel retain judgment.

## Case workflow

`INTAKE → SCOPE/FIT → IDENTITY/LEGAL EXISTENCE → OWNERSHIP/CONTROL → REGULATORY/LEGAL → STRUCTURE → PEOPLE/AUTHORITY → MANDATE → RELATIONSHIPS → ADVERSE EVENTS → CONFLICTS → SPECIALIST SIGN-OFF → MONITOR`

Every case records purpose, permitted use, jurisdictions, as-of date, exclusions, risk tier, owner, independent reviewer where required, open blockers, decision, and immutable audit events. “Complete” means scoped checks were performed or explicitly excepted; it never means risk-free.

## Evidence ranks

- **S0:** original legal instrument; court, regulator, sanctions authority, corporate/charity registry, or audited filing
- **S1:** official annual report, prospectus/public fund document, institution site, statute, or government publication
- **S2:** independently audited report or recognized market infrastructure such as GLEIF or an exchange
- **S3:** reputable financial/trade journalism with named author and direct sourcing
- **S4:** professional directory or profile
- **S5:** aggregator, unattributed material, or user/private-source lead

Authority and publisher independence are scored separately. Private imports remain leads and never become public verification. Self-description may support identity or mandate, but not silently prove ownership, comparable AUM, performance, reputation, or authority to transact.

## Claim and verification rules

Every assertion retains normalized and verbatim values, effective date, publisher, document identifier, URL, page/section, a bounded evidence passage, retrieval/first/last-seen times, content and passage hashes, extractor version, source rank, independence group, jurisdiction, confidence dimensions, conflict group, reviewer rationale, and use restrictions.

- **T0 UNASSESSED**
- **T1 LEAD**
- **T2 SOURCE_CAPTURED**
- **T3 SUPPORTED:** one appropriate source and identity match
- **T4 CORROBORATED:** dispositive S0 evidence, or two independent S1–S3 sources including S1/S2
- **T5 SPECIALIST_VERIFIED:** scoped human review and sign-off

`BLOCKED`, `CONFLICT`, `STALE`, and `REJECTED` are explicit parallel states. Entity status is a coverage roll-up; a homepage name match cannot verify the whole entity.

Confidence dimensions remain separate: identity match, source authority, independence, directness, corroboration, freshness, and extraction reliability. Fatal weaknesses cannot be averaged away. Conflicts cap a claim until review.

## Material conflicts and freshness

Competing claims are retained in a `ConflictCase`. Legal name/status, regulator, controller, authority, sanctions status, fund manager/domicile, and metric-basis conflicts block transaction readiness. Resolution requires reviewer, rationale, selected and non-selected claims, evidence, and timestamp; losing history is never deleted.

Refresh intervals are fact-specific: sanctions before each material action; authority/role 30 days; legal/regulatory, ownership/control, fund manager/domicile 90 days; mandate 180 days; stable identity/address 365 days. Reporting metrics expire after the next expected report plus grace. Material events trigger immediate refresh.

## Identity and institutional structures

Organizations auto-match only on an authoritative identifier, or compatible legal name, jurisdiction, and official domain. Name plus jurisdiction alone is probable. People require compatible name, strong contact evidence, and employment context. Shared inboxes, recycled domains, branches, similarly named funds, managers, advisers, GPs and LPs remain distinct until adjudicated.

Canonical identity clusters preserve every source record. Memberships are proposed, accepted, or rejected through immutable reviewer events. `OWNS`, `CONTROLS`, and beneficial-owner assertions always require authoritative evidence and human review; names or domains never imply ownership.

The structure model distinguishes legal entities, funds, share classes, accounts, GP, manager/AIFM, adviser, sponsor, allocator/LP, trustee, custodian, administrator, auditor, prime broker, feeder/master/parallel vehicles, SPVs, blockers, and co-investment vehicles. AUM, AUA, NAV, commitments, target close and final close remain distinct metrics with currency, basis and date.

## Decision gates

- **GREEN:** all mandatory checks corroborated or specialist-verified, fresh, with no unresolved material conflicts
- **AMBER:** exceptions are documented and assigned to a specialist/counsel with visible decision restrictions
- **RED:** legal identity or transaction authority missing, material identity/manager/ownership conflict, sanctions/regulatory issue, or evidence mismatch

PMOS recommends escalation; humans decide. There is no autonomous outreach, entity merge, beneficial-ownership inference, or legal conclusion.

## Dossier output

A dossier contains the executive decision summary, identity tree, ownership/control and authority, regulatory standing, structure diagram, defined capital metrics, decision-makers/gatekeepers, sourced relationship map, public contact paths, scoped adverse-event checks, conflicts/exceptions, evidence coverage, freshness, limitations, next action, and reviewer sign-off. Every material sentence drills into its claim and exact evidence passage.
