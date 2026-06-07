---
name: e2e-runner
description: "Run E2E test suites using playwright-cli. Use when: running test suites, executing smoke tests, running E2E/bug-bash tests, generating test reports, testing UI with plain-English test definitions. Dispatched after the Coder lands a change."
argument-hint: 'Suite name and optional flags, e.g. "smoke --env test --headed"'
---

# E2E Test Runner

Run plain-English E2E test definitions against a live web app using `playwright-cli`.

## When to Use

- User asks to run a test suite (smoke, contracts, datasets, navigation, feedback, critical, pre-release, full)
- User asks to run a specific test or tests by tag/folder
- User asks to list available suites or environments
- User asks to generate a test report

## Prerequisites

- `playwright-cli` must be installed and on PATH (`npm install -g @anthropic-ai/playwright-cli` or `npx playwright-cli`)
- The target web application must be running (or accessible at the target environment URL)

## Available Commands Reference

See [playwright-cli command reference](./references/playwright-cli.md) for the full list of commands.

## User-Provided Files

Users only need to provide three things inside `e2e-test/`:

```
e2e-test/
├── environments.json              # env name → baseUrl mapping
├── suites/*.json                  # suite definitions (tags, folders, or explicit tests)
├── test-definitions/**/*.json     # plain-English test steps + pass criteria
└── test-results/                  # output directory (agent writes here)
```

No Node.js scripts or `package.json` are required. The agent resolves suites, executes tests, and generates the HTML report directly.

## Inputs Are Read-Only

Files under the following paths are **test inputs** and MUST NOT be modified
during a test run, regardless of what you observe on the page:

- `e2e-test/test-definitions/**`
- `e2e-test/suites/**`
- `e2e-test/environments.json`

These files capture developer intent. Silently editing a `passCriteria`,
step, tag, or environment URL to make a test pass — or to match what the UI
currently shows — defeats the purpose of the test suite. If a test
definition appears wrong, **let the test fail** and surface the discrepancy
in the `evidence` field of the result. The developer can then decide whether
to update the test definition.

The agent may only write to:

- `e2e-test/test-results/**`
- `e2e-test/failure-screenshots/**`

If the user explicitly asks you to update a test definition outside of a
test run, that is fine — but never do it as a side effect of executing tests.

## Procedure

### Step 0: Parse the User Request

Extract from the user's message:

- **Suite name**: e.g. `smoke`, `contracts`, `pre-release`, `full`
- **Environment**: `localhost`, `test`, `sandbox`, `sandboxtwo` (default: `localhost`)
- **Flags**: `--headed` (always use), `--tag <tag>`, `--folder <folder>`, `--all`

If the user asks to **list suites**, read all JSON files in `e2e-test/suites/` and display their `name` and `description` fields.

If the user asks to **list environments**, read `e2e-test/environments.json` and display the env keys and their `baseUrl` values.

### Step 1: Resolve the Suite and Base URL

1. **Resolve base URL**: Read `e2e-test/environments.json` and look up the `baseUrl` for the requested environment key.

2. **Read the suite**: Read `e2e-test/suites/<suite-name>.json`.

3. **Resolve test definitions**: Read all JSON files recursively from `e2e-test/test-definitions/`. For each file, note its subfolder (e.g. `smoke/page-loads.json` has folder `smoke`) and its `tags` array.

4. **Filter tests** based on the suite config:
   - If suite has `tags`: include all test definitions where the test's `tags` array contains **any** of the suite's tags. Deduplicate by file path.
   - If suite has `folders`: include all test definitions whose subfolder matches any of the suite's folders.
   - If suite has `tests`: include only the test definitions at the explicit file paths listed.

**Suite format:**

```json
{
  "name": "Smoke Tests",
  "description": "Quick sanity checks...",
  "tags": ["smoke"]
}
```

**Test definition format:**

```json
{
  "name": "Page loads with correct title",
  "steps": [
    "Navigate to {{BASE_URL}}",
    "Wait for the page to fully load",
    "Check the page title"
  ],
  "passCriteria": "The page title should contain 'Data Contract'",
  "tags": ["smoke", "critical"]
}
```

### Step 2: Open the Browser

```bash
# Kill any stale sessions first
playwright-cli kill-all

# Open browser with persistent profile (reuses auth cookies)
playwright-cli -s=bugbash open <baseUrl> --persistent --headed
```

Wait for the page to load, then take an initial snapshot:

```bash
playwright-cli -s=bugbash snapshot
```

Read the snapshot YAML file to verify the page loaded.

