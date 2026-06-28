# Feature Specification: React + Motion UI Rewrite

**Feature Branch**: `002-react-motion-ui-rewrite`

**Created**: 2026-06-27

**Status**: Draft

**Input**: User description: "Rewrite the dashboard from a single Python-served HTML file into a
TypeScript + React frontend (Vite). Keep the Python backend. Drop the current Apple-industrial
glassmorphism look for something livelier and more characterful, with springy/bouncy ('Q弹')
motion using Motion (motion.dev), free/open-source tier."

## Context & Problem

The current UI is a single ~960-line static HTML file (`runtime/static/dashboard.html`) served
by FastAPI. It already does a lot — chat with the Planner, an agent lineage graph, a
collapsible inter-agent activity feed, conversation history CRUD, live WebSocket updates, and
light/dark theming — but:

- It is a monolith with no component architecture, hard to extend as the product grows.
- Its visual language is textbook Apple-flat: translucent `backdrop-blur` glass, SF Pro type,
  iOS system colors (`#007aff` et al.), large radii, soft shadows. The principal wants to move
  away from this toward a livelier, more characterful identity.
- It must soon render the much richer orchestration coming from spec 001 (plan decomposition,
  parallel fan-out, critique/verification rounds, mid-task clarification) — which a componentized
  React app is far better positioned to do.

This feature rewrites the **frontend** as a Vite + React + TypeScript single-page app with
Motion (motion.dev) for spring-based animation, and a new visual identity. The **backend stays
Python**; the existing API contract (REST `/api/*` + WebSocket `/ws`) is unchanged. This is a
presentation-layer rewrite, not a runtime rewrite.

### Relationship to spec 001

Spec 001 (intelligent planner orchestration) adds new orchestration concepts and events
(decomposition, critique rounds, "awaiting input"). This UI must be architected to render them.
Where 001's events do not exist yet, the UI provides the component seams but may stub the data.

## Clarifications

### Session 2026-06-27

- Q: How far does the "frontend + backend TS" rewrite go? → A: **Keep the Python backend.** Only
  the frontend is rewritten (React + TS); it consumes the existing FastAPI `/api/*` + `/ws`.
- Q: Frontend stack? → A: **Vite + React + TypeScript**, with Motion (motion.dev, free tier) for
  animation.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Componentized React SPA at feature parity (Priority: P1)

The dashboard is rebuilt as a Vite + React + TypeScript SPA that reproduces every current
capability against the unchanged backend, and is served by the existing FastAPI in production.

**Why this priority**: The foundation. Nothing else (new look, motion, 001 surfaces) can land
until the app exists and reaches parity. Independently valuable: a maintainable component
codebase replacing the monolith.

**Independent Test**: Run the React app against a live Python runtime and confirm each current
feature works — chat, lineage, activity feed, history CRUD, live updates, theme — with no loss.

**Acceptance Scenarios**:

1. **Given** a running Python backend, **When** the React app loads, **Then** it fetches agents,
   conversations, and active events and renders the same information the current dashboard shows.
2. **Given** a message sent to the Planner, **When** the backend streams events over `/ws`,
   **Then** the chat, lineage statuses, and activity feed update live.
3. **Given** a production build, **When** FastAPI serves it at `/`, **Then** the app runs without
   a separate Node server.
4. **Given** conversation history, **When** the user creates, opens, or deletes a conversation,
   **Then** behavior matches the current app (activate/replay/delete).

---

### User Story 2 - New livelier visual identity (Priority: P1)

The Apple-flat language is replaced by a distinct, more characterful identity — its own color,
type, shape, and depth system — that the principal finds "灵动" (lively/nimble) rather than
industrial, while remaining legible and accessible in light and dark modes.

**Why this priority**: This is the principal's core motivation for the rewrite; parity without
the new look does not deliver the desired outcome.

**Independent Test**: Compare against the current design tokens; confirm the new identity does
not reuse the glassmorphism/iOS-system-color language and that both themes pass AA contrast.

**Acceptance Scenarios**:

1. **Given** the new app, **When** inspecting its design tokens, **Then** they define a new
   identity (not the current `--accent:#007aff` iOS palette, SF font, heavy blur surfaces).
2. **Given** light and dark themes, **When** measured, **Then** text/background pairs meet WCAG
   AA.
3. **Given** the six agent roles, **When** displayed, **Then** each remains visually
   distinguishable in the new palette.

---

### User Story 3 - Springy "Q弹" motion system (Priority: P2)

Key interactions animate with spring physics via Motion: agent state transitions, active-edge
flow on the lineage graph, message and activity-item entrances, list reordering, and panel/
sidebar open-close. The result feels bouncy and alive — the signature of the redesign.

