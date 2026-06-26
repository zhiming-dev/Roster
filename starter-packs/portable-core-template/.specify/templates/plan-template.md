# Implementation Plan: [FEATURE]

**Branch**: `[###-feature-name]` | **Date**: [DATE] | **Spec**: [link]

**Input**: Feature specification from `/specs/[###-feature-name]/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command.

## Summary

[Primary requirement + technical approach from research]

## Technical Context

**Language/Version**: [e.g., Python 3.11, TypeScript 5.x, Go 1.22 or NEEDS CLARIFICATION]

**Primary Dependencies**: [e.g., FastAPI, React, gRPC or NEEDS CLARIFICATION]

**Storage**: [e.g., PostgreSQL, SQLite, files or N/A]

**Testing**: [e.g., pytest, Jest, go test or NEEDS CLARIFICATION]

**Target Platform**: [e.g., Linux server, browser, mobile or NEEDS CLARIFICATION]

**Project Type**: [e.g., library/cli/web-service/desktop-app or NEEDS CLARIFICATION]

**Performance Goals**: [domain-specific or NEEDS CLARIFICATION]

**Constraints**: [domain-specific or NEEDS CLARIFICATION]

**Scale/Scope**: [domain-specific or NEEDS CLARIFICATION]

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

[Gates determined based on `.specify/memory/constitution.md`]

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
src/
├── models/
├── services/
└── lib/

tests/
├── integration/
└── unit/
```

**Structure Decision**: [Document the selected structure and reference real directories]

## Complexity Tracking

> Fill ONLY if Constitution Check has violations that must be justified.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [example] | [current need] | [why simpler approach is insufficient] |
