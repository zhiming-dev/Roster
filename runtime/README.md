# Roster runtime — MVP

A small Python service that turns the markdown-first Roster agents (Planner, Coder,
E2E, QA/Validation, Reviewer, Researcher) into **actual running processes** backed by a
local Ollama daemon or Azure AI Foundry, and exposes:

- A **chat-with-Planner** endpoint (`POST /api/chat`) — the principal only ever talks
  to the Planner. The Planner dispatches to specialists.
- A **live dashboard** at <http://localhost:8765/> — a chat-history sidebar, a top
  **agent-lineage graph** that lights up the active edge when two agents are talking,
  a centered chat (your messages right, agents left), and a collapsible **inter-agent
  activity** side panel.
- A **WebSocket event stream** (`GET /ws`) — the live data the dashboard consumes.
- **Persistent chat history** in **SQLite** (`ROSTER_DB_PATH`, default
  `data/roster.db`) — every conversation and inter-agent event is saved, so you can
  reopen past chats from the sidebar and continue them.
- An **append-only provenance log** at `../runs/<runId>/provenance.jsonl`.

> This is an MVP. **Web search is wired up** (the Researcher and QA agents can really
> query the web), but most other tools are not yet — the Coder doesn't edit files and the
> E2E agent doesn't drive a real browser inside the runtime. What *is* wired up is the
> end-to-end **architecture**: per-agent provider binding, planner-only HITL surface,
> dispatch protocol, the shared LLM queue, and full observability. More tool execution is
> the next phase.

---

## 1. Prerequisites