**Why this priority**: The defining feel the principal asked for, layered onto the stable
components from US1/US2 so motion is added to a settled structure rather than a moving target.

**Independent Test**: Trigger each interaction and confirm spring-based motion (overshoot/settle),
and that enabling `prefers-reduced-motion` disables or tames it.

**Acceptance Scenarios**:

1. **Given** an agent changing status (idle→thinking→searching→done), **When** it transitions,
   **Then** the node animates with a spring, not a linear fade.
2. **Given** a new chat message or activity event, **When** it appears, **Then** it enters with
   spring motion and list neighbors reflow via layout animation.
3. **Given** the activity/sidebar panels, **When** toggled, **Then** they open/close with spring
   transitions.
4. **Given** `prefers-reduced-motion: reduce`, **When** the same interactions fire, **Then**
   motion is disabled or reduced to an accessible minimum.

---

### User Story 4 - Surfaces ready for richer orchestration (Priority: P3)

The app provides components to render spec 001's orchestration: a plan/decomposition view,
parallel fan-out on the lineage graph, critique/verification rounds, and a mid-task
clarification prompt with an explicit "awaiting input" state.

**Why this priority**: High product value but dependent on spec 001 emitting the corresponding
events; sequenced after the rewrite foundation and once 001's contract is known.

**Independent Test**: Feed the UI representative (real or stubbed) 001 events and confirm each is
rendered distinctly (a plan, a fan-out, a critique round, a pending question).

**Acceptance Scenarios**:

1. **Given** a decomposition event, **When** received, **Then** the UI shows the sub-tasks and
   their dependencies.
2. **Given** a critique/verification round, **When** received, **Then** the UI shows the pushback
   and resolution as a distinct exchange.
3. **Given** an "awaiting input" question to the principal, **When** received, **Then** the UI
   surfaces it as a prompt and reflects that the run is paused, not finished.

---

### Edge Cases

- Backend unreachable or `/ws` drops → the app shows a clear disconnected state and reconnects
  (current app silently retries; new app should make state visible).
- Long agent rosters or many specialists → the lineage layout stays readable.
- Very long messages / large search-result payloads → bounded, scrollable, no layout break.
- `prefers-reduced-motion` users → a fully usable, low-motion experience.
- Theme switch mid-animation → no broken/stuck animation states.
- Production (FastAPI-served static) vs dev (Vite proxy) → API/WS base URLs resolve correctly in
  both.

## Requirements *(mandatory)*

### Functional Requirements

**Stack & integration**

- **FR-001**: The frontend MUST be a Vite + React + TypeScript single-page application.
- **FR-002**: The frontend MUST consume the existing backend contract unchanged — REST `/api/*`
  and WebSocket `/ws` — requiring no backend behavior change to reach parity.
- **FR-003**: A production build MUST be servable as static assets by the existing FastAPI (so no
  separate Node process is needed to run Roster); development MUST proxy `/api` and `/ws` to the
  running Python server.
- **FR-004**: All animation MUST use Motion (motion.dev) free/open-source capabilities; no paid
  Motion+ feature may be required.

**Feature parity**

- **FR-005**: Users MUST be able to message the Planner and see user/agent bubbles, a typing
  indicator, error bubbles, and an empty state with example prompts.
- **FR-006**: The app MUST render the agent lineage graph (principal→planner→specialists) with
  per-agent live status and active-edge indication.
- **FR-007**: The app MUST render the collapsible inter-agent activity feed — agent messages by
  subkind, web-search query/results/errors, and runtime errors — with an unread badge when
  collapsed.
- **FR-008**: The app MUST support conversation history: list, new, open/activate (with event
  replay), and delete, plus run-id display and queue state.
- **FR-009**: The app MUST update live from `/ws` and replay persisted events when a conversation
  is opened.
- **FR-010**: The app MUST support light, dark, and system themes.

**Motion & feel**

- **FR-011**: Agent status transitions MUST animate with spring physics.
- **FR-012**: Chat messages and activity items MUST enter with spring motion, and lists MUST use
  layout animations for insertion/reordering.
- **FR-013**: Panel and sidebar open/close, and lineage node movement, MUST use spring
  transitions rather than linear easing.
- **FR-014**: The app MUST honor `prefers-reduced-motion`, providing a disabled/reduced-motion
  path that remains fully usable.

**Visual identity**

- **FR-015**: The app MUST define a new design-token system (color, type, shape, elevation) that
  is distinct from the current Apple-flat language (no dependence on iOS system colors, SF font,
  or heavy translucent-blur surfaces as the identity).
