# Roster frontend

Vite + React + TypeScript dashboard for the Roster runtime. It consumes the Python service's
`/api/*` REST endpoints and `/ws` WebSocket — there is no separate Node backend.

## Develop

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173/app/  (proxies /api + /ws → :8765)
```

Run the Python runtime in another terminal (`cd runtime && python -m roster`, serves :8765) so the
proxy has something to talk to.

## Build (served by the Python runtime)

```bash
npm run build        # type-checks, then emits to ../runtime/static/app
```

FastAPI serves the built app at `/`; the legacy `runtime/static/dashboard.html` remains the
fallback until parity (spec 002, T020) is verified.

## Other scripts

- `npm run typecheck` — `tsc --noEmit`
- `npm run lint` — ESLint (flat config)
- `npm run format` — Prettier
- `npm test` — Vitest (jsdom)

See [`../specs/002-react-motion-ui-rewrite/`](../specs/002-react-motion-ui-rewrite/) for the spec,
plan, and task list.
