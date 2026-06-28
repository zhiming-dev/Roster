# Implementation Plan: React + Motion UI Rewrite

**Branch**: `002-react-motion-ui-rewrite` | **Date**: 2026-06-27 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/002-react-motion-ui-rewrite/spec.md`

## Summary

Replace the single ~960-line `runtime/static/dashboard.html` with a Vite + React + TypeScript
single-page app, styled in the locked two-theme identity (see spec Design Direction) and animated
with Motion (motion.dev) springs. The Python FastAPI backend and its contract (`/api/*` + `/ws`)
are unchanged; the only backend touch is serving the built SPA instead of the legacy HTML. The
work is sequenced parity-first, then identity, then motion, then (flagged) orchestration surfaces
for spec 001.

## Technical Context

**Language/Version**: TypeScript 5.x (frontend); Python 3.10+ (backend, unchanged).

**Primary Dependencies**: React 18, Vite 5, Motion (`motion`, motion.dev) for React, Zustand
(small state store), CSS Modules + CSS custom properties for theming, `@fontsource` (self-hosted
Space Grotesk + Plus Jakarta Sans). Backend unchanged: FastAPI + Uvicorn.

**Storage**: N/A on the frontend. Backend persistence (SQLite via `runtime/roster/store.py`) is
untouched.

**Testing**: Vitest + React Testing Library (components, stores, event reducers); Playwright
parity smoke against a running backend; `tsc --noEmit` for type safety.

**Target Platform**: Desktop browsers (Chromium/Firefox/WebKit). Responsive-friendly, not
mobile-first.

**Project Type**: Web — SPA frontend consuming the existing Python API service.

**Performance Goals**: First meaningful render + `/ws` connect promptly on localhost; animations
target 60fps and never block input; `prefers-reduced-motion` fully honored.

**Constraints**: Must be servable by the existing FastAPI in a single Python process (no Node at
runtime); no backend contract change required for parity; both themes meet WCAG AA.

**Scale/Scope**: One active run at a time, modest event volume (chat + agent traffic) over a
single WebSocket.

## Constitution Check

*GATE: checked against [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md)
v1.0.0.*

| Principle | Bearing on this feature | Status |
|---|---|---|
| I. Human-in-the-loop | UI surfaces gates/approvals and 001's "awaiting input" state; it never auto-acts on the human's behalf | ✅ |
| II. Safety & recoverability | Presentation-only; the legacy dashboard is kept as a fallback until parity (SC-001) passes | ✅ |
| III. Least privilege / restraint | No agent capabilities or orchestration changed | ✅ n/a |
| IV. Truth over plausibility | UI renders backend data verbatim; it synthesizes no facts | ✅ |
| V. Everything observable | Consumes the provenance/event stream and makes it *more* legible | ✅ |
| VI. Typed, validated contracts | Types the existing REST/WS event kinds; requires no contract change | ✅ |
| Engineering standards | OSS-only (Motion); WCAG AA both themes; `prefers-reduced-motion`; single-process serve; no backend behavior change | ✅ |

→ No violations. Complexity Tracking below is intentionally empty.

## Research & Decisions (Phase 0)

| Decision | Choice | Rationale / alternatives |
|---|---|---|
| Frontend stack | Vite + React 18 + TS | Per spec clarification; fast dev, static build FastAPI can serve. |
| Routing | None initially (single view) | Current app is single-view; selection is state, not URL. Add `react-router` later if conversations become deep-linkable. |
| State management | Zustand | Frequent WS-driven updates to agents/events/conversations; minimal boilerplate. Alt: Context + `useReducer` (no dep) — acceptable but noisier. |
| Styling | CSS custom properties + CSS Modules | Mirrors the token-driven mockup; two themes via `data-theme`; no Tailwind config overhead. Alt: Tailwind / vanilla-extract. |
| Animation | Motion for React (`motion/react`) | The chosen library; springs, `layout`, `AnimatePresence`, `useReducedMotion`, `MotionConfig`. |
| Fonts | Self-hosted via `@fontsource` | Offline-friendly local tool; avoids Google CDN dependency at runtime. |
| Build serving | Vite `build.outDir` → `runtime/static/app`, `base: "/app/"` | FastAPI serves built assets; one process. Dev uses Vite proxy. |
| Dev proxy | Vite proxies `/api` + `/ws` → `http://localhost:8765` | Run backend + Vite dev concurrently; same code paths as prod via relative URLs. |
| Backend change | Minimal: index route serves built SPA | Keep `dashboard.html` until parity (SC-001) is verified, then switch the default. |

**Open item (spec FR-018):** how much of spec 001's surfaces land here → **resolved at plan
level**: build the *component seams* (PlanView / CritiqueRound / ClarificationPrompt) with
stubbed/flagged data in Phase D; real wiring waits until 001 emits the events.

## Backend contract this UI consumes (Phase 1 — contracts)

Existing, unchanged (from `runtime/roster/server.py`):

- REST: `GET /api/health`, `GET /api/queue`, `GET /api/agents`, `POST /api/chat`
  (`{message}` → `{reply,runId}`), `POST /api/reset`, `GET /api/conversations`,
  `GET /api/conversations/{id}`, `POST /api/conversations/{id}/activate`,
  `DELETE /api/conversations/{id}`.
- WebSocket `GET /ws`: live event stream.
- Event kinds to type as a discriminated union: `user.message`, `agent.message`
  (`subkind`: `message | thinking | task_assignment | task_result`), `agent.status`
  (`status`: `idle | queued | thinking | searching | error`), `tool.search`
  (`phase`: `query | results | error`), `runtime.error`, `run.started`.

These become `frontend/src/types/events.ts` and a typed `api` client; the UI must not require any
new endpoint to reach parity.

## Frontend data model (Phase 1 — data-model)

Store slices (Zustand):

- `agents`: `Map<name, AgentStatus>` (role, status, model, queued, search) + derived lineage.
- `lineage`: nodes (incl. synthetic `you`) + edges (you→planner, planner→specialists) + active edge.
- `messages`: ordered chat turns (principal / agent, content, error).
- `activity`: inter-agent events (message subkinds, search phases, runtime errors) + unread count.
- `conversations`: list + active id + run id + queue state.
- `connection`: WS connected/reconnecting (new — make disconnection visible per SC-006).
- `theme`: `light | dark | system`.
- (Phase D, flagged) `orchestration`: plan/decomposition, critique rounds, pending question.

## Project Structure

### Documentation (this feature)

```text
specs/002-react-motion-ui-rewrite/
├── spec.md                 # done
├── plan.md                 # this file (Phase 0/1 inlined)
├── mockups/directions.html # design reference (locked)
└── tasks.md                # Phase 2 output (/speckit-tasks) — not yet
```

### Source Code

```text
frontend/                          # NEW — Vite + React + TS app
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts                 # base:"/app/", outDir → ../runtime/static/app, dev proxy
└── src/
    ├── main.tsx
    ├── App.tsx                     # grid shell: Sidebar | Workspace | Activity
    ├── theme/                      # tokens.css (two palettes), ThemeProvider, useTheme
    ├── motion/                     # spring presets, MotionConfig (reduced-motion)
    ├── api/                        # rest client + useWebSocket hook (reconnect)
    ├── types/                      # events.ts (discriminated union), models.ts
    ├── store/                      # zustand slices (agents, messages, activity, conversations…)
    ├── components/
    │   ├── sidebar/                # Brand, NewChat, ConversationList/Item, ThemeToggle
    │   ├── lineage/                # LineageGraph (SVG edges) + AgentNode (motion)
    │   ├── chat/                   # ChatView, MessageBubble, TypingIndicator, EmptyState, Composer
    │   ├── activity/               # ActivityPanel, ActivityEvent
    │   └── orchestration/          # (Phase D, flagged) PlanView, CritiqueRound, ClarificationPrompt
    └── test/                       # Vitest setup
```

Backend touchpoints (only):

```text
runtime/roster/server.py           # index() serves built SPA (frontend → runtime/static/app)
runtime/static/dashboard.html      # kept as fallback until parity verified, then retired
```

**Structure Decision**: Source lives in a new top-level `frontend/`; Vite builds into
`runtime/static/app/` so the existing FastAPI serves it with no new process. Dev runs Vite +
Uvicorn concurrently with a proxy. This keeps the single-process deploy gate intact.

## Implementation Phases (maps to spec user stories)

- **Phase A — Foundation & parity (US1, P1).** Scaffold Vite/React/TS; types from the event
  union; REST client + reconnecting `useWebSocket`; Zustand slices; app shell; render agents,
  lineage, chat, activity, conversation CRUD against the live backend; wire send/new/open/delete;
  serve build via FastAPI. Exit: SC-001 parity checklist passes.
- **Phase B — Visual identity (US2, P1).** Implement the two-theme token system + fonts + role
  palette from the mockup; theme toggle; AA contrast pass. Exit: SC-003.
- **Phase C — Motion system (US3, P2).** Spring presets via `motion/react`; node state
  transitions, fan-out stagger, breathing busy state, flowing edges, message/activity entrances,
  list `layout` animations, panel/sidebar springs, dark aurora drift; `MotionConfig` +
  `useReducedMotion`. Exit: SC-002.
- **Phase D — Orchestration seams (US4, P3, flagged).** Stub PlanView / CritiqueRound /
  ClarificationPrompt + an `awaiting-input` state, behind a feature flag, fed mock data until
  spec 001 emits real events. Exit: components render representative 001 events.

## Risks & Mitigations

- **Asset base path** (FastAPI-served vs Vite dev) → set Vite `base:"/app/"`, use relative `/api`
  & `/ws`, verify both modes in Phase A.
- **WS reconnect UX** → first-class `connection` state + visible banner (improves on the current
  silent retry; satisfies SC-006).
- **Lineage layout** with many specialists → keep the current responsive layout math; cap/scroll.
- **Motion overload** → centralize spring presets; gate everything through `MotionConfig`; test
  reduced-motion early.
- **Parity drift** → maintain an explicit parity checklist derived from `dashboard.html`; do not
  delete the legacy file until the checklist passes.

## Complexity Tracking

*No constitution violations — table intentionally empty.*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |

## Next Steps

1. (Optional) Ratify a real `constitution.md` so `/speckit-tasks` has a true gate.
2. `/speckit-tasks` — break Phases A–D into ordered, independently-shippable tasks with the
   parity checklist as P1 acceptance.
3. Begin Phase A scaffold (`frontend/` + Vite config + backend serve switch behind the legacy
   fallback).