- **FR-016**: Both themes MUST meet WCAG AA contrast for text and essential UI.
- **FR-017**: The app MUST preserve role color-coding so the six agent roles remain
  distinguishable, expressed in the new palette.

**Orchestration-aware surfaces (links spec 001)**

- **FR-018**: The component architecture MUST be able to render spec 001 concepts — plan
  decomposition (sub-tasks + dependencies), parallel fan-out, critique/verification rounds, and a
  mid-task "awaiting input" clarification prompt.
  [NEEDS CLARIFICATION: how much of FR-018 ships in this feature vs is deferred until 001 emits
  the corresponding events]

### Key Entities

- **Conversation**: a run in history — id, title, message count, updated-at, active flag.
- **Agent node**: a role with live status (idle/queued/thinking/searching/error), model, and
  color.
- **Lineage edge**: a directed relationship (principal→planner, planner→specialist) with an
  active/flowing state.
- **Chat message**: principal or agent turn, with role, content, and error flag.
- **Activity event**: an inter-agent message (by subkind), a search phase, or a runtime error.
- **Queue state**: active/waiting/max-concurrency snapshot.
- **Theme**: light / dark / system.
- **Plan / critique / clarification** (from spec 001): decomposition, verification exchange,
  pending question.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of the current `dashboard.html` features are present in the React app, verified
  against a parity checklist.
- **SC-002**: All key interactions animate with spring physics; with `prefers-reduced-motion`
  enabled, motion is disabled or reduced while every feature stays usable.
- **SC-003**: The design no longer uses the current Apple-flat tokens; a design-token file defines
  the new identity and both themes pass WCAG AA.
- **SC-004**: Roster runs from a single Python process serving the built frontend — no separate
  Node server required at runtime.
- **SC-005**: A developer can add a new agent role or a new event-kind by editing a small, local
  set of components/config without touching unrelated parts of the app.
- **SC-006**: When the backend connection drops, the UI visibly reflects the disconnected state
  and recovers automatically on reconnect.

## Design Direction *(non-normative — validated via mockup 2026-06-27)*

Direction locked against the interactive mockup at
[`mockups/directions.html`](mockups/directions.html). It is **one identity with two themes**, not
two competing languages:

- **Single design system, light + dark both first-class.** The light theme reads warm,
  rounded, and approachable (candy-ish role colors, soft layered shadows, cream-tinted canvas);
  the dark theme reads electric and energetic (deep-ink aurora canvas, glowing role dots, accent
  glow instead of soft shadow). Same tokens, two palettes.
- **Typography**: a display family with character (Space Grotesk) for brand/headings paired with
  a friendly, legible body family (Plus Jakarta Sans). One pairing across both themes.
- **Palette**: an energetic violet → cyan accent with a coral secondary; a distinct per-role
  color set that makes the agents feel like a *team*, tuned brighter/glowing in dark.
- **Motion is the signature ("灵动 / Q弹")**: pronounced spring overshoot on state changes and
  entrances, springy hover-lift + tap-squish micro-interactions, staggered fan-out spawns,
  "breathing" pulse on busy nodes, flowing edges, a slow drifting aurora background in dark, and
  a spring-sliding theme toggle. All bounded so it clarifies rather than distracts.
- **Depth via motion + light layered shadow/glow, not heavy glassmorphism blur.**
- **Accessibility**: both themes target WCAG AA; full `prefers-reduced-motion` path.

## Assumptions

- The Python backend and its `/api/*` + `/ws` contract stay stable; if spec 001 changes events,
  the UI adapts to the new contract.
- Motion (motion.dev) is an acceptable frontend dependency, used within its free/open-source
  tier.
- Target is desktop browsers (as today); responsive behavior is desirable but not mobile-first.

## Out of Scope (this spec)

- Any change to agent orchestration logic or the runtime (that is spec 001).
- Rewriting the backend in TypeScript (explicitly decided against — Python stays).
- Authentication, multi-user, or multi-tenant operation.
- A mobile-first redesign.

## Next Steps (Spec Kit workflow)

1. ~~Build a Motion-powered interactive mockup to lock the visual identity~~ — done; see
   [`mockups/directions.html`](mockups/directions.html) and the Design Direction section
   (one identity, light + dark, springy).
2. `/speckit-clarify` — resolve FR-018's scope marker (how much 001-surface lands here).
3. `/speckit-plan` — Vite project scaffold, dev proxy + FastAPI static-serve integration,
   component map, the design-token system (the two palettes above), Motion patterns, and the
   parity migration order.
4. `/speckit-tasks` — ordered, independently-shippable tasks (P1 parity+identity → P2 motion →
   P3 orchestration surfaces).
