# QSys Frontend

This is the Next.js App Router runtime for QSys. It serves the kiosk display at
`/` and the BFF API under `/api/v1`.

## Development

Run from this directory:

```bash
pnpm install --frozen-lockfile
pnpm dev
```

Next is configured to load the repo-root `.env` during local dev and build.

## Production Build

```bash
pnpm build
pnpm start
```

`pnpm build` creates the standalone Next server and copies `public/` plus
`/.next/static` assets into `.next/standalone`, which is the directory used by
`qsys-server.service`.

The production server reads these runtime env vars from the root `.env` or
systemd environment:

- `HOSTNAME`
- `PORT`
- `NODE_ENV`
- `NEXT_TELEMETRY_DISABLED`
- `NODE_OPTIONS`
- `QSYS_MAX_VISIBLE_ORDERS`
- `QSYS_FLASH_DURATION_MS`
- `QSYS_SSE_HEARTBEAT_MS`
- `QSYS_AUTO_RELOAD_INTERVAL_MS`
