---
description: "Task list template for feature implementation"
---

# Tasks: [FEATURE NAME]

**Input**: Design documents from `/specs/[###-feature-name]/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Test tasks are OPTIONAL - include them only if explicitly requested in the spec.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3...)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

- [ ] T001 Create project structure per implementation plan
- [ ] T002 Initialize [language] project with [framework] dependencies
- [ ] T003 [P] Configure linting and formatting tools

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T004 Setup data schema / migration framework
- [ ] T005 [P] Implement auth framework (if applicable)
- [ ] T006 Create base models/entities all stories depend on
- [ ] T007 Configure error handling and logging

**Checkpoint**: Foundation ready - user story implementation can begin.

---

## Phase 3: User Story 1 - [Title] (Priority: P1) 🎯 MVP

**Goal**: [What this story delivers]

**Independent Test**: [How to verify this story works on its own]

- [ ] T010 [P] [US1] Create [Entity] model in src/models/[entity]
- [ ] T011 [US1] Implement [Service] in src/services/[service]
- [ ] T012 [US1] Implement [endpoint/feature]
- [ ] T013 [US1] Add validation and error handling

**Checkpoint**: User Story 1 fully functional and testable independently.

---

## Phase 4: User Story 2 - [Title] (Priority: P2)

**Goal**: [What this story delivers]

- [ ] T020 [P] [US2] Create [Entity] model
- [ ] T021 [US2] Implement [Service]
- [ ] T022 [US2] Implement [endpoint/feature]

**Checkpoint**: User Stories 1 and 2 both work independently.

---

## Phase N: Polish & Cross-Cutting Concerns

- [ ] TXXX [P] Documentation updates
- [ ] TXXX Code cleanup and refactoring
- [ ] TXXX [P] Additional unit tests (if requested)
- [ ] TXXX Security hardening

---

## Dependencies & Execution Order

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup. BLOCKS all user stories.
- **User Stories (Phase 3+)**: Depend on Foundational; can run in parallel if staffed.
- **Polish (Final)**: Depends on desired user stories being complete.

### Within Each User Story

- Tests (if included) written and failing before implementation
- Models before services
- Services before endpoints
- Story complete before moving to next priority
