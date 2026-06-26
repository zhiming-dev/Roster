# Copilot Instructions

This file should describe how code is built and maintained in this repository.

## Coding Standards

- Follow existing repository style and naming conventions.
- Prefer consistency with nearby code over introducing new patterns.
- Keep classes and files focused on one responsibility where practical.

## Project Layout

Document your key folders here, for example:

- `src/` - application code
- `tests/` - automated tests
- `scripts/` - build and automation scripts
- `docs/` - product and engineering documentation

## Build and Test

Document the exact commands used by your project, for example:

```bash
<build command>
<test command>
```

## Repository-Specific Rules

Add concrete rules that reduce ambiguity, for example:

- Which abstractions are mandatory for data access
- Which modules own configuration loading
- Which APIs are deprecated and must not be used
- Required test strategy for changed code

## Change Quality Bar

- Favor minimal diff size for easier review.
- Add tests when behavior changes.
- Do not perform unrelated refactors in the same change.
- Avoid placeholder implementations unless explicitly requested.

## Security and Privacy

- Never hardcode secrets, keys, tokens, or credentials.
- Use approved secret management for runtime configuration.
- Avoid logging sensitive user or production data.