### Step 3: Execute Each Test

For each test definition, execute this loop:

#### 3a. Execute Each Step

For each step in the test's `steps` array:

1. **Read the current snapshot** to understand the page state
2. **Interpret the step** — translate the plain English into playwright-cli commands:
   - `"Navigate to {{BASE_URL}}"` → `playwright-cli -s=bugbash goto <baseUrl>`
   - `"Click on 'My contracts' in the sidebar"` → find the element in the snapshot YAML with matching text, use its `[ref=eNN]` → `playwright-cli -s=bugbash click eNN`
   - `"Wait for the page to load"` → `playwright-cli -s=bugbash snapshot` (take a fresh snapshot after a brief pause)
   - `"Type 'test' into the search box"` → find the input in snapshot → `playwright-cli -s=bugbash fill eNN "test"`
   - `"Look for..."` / `"Observe..."` / `"Verify..."` → observation step, just take a snapshot and check
3. **Execute the command(s)** in the terminal
4. **Take a new snapshot** after each action: `playwright-cli -s=bugbash snapshot`
5. **Read the snapshot file** to confirm the action succeeded
6. **Record the result**: step text, pass/fail, what you did, timing

**CRITICAL**: Always read the snapshot YAML to find element refs. Never guess or reuse refs from a previous snapshot — the page may have changed.

#### 3b. Evaluate Pass Criteria

After all steps complete:

1. Take a final snapshot: `playwright-cli -s=bugbash snapshot`
2. Read the snapshot YAML file
3. Evaluate each condition in `passCriteria` against what you see in the snapshot
4. For each criterion, note whether it's met and cite the evidence from the snapshot
5. The test passes only if ALL criteria are met AND all steps succeeded

##### CRITICAL — Criterion Fidelity (do not violate)

The `passCriteria` string captures **developer intent**. Silently rewriting it
to match what the page actually shows defeats the entire purpose of the test.
The following rules are non-negotiable:

1. **Verbatim copy.** The `criterion` field written to `results.json` MUST have the
   exact same string content/value as stored in the `passCriteria` field of the test definition
   file. Do **not** paraphrase, fix typos, correct casing, normalize quotes,
   substitute synonyms, or "clean up" the wording — even if it is obviously
   wrong, ambiguous, or contains a typo.

2. **Evaluate literally.** Match the criterion against the snapshot exactly as
   written. If `passCriteria` says `"An 'Add Chart' button should be visible"`
   and the page contains an "Add filter" button (but no "Add Chart" button),
   the criterion is **NOT met**. Mark `met: false`. Do not infer intent, do
   not match on similarity, do not assume it is a typo, do not "help" the
   author by accepting a near-match.

