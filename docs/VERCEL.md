# Vercel Deployment

PMOS deliberately separates the public/demo UI from private intelligence.

## Recommended deployment

- `apps/web`: Vercel
- `apps/api`: local Mac during development, or private infrastructure later
- private SQLite/Postgres: never bundled with the public web build
- demo data: synthetic/public-safe only

## Deploy the web UI

Install Vercel CLI:

```bash
npm i -g vercel
```

From `apps/web`:

```bash
vercel link
vercel env add NEXT_PUBLIC_API_URL
vercel --prod
```

For a purely public demo, `NEXT_PUBLIC_API_URL` can point at a sanitized demo API. Do not expose your local/private PMOS API to the open internet without authentication, authorization and transport security.
