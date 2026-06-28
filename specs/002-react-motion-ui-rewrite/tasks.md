---
description: "Task list — React + Motion UI Rewrite"
---

# Tasks: React + Motion UI Rewrite

**Input**: Design documents in `specs/002-react-motion-ui-rewrite/` ([spec.md](./spec.md),
[plan.md](./plan.md), [mockups/directions.html](./mockups/directions.html))

**Gate**: [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md) v1.0.0 — passed
in plan.md.

**Tests**: The spec does not request TDD; tests here are limited to a constitutionally-required
**parity check** (Engineering Standards: "parity before removal") plus a light smoke. Marked
accordingly.

## Format: `[ID] [P?] [Story] Description`

- **[P]** = can run in parallel (different files, no dependency on another unchecked task).
- **[Story]** = US1 (parity) · US2 (identity) · US3 (motion) · US4 (orchestration seams).
- Paths are relative to repo root. New frontend lives under `frontend/`.

---

## Phase 1: Setup (shared infrastructure)

- [x] T001 Scaffold `frontend/` — Vite + React + TS: `frontend/package.json`,
  `frontend/tsconfig.json` (strict), `frontend/index.html`, `frontend/src/main.tsx`,
  `frontend/vite.config.ts` with `base: "/app/"`, `build.outDir: "../runtime/static/app"`,
  and a dev `server.proxy` for `/api` + `/ws` → `http://localhost:8765`.
- [x] T002 [P] Add dependencies in `frontend/package.json`: runtime `react`, `react-dom`,
  `motion`, `zustand`, `@fontsource/space-grotesk`, `@fontsource/plus-jakarta-sans`; dev `vite`,
  `typescript`, `@vitejs/plugin-react`, `vitest`, `@testing-library/react`, `@playwright/test`.
- [x] T003 [P] Configure ESLint + Prettier for `frontend/` (`eslint.config.js` flat config, `.prettierrc`).
- [x] T004 [P] Vitest + RTL setup at `frontend/src/test/setup.ts` and `vitest` config in
  `vite.config.ts`.

---

## Phase 2: Foundational (blocking prerequisites)

**⚠️ No user-story work begins until this phase is complete.**

- [x] T005 Type the backend contract — `frontend/src/types/events.ts` (discriminated union for
  `user.message`, `agent.message` w/ `subkind` `message|thinking|task_assignment|task_result`,
  `agent.status` w/ `status` `idle|queued|thinking|searching|error`, `tool.search` w/ `phase`
  `query|results|error`, `runtime.error`, `run.started`) and `frontend/src/types/models.ts`
  (Agent, Conversation, ChatMessage, ActivityEvent, QueueState).
- [x] T006 REST client `frontend/src/api/client.ts` — typed wrappers for `GET /api/agents`,
  `GET /api/queue`, `POST /api/chat`, `POST /api/reset`, `GET /api/conversations`,
  `GET /api/conversations/{id}`, `POST /api/conversations/{id}/activate`,
  `DELETE /api/conversations/{id}`.
- [x] T007 Reconnecting WS hook `frontend/src/api/useWebSocket.ts` — connect `/ws`, auto-reconnect
  with backoff, surface a `connection` state (connected / reconnecting).
- [x] T008 [P] Zustand store slices in `frontend/src/store/` — `agents`, `messages`, `activity`
  (+ unread), `conversations` (+ runId, queue), `connection`, `theme`; plus a `lineage` selector
  deriving nodes/edges from `agents`.
- [x] T009 [P] Event reducer `frontend/src/store/handleEvent.ts` — map one backend event to store
  mutations (port of the current `handleEvent`, incl. `live` vs replay handling).
- [x] T010 App shell `frontend/src/App.tsx` — CSS-grid layout (Sidebar | Workspace | Activity)
  with empty region placeholders; mount providers in `main.tsx`.
