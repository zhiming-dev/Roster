# Code change workflow

The Code change view runs this sequence:

Request → plan approval → Coder → Reviewer → tests → diff approval → downloadable patch.

## Use it

1. Install the runtime requirements and build the frontend as described in the runtime README.
2. Start the runtime and open the dashboard.
3. In Setup, save the absolute path of a clean Git repository under Code change workspace. Select Apply to new chat.
4. Configure one Coder with read, edit and execute tools, plus one Reviewer. Both need working model providers. The built in team already includes these roles.
5. Open Code change. Enter a concrete request and the repository's test command, for example `python3 verify.py` or `npm test`.
6. Review the proposed scope, acceptance criteria and exact test command. Select Approve plan and run.
7. Inspect the Reviewer findings, actual command output and diff. Select Approve diff and prepare patch to enable the download.

The command executes from the repository root as a single process. Use a repository script for multiple test steps. It must return a failing exit code when verification fails. A successful exit is evidence that this command passed, not proof of comprehensive test coverage.

## Guarantees in this flow

The Coder cannot start through this flow until its plan is approved. The Reviewer is instantiated with only the read tool and must return an explicit passing verdict before tests run. Test failure, missing commands, an empty change, oversized changes, protected fixture edits and changes to the reviewed patch all prevent delivery.

Both approval decisions identify a specific pending gate. Concurrent mutation requests receive HTTP 409. The final decision checks that the current patch still matches the patch reviewed and tested. The download serves an immutable artifact with a verified SHA256 digest. Binary changes are included. Git checks applicability against the exact base commit before requesting diff approval.

This workflow is available through Code change. The existing general chat orchestration remains a separate interface and does not gain these workflow guarantees.

## Persistence and recovery

Artifacts are stored under `runs/<runId>/change/`: the draft and approved plans, `workflow.json`, `review.md`, `tests.log` and, after diff approval, `delivery.patch`.

Reopening the conversation restores a pending plan, diff or Coder action decision. An interruption during coding, review, testing or action execution marks the workflow blocked instead of automatically repeating work. Inspect its preserved worktree and start a new chat with a revised request. Automatic retry and automatic repair of failed reviews are not implemented.

The new checkpoint uses the additive v1 workflow schema. Existing Plan and Task schemas are unchanged. The legacy provenance format is unchanged by this feature.

## Execution boundary

The worktree isolates ordinary edits from the target checkout. File tools enforce capability grants and protect supplied test fixtures. Command execution still runs as a local subprocess with the existing risk classifier; it is not an operating system sandbox. Use a disposable repository and trusted test commands for initial trials. Container isolation is a separate milestone.

## Verification

Run the Python test suite from `runtime/`, and frontend unit tests, build and lint from `frontend/`.

The browser test uses real FastAPI, React, Git, command execution and patch download, with scripted model replies and a temporary repository. It requires the runtime virtual environment, installed Playwright Chromium and a built frontend. From `frontend/`, run:

```sh
npx playwright test --config playwright.workflow.config.ts
```

Its dedicated local server listens on port 8876 and is stopped after the test. No external model account is used. Live model quality and completion reliability still require separate evaluation.
