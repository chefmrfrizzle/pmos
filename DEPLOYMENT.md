# Deployment

Run `make public-check`, tests, and the web production build before deployment. Vercel receives only `apps/web` and synthetic public assets. Never configure `PMOS_DB_URL`, `PMOS_PRIVATE_ROOT`, private API origins, or private credentials in a public project. Verify desktop/mobile rendering, core interactions, network requests, and console errors after release.
