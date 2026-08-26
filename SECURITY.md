# Security

Primary threats are accidental Git/deployment leakage, secrets, client-side exposure, unsafe imports, SSRF, malicious HTML, formula injection, path traversal, and incorrect identity merges.

`scripts/public_release_check.py` fails closed on private paths, archives, databases, spreadsheets, keys, likely secrets, large exports, and email-bearing CSV files. Run it before staging, committing, or deploying. Private services bind locally by default. Importers must preserve raw values, sanitize spreadsheet formulas on export, reject paths outside the configured import root, and queue ambiguous identity matches for review. Crawlers allow only credential-free public HTTP(S), validate DNS and every redirect, fail closed when robots rules are unavailable, reject oversized/non-HTML responses, strip executable HTML, and rate-limit per host.