3. **Evidence reports reality.** The `evidence` field describes what you
   actually saw on the page. It is the only place where you may note a
   discrepancy (e.g. *"No 'Add Chart' button found. An 'Add filter' button
   [ref=e156] is present — possible typo in test definition"*). The criterion
   text itself stays untouched and the test still fails.

4. **Failures are signal, not noise.** A failing test caused by a stale or
   incorrect `passCriteria` is a *correct* outcome — it tells the developer
   the test definition needs human review. Never convert such a failure into
   a pass by editing the criterion.

If you find yourself wanting to change a criterion's wording to make a test
pass, stop — that is the bug this rule exists to prevent.

#### 3c. Screenshot on Failure

If a test fails:

```bash
mkdir -p e2e-test/failure-screenshots
playwright-cli -s=bugbash screenshot --filename=failure-screenshots/fail-<test-name>.png
```

### Step 4: Generate the Report

After all tests complete, generate both the results JSON and the HTML report directly — no Node.js scripts are needed.

#### 4a. Write results.json

Write the results JSON to `e2e-test/test-results/results.json` with this structure:

```json
{
  "suiteName": "Smoke Tests",
  "suiteDescription": "Quick sanity checks...",
  "baseUrl": "http://localhost:3000/...",
  "startedAt": "2026-03-30T10:00:00.000Z",
  "durationMs": 42000,
  "results": [
    {
      "name": "Page loads with correct title",
      "path": "smoke/page-loads.json",
      "tags": ["smoke", "critical"],
      "pass": true,
      "criteria": {
        "pass": true,
        "checks": [
          {
            "criterion": "Page title contains 'Data Contract'",
            "met": true,
            "evidence": "Page title is 'Data Contract - Datasets'"
          }
        ]
      },
      "steps": [
        {
          "text": "Navigate to the base URL",
          "ok": true,
          "action": "goto",
          "detail": "Navigated to http://localhost:3000/...",
          "durationMs": 3200
        }
      ],
      "screenshot": null,
      "durationMs": 8500
    }
  ]
}
```

For failed test screenshots, convert the PNG to a base64 data URI for the `screenshot` field:

```
data:image/png;base64,<base64-encoded-png>
```

#### 4b. Generate report.html

Write a self-contained HTML file to `e2e-test/test-results/report.html`. The file must follow this **exact** structure — do not deviate from the CSS class names, element nesting, or JavaScript.

Compute these values from `results.json` before generating:

- `PASSED` = count of results where `pass === true`
- `FAILED` = total − PASSED
- `PASS_PCT` = `(PASSED / total * 100)` (or 0 if total is 0)
- `FAIL_PCT` = `(FAILED / total * 100)` (or 0 if total is 0)
- `DURATION` = human-readable duration from `durationMs` (e.g. `42.3s`, `2m 15s`)
- `DATE` = formatted date from `startedAt` (e.g. `Thu, Apr 24, 2026`)
- `TIME` = formatted time from `startedAt` in 24h format (e.g. `14:30:05`)

**Full HTML structure:**

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>SUITE_NAME — Test Report</title>
    <style>
      :root {
        --pass: #34d058;
        --pass-bg: #e6f9ed;
        --pass-border: #b7ebc6;
        --fail: #e05d44;
        --fail-bg: #fde8e8;
        --fail-border: #f5c6c6;
        --bg: #f8f9fa;
        --card-bg: #ffffff;
        --text: #1a1a1a;
        --text-dim: #6b7280;
        --border: #e5e7eb;
        --radius: 8px;
        --shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
        --font:
          -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica,
          Arial, sans-serif;
      }
      * {
        box-sizing: border-box;
        margin: 0;
        padding: 0;
      }
      body {
        font-family: var(--font);
        background: var(--bg);
        color: var(--text);
        line-height: 1.5;
      }
      .root {
        max-width: 960px;
        margin: 0 auto;
        padding: 24px 16px;
      }
      .header {
        background: var(--card-bg);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        padding: 24px;
        margin-bottom: 24px;
        box-shadow: var(--shadow);
      }
      .header-top {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        flex-wrap: wrap;
        gap: 8px;
      }
      .suite-name {
        font-size: 22px;
        font-weight: 700;
      }
      .header-meta {
        display: flex;
        gap: 12px;
        color: var(--text-dim);
        font-size: 13px;
      }
      .meta-item {
        white-space: nowrap;
      }
      .suite-desc {
        color: var(--text-dim);
        margin-top: 4px;
        font-size: 14px;
      }
      .suite-url {
        color: var(--text-dim);
        margin-top: 4px;
        font-size: 13px;
      }
      .suite-url code {
        background: #f1f3f5;
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 12px;
      }
      .summary-bar {
        margin-top: 16px;
      }
      .summary-counts {
        display: flex;
        gap: 12px;
        margin-bottom: 8px;
      }
      .count {
        font-size: 14px;
        font-weight: 600;
      }
      .count.total {
        color: var(--text);
      }
      .count.passed {
        color: var(--pass);
      }
      .count.failed {
        color: var(--fail);
      }
      .progress-bar {
        height: 8px;
        border-radius: 4px;
        background: var(--border);
        display: flex;
        overflow: hidden;
      }
      .progress-pass {
        background: var(--pass);
        transition: width 0.3s;
      }
      .progress-fail {
        background: var(--fail);
        transition: width 0.3s;
      }
      .test-list {
        display: flex;
        flex-direction: column;
        gap: 8px;
      }
      .test-card {
        background: var(--card-bg);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        box-shadow: var(--shadow);
        overflow: hidden;
      }
      .test-card.fail {
        border-left: 4px solid var(--fail);
      }
      .test-card.pass {
        border-left: 4px solid var(--pass);
      }
      .test-header {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 12px 16px;
        cursor: pointer;
        user-select: none;
        transition: background 0.15s;
      }
      .test-header:hover {
        background: #f9fafb;
      }
      .test-status-icon {
        font-weight: 700;
        font-size: 16px;
        width: 22px;
        text-align: center;
        flex-shrink: 0;
      }
      .test-status-icon.pass {
        color: var(--pass);
      }
      .test-status-icon.fail {
        color: var(--fail);
      }
      .test-name {
        font-weight: 600;
        font-size: 14px;
        flex: 1;
      }
      .test-tags {
        display: flex;
        gap: 4px;
        flex-wrap: wrap;
      }
      .tag {
        background: #eef2ff;
        color: #4338ca;
        font-size: 11px;
        padding: 2px 8px;
        border-radius: 12px;
        font-weight: 500;
        white-space: nowrap;
      }
      .test-duration {
        color: var(--text-dim);
        font-size: 12px;
        font-variant-numeric: tabular-nums;
        white-space: nowrap;
      }
      .test-chevron {
        font-size: 18px;
        color: var(--text-dim);
        transition: transform 0.2s;
        flex-shrink: 0;
      }
      .test-chevron.open {
        transform: rotate(90deg);
      }
      .test-body {
        display: none;
        padding: 0 16px 16px;
        border-top: 1px solid var(--border);
      }
      .test-body.open {
        display: block;
      }
      .section {
        margin-top: 16px;
      }
      .section-title {
        font-size: 13px;
        font-weight: 600;
        color: var(--text-dim);
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 8px;
      }
      .ai-badge {
        background: linear-gradient(135deg, #667eea, #764ba2);
        color: #fff;
        font-size: 10px;
        padding: 2px 8px;
        border-radius: 10px;
        text-transform: none;
        letter-spacing: 0;
        font-weight: 600;
        vertical-align: middle;
        margin-left: 6px;
      }
      .step-list {
        list-style: none;
        counter-reset: step;
      }
      .step-item {
        display: flex;
        align-items: flex-start;
        gap: 8px;
        padding: 6px 0;
        border-bottom: 1px solid #f3f4f6;
        font-size: 13px;
      }
      .step-item:last-child {
        border-bottom: none;
      }
      .step-icon {
        width: 18px;
        text-align: center;
        flex-shrink: 0;
        font-weight: 700;
      }
      .step-item.pass .step-icon {
        color: var(--pass);
      }
      .step-item.fail .step-icon {
        color: var(--fail);
      }
      .step-text {
        flex: 1;
      }
      .step-detail {
        color: var(--text-dim);
        font-size: 12px;
        max-width: 350px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .step-time {
        color: var(--text-dim);
        font-size: 11px;
        white-space: nowrap;
      }
      .criteria-list {
        list-style: none;
      }
      .criteria-item {
        padding: 8px 0;
        border-bottom: 1px solid #f3f4f6;
        font-size: 13px;
      }
      .criteria-item:last-child {
        border-bottom: none;
      }
      .criteria-icon {
        font-weight: 700;
        margin-right: 6px;
      }
      .criteria-item.pass .criteria-icon {
        color: var(--pass);
      }
      .criteria-item.fail .criteria-icon {
        color: var(--fail);
      }
      .criteria-evidence {
        color: var(--text-dim);
        font-size: 12px;
        margin-top: 2px;
        padding-left: 24px;
        font-style: italic;
      }
      .screenshot-container {
        border: 1px solid var(--border);
        border-radius: var(--radius);
        overflow: hidden;
        max-width: 100%;
      }
      .screenshot {
        width: 100%;
        height: auto;
        display: block;
      }
      .footer {
        text-align: center;
        color: var(--text-dim);
        font-size: 12px;
        margin-top: 32px;
        padding-top: 16px;
        border-top: 1px solid var(--border);
      }
      .test-card.fail .test-body {
        display: block;
      }
      .test-card.fail .test-chevron {
        transform: rotate(90deg);
      }
    </style>
  </head>
  <body>
    <div class="root">
      <header class="header">
        <div class="header-top">
          <h1 class="suite-name">SUITE_NAME</h1>
          <div class="header-meta">
            <span class="meta-item">DATE</span>
            <span class="meta-item">TIME</span>
            <span class="meta-item">DURATION</span>
          </div>
        </div>
        <p class="suite-desc">SUITE_DESCRIPTION</p>
        <p class="suite-url">Base URL: <code>BASE_URL</code></p>
        <div class="summary-bar">
          <div class="summary-counts">
            <span class="count total">TOTAL tests</span>
            <span class="count passed">PASSED passed</span>
            <!-- Only include this span if FAILED > 0 -->
            <span class="count failed">FAILED failed</span>
          </div>
          <div class="summary-progress">
            <div class="progress-bar">
              <div class="progress-pass" style="width:PASS_PCT%"></div>
              <div class="progress-fail" style="width:FAIL_PCT%"></div>
            </div>
          </div>
        </div>
      </header>
      <div class="test-list">
        <!-- REPEAT THIS BLOCK for each test result (index = 0-based) -->
        <div class="test-card pass" data-index="0">
          <div class="test-header" onclick="toggle(0)">
            <span class="test-status-icon pass">✓</span>
            <span class="test-name">TEST_NAME</span>
            <span class="test-tags"
              ><span class="tag">tag1</span> <span class="tag">tag2</span></span
            >
            <span class="test-duration">8.5s</span>
            <span class="test-chevron" id="chevron-0">›</span>
          </div>
          <div class="test-body" id="body-0">
            <div class="section">
              <h3 class="section-title">Steps</h3>
              <ol class="step-list">
                <!-- One li per step -->
                <li class="step-item pass">
                  <span class="step-icon">✓</span>
                  <span class="step-text">STEP_TEXT</span>
                  <span class="step-detail">DETAIL</span>
                  <span class="step-time">3.2s</span>
                </li>
              </ol>
            </div>
            <div class="section">
              <h3 class="section-title">
                Pass Criteria <span class="ai-badge">AI evaluation</span>
              </h3>
              <ul class="criteria-list">
                <!-- One li per criterion check -->
                <li class="criteria-item pass">
                  <span class="criteria-icon">✓</span>
                  <span class="criteria-text">CRITERION_TEXT</span>
                  <div class="criteria-evidence">EVIDENCE_TEXT</div>
                </li>
              </ul>
            </div>
            <!-- Only include screenshot section if screenshot is not null -->
            <div class="section">
              <h3 class="section-title">Screenshot</h3>
              <div class="screenshot-container">
                <img
                  class="screenshot"
                  src="data:image/png;base64,..."
                  alt="Test screenshot"
                  loading="lazy"
                />
              </div>
            </div>
          </div>
        </div>
        <!-- END REPEAT -->
      </div>
      <footer class="footer">
        Generated by <strong>e2e-runner</strong> AI-powered executor
        &middot; GENERATED_AT_ISO
      </footer>
    </div>
    <script>
      function toggle(idx) {
        var body = document.getElementById("body-" + idx);
        var chevron = document.getElementById("chevron-" + idx);
        body.classList.toggle("open");
        chevron.classList.toggle("open");
      }
    </script>
  </body>
</html>
```

**Key rules when generating:**

- Use `class="test-card pass"` + `class="test-status-icon pass"` + icon `✓` for passing tests
- Use `class="test-card fail"` + `class="test-status-icon fail"` + icon `✗` for failing tests
- For steps: `class="step-item pass"` with `✓`, or `class="step-item fail"` with `✗`
- For criteria: `class="criteria-item pass"` with `✓`, or `class="criteria-item fail"` with `✗`
- Omit the `<span class="count failed">` line entirely when FAILED is 0
- Omit the `<p class="suite-desc">` line if suite has no description
- Omit the screenshot `<div class="section">` block if `screenshot` is null
- Include the `step-detail` span only if the step has a `detail` field
- Include the `step-time` span only if the step has a `durationMs` field
- Include the `criteria-evidence` div only if the check has an `evidence` field
- HTML-escape all user-provided text (`&` → `&amp;`, `<` → `&lt;`, `>` → `&gt;`, `"` → `&quot;`)
- The `data-index`, `onclick`, `id="chevron-N"`, and `id="body-N"` must use the 0-based result index

Write the completed HTML to `e2e-test/test-results/report.html`.

### Step 5: Cleanup and Report

1. Close the browser: `playwright-cli -s=bugbash close`
2. Tell the user the results: total passed/failed, duration
3. Let the user know the report is at `e2e-test/test-results/report.html`

## Output Format

While running, provide a live summary for each test:

```
[1/4] Page loads with correct title  #smoke #critical
  ├─ Step 1: Navigate to base URL ✓
  ├─ Step 2: Wait for page to load ✓
  ├─ Step 3: Check page title ✓
  ├─ Criteria: Page title contains 'Data Contract' ✓ (title: "Data Contract - Datasets")
  └─ Result: PASS (3.2s)
```

At the end, provide a summary:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  4 passed, 0 failed  (42.3s)
  Report: e2e-test/test-results/report.html
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## Tips

- If `playwright-cli` is not found globally, try `npx playwright-cli`
- The `--persistent` flag reuses browser profile cookies, which avoids re-authentication (important for Microsoft SSO)
- After navigation actions (`goto`, `click` on a link), always wait briefly and take a fresh snapshot before the next step
- If an element can't be found in the snapshot, the step fails — report it clearly and move to the next test