- [x] T011 Backend serve switch — `runtime/roster/server.py`: `index()` serves the built SPA from
  `runtime/static/app/index.html` when present, else falls back to `dashboard.html`; mount the
  built `assets/`. (Constitution II: keep the legacy fallback until parity passes.)

**Checkpoint**: foundation ready — user stories can begin.

---

## Phase 3: User Story 1 — Componentized SPA at feature parity (P1) 🎯 MVP

**Goal**: Every current `dashboard.html` capability works in React against the unchanged backend.

**Independent Test**: Run the React build behind FastAPI on a live runtime; the parity checklist
(T020) passes with no loss vs the legacy dashboard.

- [x] T012 [P] [US1] Sidebar shell `frontend/src/components/sidebar/` — `Brand.tsx`,
  `NewChatButton.tsx` (→ `POST /api/reset`).
- [x] T013 [US1] `ConversationList.tsx` + `ConversationItem.tsx` — list, open (activate + replay),
  delete (confirm), active highlight, run-id + queue chip; wired to client + store.
- [x] T014 [P] [US1] `frontend/src/components/lineage/LineageGraph.tsx` — SVG curved edges +
  responsive node layout (port `buildLineage`/`layoutLineage`), `you→planner→specialists`.
- [x] T015 [US1] `AgentNode.tsx` — role color, live status (idle/queued/thinking/searching/error),
  the synthetic `you` node, active-edge flash on traffic.
- [x] T016 [P] [US1] Chat surface `frontend/src/components/chat/` — `ChatView.tsx`,
  `MessageBubble.tsx` (user/agent/error), `TypingIndicator.tsx`, `EmptyState.tsx` (suggestions
  fill the composer).
- [x] T017 [US1] `Composer.tsx` — autosizing textarea, Enter-to-send / Shift+Enter newline,
  disabled while awaiting; optimistic user bubble; error bubble on failure.
- [x] T018 [P] [US1] Activity feed `frontend/src/components/activity/` — `ActivityPanel.tsx`
  (collapsible + unread badge), `ActivityEvent.tsx` (agent-message subkinds, `tool.search`
  query/results/error with linkified URLs, `runtime.error`).
- [x] T019 [US1] Wire it together — feed `/ws` (live) and conversation replay through
  `handleEvent` into all surfaces; render a visible **disconnected/reconnecting banner**
  (SC-006); load active conversation on boot.
- [x] T020 [US1] Parity checklist `specs/002-react-motion-ui-rewrite/parity-checklist.md` derived
  from `dashboard.html`; verify each item against the React app.
- [x] T021 [US1] (light) Playwright smoke `frontend/tests/smoke.spec.ts` — load, send a message,
  observe a status change + an activity event, create/delete a conversation.

**Checkpoint**: SC-001 (parity) and SC-006 (visible disconnect) met. App is usable end-to-end.

---

## Phase 4: User Story 2 — New livelier visual identity (P1)

**Goal**: Replace the Apple-flat language with the locked one-identity / two-theme system.

**Independent Test**: Tokens no longer match the legacy iOS palette/SF/blur; both themes pass AA.

- [x] T022 [US2] Design tokens `frontend/src/theme/tokens.css` — the two palettes (light warm /
  dark aurora), role colors, radii, shadows/glow, font vars; switched via `data-theme`. Port from
  `mockups/directions.html`.
- [x] T023 [P] [US2] Self-host fonts via `@fontsource` (Space Grotesk display, Plus Jakarta Sans
  body); wire `--font-d` / `--font`.
- [x] T024 [US2] `ThemeProvider` + `useTheme` (light/dark/system, persisted to localStorage) and
  `ThemeToggle.tsx` (spring-sliding knob).
- [x] T025 [US2] Apply tokens across all Phase-3 components (CSS Modules); remove any placeholder
  Apple-flat styling.
- [~] T026 [US2] WCAG AA contrast pass on both themes; fix failing pairs (SC-003).

