# PMOS Due-Diligence Standard

Every entity is researched through the same institutional lens.

## Required entity record

- legal / public name
- entity type and universe
- headquarters + material offices
- official domain
- jurisdiction
- mandate / function
- AUM/AUA/fund size when officially available
- asset classes / acquisition mandate
- senior decision-makers
- relevant functional gatekeepers
- publicly evidenced relationships
- capital-access score
- asset-access score
- network-leverage score
- engagement-probability score
- immediate-value-fit score
- evidence-confidence score
- explicit PMOS useful wedge
- last verified timestamp
- verification status
- next action

## Evidence hierarchy

1. regulator / statute / official filing
2. official institutional website, annual report or press release
3. official professional biography
4. audited report / recognized institutional publication
5. reputable financial or trade media
6. professional directories
7. social/professional profile
8. unknown / unattributed source

A lower-ranked source must never silently override a higher-ranked current source.

## Contact rules

- never invent email formats
- never infer a private phone number
- preserve the public professional context for every contact
- mark stale contacts instead of deleting history
- retain source + verification date
- do not infer family membership or beneficial ownership from surname alone

## Ownership / UBO

PMOS may ingest lawful public beneficial-ownership evidence from official registries or user-authorized sources. It must distinguish:

- legal owner
- beneficial owner
- controlling person
- trustee
- protector
- beneficiary
- investment manager
- authorized representative

Do not collapse these roles.

## Relationship graph

Edges require evidence and a date where possible:

- OWNS
- MANAGES
- ADVISES
- ALLOCATES_TO
- INVESTED_IN
- CO_INVESTED_WITH
- TRUSTEE_OF
- BOARD_MEMBER_OF
- REPRESENTS
- INSURES
- FINANCES
- CUSTODIES
- INTRODUCED_BY
- BOUGHT_FROM
- SOLD_TO

Each edge has `source_url`, `confidence`, `first_seen`, `last_seen`, and `verification_status`.

## Refresh policy

- A+ strategic counterparties: 30 days
- A: 60 days
- B: 180 days
- C / archive: 365 days

Role/title changes become review items; they are not silently overwritten.