- Python 3.10+
- [Ollama](https://ollama.com/) running locally (`ollama serve`)
- At least one model pulled. Default config uses `llama3.1:8b`:

  ```bash
  ollama pull llama3.1:8b
  ```

  You can mix models per agent (e.g. a code-specialized model for the Coder). See
  [`agents.config.yaml`](./agents.config.yaml).

## 2. Install

From this directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 3. Run

```powershell
python -m roster
```

Then open <http://localhost:8765/>.

On startup the runtime health-checks every agent (`GET /api/health`) and logs, per
agent, whether its provider endpoint is reachable and the configured model is present.

### The dashboard, at a glance

- **Left — history.** Every conversation is listed (newest first). Click one to reopen
  it (the Planner's history is restored so you can continue); **New chat** starts a
  fresh run; hover an item to delete it.
- **Top — agent lineage.** A horizontal graph of the agents. When the Planner dispatches
  a specialist (or one reports back), that edge animates and both nodes pulse; a node
  glows while it's `thinking` / `searching` / `queued`.
- **Center — chat.** You talk to the Planner. Your messages sit on the right, every
  agent reply on the left.
- **Right — inter-agent activity.** A collapsible panel (closed by default; open it with
  the **Activity** button) streaming dispatches, task results, web searches and errors.

### Run in Docker (with persistent SQLite history)

SQLite is file-based, so "running it in Docker" means the runtime container keeps its
`roster.db` on a mounted volume. From this directory:

```powershell
docker compose up --build
```

Then open <http://localhost:8765/>. Conversation history is written to the `roster-data`
volume and survives `docker compose down`; wipe it with `docker compose down -v`.

> The build context is the **repo root** (agents reference `../<role>-agent/*.agent.md`),
> which the provided [`docker-compose.yml`](./docker-compose.yml) sets for you. Put model
> secrets in the environment (e.g. `ROSTER_PLANNER_API_KEY`) or a `runtime/.env` file
> rather than committing them — the YAML already supports `${ENV_VAR}` expansion. If an
> agent points at a **local Ollama**, use `http://host.docker.internal:11434` as its
> endpoint so the container can reach the host daemon.

## 4. Try it

In the chat box, talk to the Planner the way the principal would:

> add a `/health` endpoint to the API, then E2E-test it

Open the **Activity** panel (top-right) and you'll see:

```
principal → planner          user.message
planner   → coder             task_assignment   "add a /health endpoint that returns 200"
coder     → planner           task_result       "Plan: add route in app.py …"
planner   → e2e               task_assignment   "smoke-test GET /health expecting 200"
e2e       → planner           task_result       "Steps I would run: open browser, …"
planner   → principal         message           "Done — coder proposed X, E2E validated Y."
```

Or try a research question to see the **web-search tool** in action:

> how did the 3 US indexes do on 2026-06-05 and what drove them?

The Planner dispatches to `researcher`, whose lineage node glows green (`searching`) while
live queries run; the queries and result URLs stream into the Activity panel as `search`
rows. The Planner can then have `qa` fact-check the synthesis before delivering it.

The Planner is told (via runtime system-prompt suffix) that it ends a reply with
`DISPATCH:<role>:<task>` when it needs a specialist. The orchestrator parses that
line, invokes the sub-agent, and feeds its reply back as the Planner's next user turn,
prefixed with `[<role> reports]:`.

## 5. Project layout

```
runtime/
├── agents.config.yaml          ← SINGLE centralized config (providers + queue)
├── requirements.txt
├── roster/
│   ├── __main__.py             ← `python -m roster` entry point
│   ├── config.py               ← loads YAML, expands ${ENV} secrets, parses .agent.md
│   ├── logging_setup.py        ← structured logging config
│   ├── queue.py                ← observable shared LLM queue (RequireQueue)
│   ├── search.py               ← web-search tool (DuckDuckGo no-key / Tavily)
│   ├── providers/              ← LLM provider package
│   │   ├── base.py             ← Provider protocol + ProviderError
│   │   ├── ollama.py           ← local Ollama backend
│   │   └── azure_foundry.py    ← Azure AI Foundry / Azure OpenAI backend
│   ├── agent.py                ← live Agent (provider + history + status + queue + SEARCH loop)
│   ├── orchestrator.py         ← planner-led dispatch loop, parses DISPATCH:
│   ├── bus.py                  ← in-process pub/sub (WebSocket fan-out)
│   ├── provenance.py           ← append-only JSONL writer
│   ├── store.py                ← SQLite persistence (conversations + event streams)
│   └── server.py               ← FastAPI app: /, /api/chat, /api/agents, /api/conversations, /ws
├── static/
│   └── app/                    ← built React SPA (Vite output; served at /) — the dashboard
├── Dockerfile                  ← runtime image (build context = repo root)
└── docker-compose.yml          ← run the app + persistent SQLite volume
```

> The `researcher` agent (in [`../researcher-agent/`](../researcher-agent/)) is the first
> Roster agent with a real tool wired up — web search. The planner dispatches
> live/external-fact questions to it instead of guessing.

### Dashboard frontend (Vite + React + TypeScript)

The dashboard is a **Vite + React + TypeScript** single-page app under
[`../frontend/`](../frontend/) (spec 002), using [Motion](https://motion.dev) for the springy
animations. The Python backend and its `/api/*` + `/ws` contract are unchanged — this is a
presentation layer that consumes them.

```powershell
cd ../frontend
npm install
npm run dev      # Vite dev server on http://localhost:5173, proxying /api + /ws → :8765
npm run build    # type-check + bundle → runtime/static/app/ (served by FastAPI at /)
npm run test     # Vitest unit tests
npm run lint     # ESLint
```

In production there is **no separate Node server**: `npm run build` emits the SPA into
`runtime/static/app/`, and FastAPI serves it at `/`. The Docker image builds the SPA in a
dedicated stage, so the container is self-contained; if you start the runtime without a build,
`/` shows a short "build the dashboard" page. For local UI work, run the Python runtime
(`python -m roster`) for the API and `npm run dev` for hot-reloading React against it.

## 6. Configuration

Everything lives in **one file** — [`agents.config.yaml`](./agents.config.yaml). Per
agent you set, directly there:

| field | applies to | meaning |
|---|---|---|
| `provider` | all | `ollama` or `azure_foundry` |
| `endpoint` | all | backend base URL |
| `model` | ollama | Ollama model name (e.g. `tinyllama:latest`) |
| `deployment` | azure | Azure deployment name (falls back to `model`) |
| `api_key` | azure | secret — use `${ENV_VAR}`, never a literal |
| `api_version` | azure | Azure REST `api-version` |
| `options` | all | `temperature`, `num_predict`/`max_tokens`, … |

`defaults:` are inherited by every agent; any agent may override any field.

> **Built-in fallback.** You don't have to create `agents.config.yaml` to get started: if it
> is absent, the runtime (and the in-app **Setup** page) fall back to the committed
> [`agents.config.example.yaml`](./agents.config.example.yaml) — the repo's built-in team
> (planner/coder/qa/researcher/…). The first edit you save in Setup materializes your own
> `agents.config.yaml` from that template, leaving the example untouched. Secrets entered in
> Setup are written to a gitignored `.env` and referenced from the YAML as `${VAR}`.

### Using Azure AI Foundry

Point any agent at a Foundry deployment by overriding its provider block:

```yaml
agents:
  planner:
    agent_file: ../planner-agent/planner.agent.md
    role: planner
    provider: azure_foundry
    endpoint: https://YOUR-RESOURCE.services.ai.azure.com   # or *.openai.azure.com
    deployment: gpt-4o-mini
    api_key: ${AZURE_FOUNDRY_API_KEY}
    api_version: "2024-05-01-preview"
    options: { temperature: 0.2, max_tokens: 800 }
```

Then export the key before starting (it is **never** stored in the YAML or returned by
the API):

```powershell
$env:AZURE_FOUNDRY_API_KEY = "<your-key>"
python -m roster
```

The URL convention is auto-detected: `*.openai.azure.com` uses the Azure OpenAI
`/openai/deployments/<name>/chat/completions` path; everything else uses the Foundry
model-inference `/models/chat/completions` path. You can mix providers freely — e.g. a
cloud planner with local Ollama specialists.

### Shared LLM queue (one key, many agents)

When several agents share **one** backend / API key, hitting it concurrently causes
rate-limit errors (cloud) or memory thrash (local). The `queue` block serializes the
agents you list:

```yaml
queue:
  max_concurrency: 1          # how many queued calls may run at once
  require_queue:              # these agents must wait their turn
    - planner
    - coder
    - e2e
    - reviewer
    - qa
    - researcher
```

Agents in `require_queue` go through a FIFO queue admitting at most `max_concurrency`
calls at a time; the rest call the model directly. An agent waiting for a slot reports
the **`queued`** status (with how many are ahead), which is rendered on the dashboard
agent card and in the live `queue:` meter in the header — full observability of the
wait state. Raise `max_concurrency` once you move off a single shared key.

### Web search (the researcher's tool)

Agents granted `tools: [search]` can search the web. The `researcher` agent has it by
default, so the planner can dispatch live-fact questions ("how did the indexes do on
2026-06-05?") instead of hallucinating. Configure the backend in the `search` block:

```yaml
search:
  enabled: true
  provider: auto          # auto | duckduckgo | tavily | none
  # api_key: ${TAVILY_API_KEY}
  max_results: 5
```

- **`auto`** (default) → **DuckDuckGo**, which needs **no API key** and works out of the
  box. If a `TAVILY_API_KEY` env var (or `search.api_key`) is present, it auto-upgrades to
  **Tavily** (cleaner, more reliable results).
- **`duckduckgo`** → force the no-key backend.
- **`tavily`** → force Tavily (needs a key from [tavily.com](https://tavily.com)).
- **`none`** → disable search entirely.

Mechanically: when a search-enabled agent ends a reply with `SEARCH: <query>`, the runtime
runs the query, feeds results back as the next turn, and lets the agent continue (up to 3
searches per turn). The agent's card shows a green **`searching`** status while a query is
in flight, and every query + result set streams to the dashboard event feed as
`🌐 search` rows — full observability. The agents are instructed to cite result URLs and
to never fabricate when search returns nothing.

### Per-agent env overrides

Without editing the file:

```powershell
$env:ROSTER_PLANNER_PROVIDER = "azure_foundry"
$env:ROSTER_PLANNER_ENDPOINT = "https://r.services.ai.azure.com"
$env:ROSTER_PLANNER_DEPLOYMENT = "gpt-4o-mini"
$env:ROSTER_PLANNER_API_KEY = "<key>"
$env:ROSTER_CODER_MODEL = "qwen2.5-coder:7b"
python -m roster
```

## 7. Provenance

Every run gets a fresh id (`run_YYYY-MM-DD_<hex>`). The orchestrator writes events
(`principal.message`, `planner.reply`, `task.dispatched`, `task.result`, …) to:

```
../runs/<runId>/provenance.jsonl
```

This is the same JSONL contract documented in
[`../shared/provenance/SKILL.md`](../shared/provenance/SKILL.md) and used by the
research harness for replay.

## 8. Troubleshooting

### My machine froze the moment I sent a message

Almost always one of:

1. **`num_ctx` was overridden to a value larger than the model needs.** Direct
   `ollama run` uses the model's native context (e.g. 2048 for tinyllama), but our
   HTTP calls let you set `options.num_ctx`. A bigger context → much bigger KV-cache
   buffer → on consumer hardware, Windows pages it to disk and the whole system
   freezes. The default `agents.config.yaml` no longer sets `num_ctx`; let Ollama
   pick.
2. **Your model doesn't fit in RAM/VRAM.** Check Task Manager during the first
   inference. If "In use" memory spikes and "Available" drops to zero, the model
   is too big. Try `tinyllama` or `phi3:mini` first.
3. **System prompt is too long for the model.** The full `.agent.md` is loaded as
   the system prompt — that's 1500-2500 tokens. For tiny models, set
   `system_prompt_max_chars: 1500` in `agents.config.yaml` (under `defaults:` or
   per-agent) to truncate.

The runtime now serializes **all** Ollama calls per endpoint (process-wide async
lock in [`roster/agent.py`](./roster/agent.py)), so even if multiple chat
requests overlap, only one inference runs at a time. This is the single most
important safeguard against thrash on a local machine.

### Dashboard shows `[error] Unexpected token 'I', "Internal S"...`

That was the pre-fix server returning plain-text `Internal Server Error`. After
this release, all errors come back as JSON. If you still see one, look at the
terminal — the orchestrator now publishes `runtime.error` events to the
dashboard's event feed too.

### `Ollama returned 404 for model 'X'`

You haven't pulled it. `ollama pull X`.

### `Ollama timed out after 90s`

Either the model is paging to disk (see #1 above) or the prompt eval is genuinely
that slow. Reduce `system_prompt_max_chars`, switch to a smaller model, or raise
`request_timeout_s` in the config if you genuinely need a long inference.

## 9. What's intentionally missing in MVP

| Feature | Status | Where it goes next |
|---|---|---|
| Web search tool | ✅ DuckDuckGo (no key) / Tavily | More backends (Bing, Brave, Azure grounding) behind the same `SearchProvider`. |
| Real tool execution (file edits, shell, browser) | ❌ | Sub-agents need a sandboxed tool layer. Coder talks about edits but doesn't make them. |
| Approval Gate UI | ❌ (logged only) | T3/T4 dispatches should pop a confirm in the dashboard before the sub-agent is called. |
| Streaming responses | ❌ | Ollama supports it; swap `stream=False` and pipe chunks over the WebSocket. |
| Council deliberation | ❌ | Wire a `convene_council()` path that fans the same prompt to multiple providers. |
| Cloud providers | ✅ Azure AI Foundry / Azure OpenAI | Add OpenAI / Anthropic / Gemini behind the same `Provider` protocol in `providers/`. |
| Shared-resource queue | ✅ `queue.require_queue` | Per-backend queues, priority lanes, token-bucket rate limiting. |
| Persistent chat history | ✅ SQLite (`data/roster.db`) | Conversations + inter-agent events persist; reopen & continue past chats from the sidebar. |
| Multi-turn sub-agent memory | partial | The Planner's history is restored when reopening a chat; sub-agent histories are not (yet). |

## 10. Why this shape

The user-facing surface is **one agent** (the Planner) because that is exactly the
guarantee the framework promises the principal: *one place to give intent, one place
to get accountability*. Sub-agents are an implementation detail of how the Planner
gets the work done — visible in the dashboard for trust and debugging, but never the
party the human negotiates with.