**Checkpoint**: SC-003 met; the app looks like the mockup in both themes (static).

---

## Phase 5: User Story 3 — Springy "Q弹" motion system (P2)

**Goal**: Layer Motion springs across the now-stable components.

**Independent Test**: Each interaction shows spring physics; `prefers-reduced-motion` tames it.

- [x] T027 [US3] Motion foundation — spring presets `frontend/src/motion/springs.ts` (bouncy /
  soft / snappy) and `<MotionConfig reducedMotion="user">` in `App.tsx`.
- [x] T028 [P] [US3] Animate `AgentNode` — status transitions, fan-out **stagger** spawn,
  breathing busy state, flowing active edges.
- [x] T029 [P] [US3] Animate chat — message spring entrance via `AnimatePresence`; list `layout`
  animations on insert.
- [x] T030 [P] [US3] Animate activity — event entrance + unread-badge pop.
- [x] T031 [P] [US3] Animate chrome — panel/sidebar open-close springs, conversation hover/tap,
  theme-toggle knob, dark aurora background drift.
- [x] T032 [US3] Verify `prefers-reduced-motion` across all interactions (SC-002).

**Checkpoint**: SC-002 met; the "灵动 / Q弹" feel matches the mockup.

---

## Phase 6: User Story 4 — Orchestration seams for spec 001 (P3, flagged)

**Goal**: Component seams that render 001's concepts, behind a flag, fed mock data until 001 emits
real events (resolves FR-018 at plan level).

**Independent Test**: With mock data, each 001 concept renders distinctly.

- [x] T033 [US4] Feature flag + `orchestration` store slice (plan / critique / clarification) with
  a mock-data source.
- [x] T034 [P] [US4] `frontend/src/components/orchestration/PlanView.tsx` — decomposition
  (sub-tasks + dependencies).
- [x] T035 [P] [US4] `CritiqueRound.tsx` — pushback + resolution exchange.
- [~] T036 [US4] `ClarificationPrompt.tsx` + a run **"awaiting input"** state in the chat/composer.

**Checkpoint**: representative 001 events render (mock); ready to wire when 001 ships.

---

## Phase 7: Polish & cross-cutting

- [ ] T037 Retire `runtime/static/dashboard.html` and make the SPA the default served file — only
  after T020 parity passes (Constitution II).
- [ ] T038 [P] Docs — update `runtime/README.md` + `AGENTS.md` with `frontend/` layout and the
  dev (`vite`) / build (`vite build`) / serve commands.
- [ ] T039 [P] First-load + `/ws`-connect and bundle-size check (SC-004 single-process serve).
- [ ] T040 Final a11y sweep — keyboard nav, visible focus, reduced-motion — and cleanup.

---

## Dependencies & Execution Order

- **Setup (T001–T004)**: no deps; T002–T004 parallel after T001.
- **Foundational (T005–T011)**: depends on Setup; **blocks all user stories**. T008/T009 parallel;
  T005/T006/T007 before them; T010/T011 independent of each other.
- **US1 (T012–T021)**: depends on Foundational. T012/T014/T016/T018 parallel (distinct dirs);
  T013/T015/T017/T019 wire stores → sequence after their components; T020/T021 last.
- **US2 (T022–T026)**: depends on US1 components existing (it restyles them). T023 parallel.
- **US3 (T027–T032)**: depends on US2 (motion layers onto settled styles). T028–T031 parallel.
- **US4 (T033–T036)**: depends on Foundational only; can proceed in parallel with US2/US3 if
  staffed. T034/T035 parallel.
- **Polish (T037–T040)**: T037 gated on T020; others after desired stories complete.

### Within each story

- Components before the task that wires them into stores.
- Story complete (its checkpoint met) before moving to the next priority.
- MVP = Phase 1 + 2 + **US1** (a working, parity React app). US2 makes it look right; US3 makes it
  feel right; US4 prepares for spec 001.
