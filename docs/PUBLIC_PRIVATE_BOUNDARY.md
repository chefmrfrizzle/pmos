# Public / Private Boundary

## Safe for public repository

- application code
- schemas
- scoring methodology
- generic universe taxonomy
- official institution names and public corporate URLs
- synthetic demo data
- documentation

## Private by default

- investor/contact spreadsheets
- personal professional emails and direct phone datasets assembled for outreach
- relationship notes
- warm-introduction paths
- outreach status
- response history
- client or counterparty documents
- non-public ownership / UBO records
- scraped pages retained for internal analysis
- private source credentials
- proprietary scoring outputs tied to identifiable people

The public repo's `.gitignore` blocks common private-data formats by default. Run `make public-check` before every public release.
