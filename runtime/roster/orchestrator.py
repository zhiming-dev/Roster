"""Orchestrator — turns one principal message into a planner-led multi-agent exchange."""

from __future__ import annotations

import asyncio
import datetime as _dt
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any

from . import events
from .agent import Agent
from .bus import bus
from .config import RuntimeConfig, load_config
from .diffutil import summarize_diff
from .protocol import parse_planner_turn
from .provenance import ProvenanceLog, new_run_id, runs_dir
from .queue import LlmQueue
from .run_state import OrchestrationState, RunStatus, TurnResult
from .search import SearchProvider, build_search_provider
from .task_result import build_task_result, new_task_id, write_diff_artifact, write_task_result
from .tools import ToolExecutor
from .workspace import Worktree, WorkspaceError, WorkspaceManager

log = logging.getLogger("roster.orchestrator")


def runtime_preamble(*, can_search: bool = False, has_searcher: bool = False) -> str:
    """A dynamic preamble prepended to every agent's system prompt.

    Two jobs: (1) tell the model what *today* is, so a model whose training data
    predates the system clock stops treating recent dates as "the future"; and
    (2) describe the agent's *actual* tool situation so it neither fabricates data
    nor — just as bad — refuses to use a tool it genuinely has.

    The tool paragraph is tailored to the agent:

    * ``can_search`` — this agent holds the web-search tool itself (its `SEARCH:`
      usage is spelled out later in the suffix). It must USE it for live facts.
    * ``has_searcher`` — this agent can't search directly but can DISPATCH to a
      specialist that can (the Planner's case).
    * neither — genuinely tool-less; it must say so rather than invent data.
    """
    now = _dt.datetime.now().astimezone()
    date_part = (
        "## Current context\n\n"
        f"The current date is {now:%Y-%m-%d} ({now:%A}). Treat this as *today*. "
        "Any date on or before today is in the PAST — never call a past or present "
        "date 'the future'.\n\n"
    )
    if can_search:
        tools_part = (
            "You DO have a **web-search tool** in this runtime (its `SEARCH:` usage is "
            "described below). USE it whenever a request needs live or external facts "
            "(news, market prices, weather, scores, recent events) — never claim you "
            "lack web access. You do NOT have a file system, code execution, or other "
            "live data feeds. Base every factual claim on actual search results and "
            "cite their URLs; if a search returns nothing or fails, say so plainly and "
            "DO NOT invent numbers, quotes, headlines, or citations."
        )
    elif has_searcher:
        tools_part = (
            "You have no tools you invoke directly, but you CAN dispatch to specialists "
            "that have a real web-search tool (see the dispatch menu below). For any "
            "live or external fact (news, market prices, weather, scores, recent "
            "events), DISPATCH to a web-searching specialist rather than answering from "
            "memory — and never tell the principal the system 'cannot' search, because "
            "it can. Do NOT invent specific numbers, quotes, headlines, or citations "
            "yourself; let the specialist gather them."
        )
    else:
        tools_part = (
            "You have **no tools** in this runtime: no web/internet access, no file "
            "system, no code execution, no live data feeds. You therefore CANNOT look "
            "up real-time or external facts (market prices, news, weather, scores, "
            "etc.). If a request needs such data, say so plainly and DO NOT invent "
            "specific numbers, quotes, headlines, or source citations. Offer what you "
            "genuinely can do — structure, methodology, which sources the principal "
            "should consult — instead of fabricating an answer that looks real."
        )
    return date_part + tools_part


PLANNER_RUNTIME_HEAD = """\
## Runtime protocol (Roster MVP)

You are running inside the Roster runtime. You speak to the human principal directly.
The specialist sub-agents below are available; you dispatch to them when their expertise
is needed. The runtime — not you — actually invokes them.

Available specialists:
"""

# Short, accurate role blurbs for the planner's specialist list.
_ROLE_BLURBS = {
    "coder": "implements code changes on a feature branch",
    "e2e": "runs end-to-end browser/Playwright tests against a running build — dispatch AFTER the coder lands a change",
    "reviewer": "reviews diffs against success criteria",
    "qa": "validates & fact-checks another agent's output (reports, claims, research) against evidence; can search the web to verify",
    "researcher": "searches the web and synthesizes findings with source URLs",
}


def build_planner_suffix(specialists: list[tuple[str, str, bool]]) -> str:
    """`specialists` = list of (name, blurb, can_search)."""
    lines = []
    for name, blurb, can_search in specialists:
        tag = "  ← can search the web" if can_search else ""
        lines.append(f"- `{name}` — {blurb}{tag}")
    has_searcher = any(cs for _, _, cs in specialists)
    if has_searcher:
        web_rule = (
            "- For live or external facts (market data, news, weather, scores), dispatch "
            "to a specialist that can search the web (tagged above). Do NOT answer such "
            "questions from memory and do NOT fabricate numbers, quotes, or citations.\n"
        )
    else:
        web_rule = (
            "- None of the specialists can browse the web or fetch external data. If a "
            "goal needs live/external information, say so plainly instead of inventing "
            "it.\n"
        )
    return (
        PLANNER_RUNTIME_HEAD
        + "\n".join(lines)
        + """

You ORCHESTRATE; you never do the work yourself. After any brief reasoning, end your reply
with directive lines the runtime executes (no backticks):

    PLAN: <one-line summary of how you split the goal>     (optional)
    DISPATCH:<role>:<one-line task>                        (ONE line per sub-task)
    ASK: <a single question for the principal>             (only when truly blocked)

How it works:
- Decompose a non-trivial goal into the FEWEST sub-tasks that genuinely differ and emit a
  DISPATCH line for EACH — several at once. Independent dispatches run IN PARALLEL. Match each
  task to the role whose expertise fits.
- The runtime runs them and feeds every result back as your next turn, each prefixed
  `[<role> reports]:`. Review them CRITICALLY: if a result is wrong, inconsistent, or
  unverified, DISPATCH again — to the same specialist to dig deeper, or to `qa` to fact-check —
  before you answer. After the first results return you may run up to two more rounds to verify.
- When you have enough, write the principal ONE synthesized final answer covering every part
  of their request, with NO PLAN/DISPATCH/ASK line.
- For a simple conversational message (greeting, status), just reply directly — no directives.
- Match work to the right role:
    · `researcher` gathers live/external facts via web search.
    · `qa` validates / fact-checks another agent's output (and can search to verify) — use it
      to vet accuracy, NOT to run a browser.
    · `e2e` drives a real browser against a RUNNING build — only after `coder` lands a change.
"""
        + web_rule
        + """- If a tool failed during the run (e.g. a web search was rate-limited or returned a bot
  challenge), TELL the principal what failed and the likely remedy (e.g. set TAVILY_API_KEY for a
  reliable search backend) — don't only say you couldn't verify.
- Use ASK sparingly — only when you cannot proceed safely; the runtime relays it to the
  principal and you continue once they answer.
- You never perform destructive (irreversible, T3/T4) actions yourself. If a sub-task would be
  irreversible, say so and ask the principal for explicit confirmation in chat first.
"""
    )


_SUBAGENT_HEAD = """\
## Runtime protocol (Roster MVP)

You are running inside the Roster runtime as a specialist sub-agent. The Planner has
dispatched a single task to you. Your reply goes back to the Planner, not to the human
principal. Be concise and structured:

- Restate the task in one line.
- Do the work with the tools available to you (described below). Act with real tools and
  report what they ACTUALLY returned — never describe hypothetical actions or invent results.
- Return a short, structured result the Planner can act on.
"""

_SUBAGENT_TOOLS = """\

## File & shell tools

You work inside an isolated git worktree of the target repository — a feature branch, never
`main`. To use a tool, end a reply with EXACTLY ONE directive; the runtime runs it and feeds
the result back as your next turn. Then continue, or give your final answer with no directive.

Read a file (returns its real contents):

    READ: path/to/file.py

Create or overwrite a file — put the FULL new contents in a fenced block immediately after:

    EDIT: path/to/file.py
    ```
    <the complete new file contents>
    ```

Run a shell command in the worktree (returns stdout, stderr, and the exit code):

    EXEC: pytest -q

Rules:
- Paths are relative to the worktree; you cannot read or write outside it.
- Make real changes by actually issuing EDIT — a real diff is produced from what you write.
- Boundary-crossing commands (network, `git push`, `sudo`, deleting outside the worktree)
  are BLOCKED pending human approval and come back `[blocked]` — do not retry them; continue
  without them or tell the Planner.
- Verify your work when you can (build/tests via EXEC), and base every claim on real output.
"""

_SUBAGENT_SEARCH = """\

## Web search tool

You CAN search the web. To do so, end a reply with EXACTLY one line:

    SEARCH: <your search query>

Keep the query SHORT — 3–6 keywords, the way a person types into a search box
(e.g. `S&P 500 close June 26 2026`). Do NOT wrap it in quotation marks and do NOT
write a long full-sentence query: overly long or quoted queries reliably return
zero results.

The runtime runs the search and feeds results back as the next turn, prefixed with
`[search results]`. Then continue — search again (up to 3 times total) or write your
final answer with NO `SEARCH:` line. Base every factual claim (prices, dates, news,
numbers) ONLY on returned results and cite their URLs. If results are empty or fail,
say so — never fabricate.
"""

_SUBAGENT_TAIL = """\

Do NOT fabricate tool output, test results, data, or citations beyond what tools
actually returned. You have no chat with the principal — do not address them directly.
"""


def build_subagent_suffix(can_search: bool, can_use_tools: bool = False) -> str:
    parts = [_SUBAGENT_HEAD]
    if can_use_tools:
        parts.append(_SUBAGENT_TOOLS)
    if can_search:
        parts.append(_SUBAGENT_SEARCH)
    parts.append(_SUBAGENT_TAIL)
    return "".join(parts)


_FILE_TOOL_CAPS = frozenset({"read", "edit", "execute"})


def wants_file_tools(tools: list[str]) -> bool:
    """True if an agent's grant includes any file/shell capability (spec 004)."""
    return bool(_FILE_TOOL_CAPS & {t.lower() for t in tools})


def _default_worktrees_root(target_repo: str) -> Path:
    return Path(target_repo).resolve().parent / ".roster-worktrees"

# Per principal message: one decomposition/fan-out round, then up to MAX_CRITIQUE
# critique/verification rounds, then a synthesized answer. MAX_PLANNER_TURNS is the hard
# ceiling on planner turns (fan-out + critique rounds + synthesis + slack).
MAX_PLANNER_TURNS = 6
MAX_CRITIQUE = 2


class Run:
    """One conversation = one run. Holds the planner + sub-agents + provenance."""

    def __init__(self, config_path: str | Path, run_id: str | None = None) -> None:
        # `run_id` is supplied when reopening a persisted conversation so the new
        # in-memory run rebinds to its existing provenance log and history.
        self.run_id = run_id or new_run_id()
        self.prov = ProvenanceLog(runs_dir(), self.run_id)
        # Orchestration state persists ACROSS principal messages so a mid-task `ASK`
        # can suspend and the next message can resume the same run.
        self.orch_state = OrchestrationState(max_critique=MAX_CRITIQUE)
        cfg: RuntimeConfig = load_config(config_path)

        if "planner" not in cfg.agents:
            raise RuntimeError("agents.config.yaml must define an agent named 'planner'")

        self.queue_cfg = cfg.queue
        self.llm_queue = LlmQueue(cfg.queue.max_concurrency)
        require = set(cfg.queue.require_queue)
        self.require_queue = require

        # One shared web-search backend; attached only to agents granted the tool.
        self.search_cfg = cfg.search
        self.search_provider: SearchProvider | None = build_search_provider(cfg.search)

        # Per-run workspace (spec 004): an isolated git worktree the Coder/E2E file & shell
        # tools act in. Absent/invalid/dirty target → tools are unavailable and the agent says
        # so (no fabrication) rather than the run failing.
        self.workspace_cfg = cfg.workspace
        self.workspace: WorkspaceManager | None = None
        self._worktree: Worktree | None = None
        self.workspace_error: str | None = None
        if cfg.workspace.target_repo:
            root = cfg.workspace.worktrees_root or str(
                _default_worktrees_root(cfg.workspace.target_repo)
            )
            try:
                self.workspace = WorkspaceManager(cfg.workspace.target_repo, root, self.run_id)
                self._worktree = self.workspace.create("work")
                log.info(
                    "run %s: workspace ready at %s (%s)",
                    self.run_id,
                    self._worktree.path,
                    self._worktree.branch,
                )
            except WorkspaceError as exc:
                self.workspace_error = str(exc)
                self.workspace = None
                self._worktree = None
                log.warning(
                    "run %s: workspace unavailable — file/shell tools disabled: %s",
                    self.run_id,
                    exc,
                )

        def _queue_for(name: str) -> LlmQueue | None:
            return self.llm_queue if name in require else None

        def _search_for(agent_cfg: Any) -> SearchProvider | None:
            if self.search_provider is None:
                return None
            return self.search_provider if "search" in agent_cfg.tools else None

        def _executor_for(agent_cfg: Any) -> ToolExecutor | None:
            if self._worktree is None or not wants_file_tools(agent_cfg.tools):
                return None
            return ToolExecutor(self._worktree)

        # Specialist metadata for the planner's (dynamic) dispatch menu.
        specialists: list[tuple[str, str, bool]] = []
        for name, agent_cfg in cfg.agents.items():
            if name == "planner":
                continue
            blurb = _ROLE_BLURBS.get(
                agent_cfg.role, (agent_cfg.description or agent_cfg.role)[:80]
            )
            specialists.append((name, blurb, _search_for(agent_cfg) is not None))

        has_searcher = any(can_search for _, _, can_search in specialists)

        planner_cfg = cfg.agents["planner"]
        planner_preamble = runtime_preamble(
            can_search=_search_for(planner_cfg) is not None,
            has_searcher=has_searcher,
        )
        planner_suffix = planner_preamble + "\n\n" + build_planner_suffix(specialists)

        self.planner = Agent.from_config(
            planner_cfg,
            runtime_suffix=planner_suffix,
            queue=_queue_for("planner"),
            search=_search_for(planner_cfg),
            search_max_results=cfg.search.max_results,
        )
        self.subagents: dict[str, Agent] = {}
        for name, agent_cfg in cfg.agents.items():
            if name == "planner":
                continue
            search = _search_for(agent_cfg)
            executor = _executor_for(agent_cfg)
            self.subagents[name] = Agent.from_config(
                agent_cfg,
                runtime_suffix=(
                    runtime_preamble(can_search=search is not None)
                    + "\n\n"
                    + build_subagent_suffix(search is not None, executor is not None)
                ),
                queue=_queue_for(name),
                search=search,
                executor=executor,
                search_max_results=cfg.search.max_results,
            )
        log.info(
            "run %s: %d agents, queue max_concurrency=%d, require_queue=%s, search=%s",
            self.run_id,
            len(cfg.agents),
            cfg.queue.max_concurrency,
            sorted(require) or "<none>",
            self.search_provider.name if self.search_provider else "disabled",
        )

    def all_agents(self) -> list[Agent]:
        return [self.planner, *self.subagents.values()]

    def resume_from_events(self, events: list[dict[str, Any]]) -> None:
        """Seed the planner's chat history from a persisted conversation so it can
        continue where it left off.

        Only the principal⇄planner transcript is restored — sub-agent histories are
        ephemeral and start fresh (acceptable for this MVP). Each prior principal
        message becomes a ``user`` turn and each final planner reply an ``assistant``
        turn, preserving the system prompt already at ``history[0]``.
        """
        for e in events:
            kind = e.get("kind")
            if kind == "user.message":
                content = str(e.get("content") or "")
                if content:
                    self.planner.history.append({"role": "user", "content": content})
            elif (
                kind == "agent.message"
                and e.get("to") == "principal"
                and e.get("subkind", "message") == "message"
            ):
                content = str(e.get("content") or "")
                if content:
                    self.planner.history.append(
                        {"role": "assistant", "content": content}
                    )

    def queue_stats(self) -> dict[str, Any]:
        st = self.llm_queue.stats()
        return {
            "max_concurrency": st.max_concurrency,
            "waiting": st.waiting,
            "active": st.active,
            "require_queue": sorted(self.require_queue),
            "search": self.search_provider.name if self.search_provider else None,
        }

    async def aclose(self) -> None:
        for a in self.all_agents():
            try:
                await a.provider.aclose()
            except Exception:  # noqa: BLE001 - best-effort cleanup
                log.debug("provider aclose failed for agent %s", a.cfg.name, exc_info=True)
        if self.search_provider is not None:
            try:
                await self.search_provider.aclose()
            except Exception:  # noqa: BLE001 - best-effort cleanup
                log.debug("search provider aclose failed", exc_info=True)

    async def health(self) -> list[dict[str, Any]]:
        return [await a.health() for a in self.all_agents()]

    async def _publish_message(
        self, src: str, dst: str, content: str, subkind: str = "message"
    ) -> None:
        await bus.publish(
            "agent.message",
            subkind=subkind,
            **{"from": src, "to": dst, "content": content},
        )

    async def _run_dispatch(self, role: str, task: str, round_idx: int) -> tuple[str, str]:
        """Dispatch one task to a specialist and return (role, reply). Safe to gather()."""
        await self._publish_message("planner", role, task, subkind="task_assignment")
        self.prov.emit("task.dispatched", actor="planner", to=role, task=task, round=round_idx)
        await events.emit_task_dispatched(to=role, task=task, round=round_idx)
        subagent = self.subagents[role]
        sub_reply = await subagent.chat(task)
        self.prov.emit(
            "task.result", actor=role, model=subagent.cfg.provider.target, content=sub_reply
        )
        if subagent.executor is not None:
            await self._finalize_tool_result(subagent, sub_reply)
        await self._publish_message(role, "planner", sub_reply, subkind="task_result")
        return role, sub_reply

    async def _finalize_tool_result(self, subagent: Agent, sub_reply: str) -> None:
        """Capture a tool-using specialist's change set: write ``diff.patch`` + a schema-valid
        ``TaskResult``, emit the final diff event, and record provenance (spec 004, T014)."""
        assert subagent.executor is not None
        task_id = new_task_id()
        patch = await asyncio.to_thread(subagent.executor.full_diff)
        runs = runs_dir()
        write_diff_artifact(runs, self.run_id, task_id, patch)
        files = summarize_diff(patch)
        result = build_task_result(
            task_id=task_id,
            run_id=self.run_id,
            completed_by=subagent.cfg.name,
            summary=sub_reply.strip()[:500],
            patch=patch,
        )
        write_task_result(runs, self.run_id, result)
        if files:
            await events.emit_tool_file(
                subagent.cfg.name, "diff", files=[asdict(f) for f in files], patch=patch
            )
        self.prov.emit(
            "task.result.artifact",
            actor=subagent.cfg.name,
            taskId=task_id,
            artifact=f"artifacts/{task_id}/diff.patch",
            filesChanged=len(files),
            additions=sum(f.additions for f in files),
            deletions=sum(f.deletions for f in files),
        )

    async def handle_principal_message(self, user_text: str) -> TurnResult:
        # If the run is paused on a clarification, THIS message is the answer — resume the
        # same orchestration rather than starting fresh.
        resuming = self.orch_state.awaiting_input

        await bus.publish(
            "user.message", **{"from": "principal", "to": "planner", "content": user_text}
        )
        self.prov.emit("principal.message", actor="principal", content=user_text)

        if resuming:
            await events.emit_clarification_answered(user_text)
            self.prov.emit("clarification.answered", actor="principal", answer=user_text)
            self.orch_state.resume()
            next_input = f"[principal answers]: {user_text}\n\nContinue the task."
        else:
            self.orch_state.reset()
            next_input = user_text

        final_reply = ""
        status = "done"

        for turn_idx in range(MAX_PLANNER_TURNS):
            reply = await self.planner.chat(next_input)
            self.prov.emit(
                "planner.reply",
                actor="planner",
                turn=turn_idx,
                model=self.planner.cfg.provider.target,
                content=reply,
            )
            turn = parse_planner_turn(reply)

            # 1) Mid-task clarification: ask the principal and SUSPEND. The next message
            #    resumes this same run (the planner's history + orchestration state persist).
            if turn.ask is not None:
                if turn.prose:
                    await self._publish_message(
                        "planner", "principal", turn.prose, subkind="thinking"
                    )
                await self._publish_message("planner", "principal", turn.ask)
                await events.emit_clarification_requested(turn.ask)
                self.prov.emit("clarification.requested", actor="planner", question=turn.ask)
                resume_phase = (
                    RunStatus.CRITIQUING if self.orch_state.gathered else RunStatus.PLANNING
                )
                self.orch_state.suspend(resume_phase)
                final_reply = turn.ask
                status = "awaiting_input"
                break

            # 2) No directives → the planner's final answer to the principal.
            if not turn.dispatches:
                answer = turn.prose or reply
                await self._publish_message("planner", "principal", answer)
                final_reply = answer
                self.orch_state.reset()
                break

            # 3) The planner wants to dispatch. The first dispatching turn is the
            #    decomposition/fan-out; every later one is a critique/verification round
            #    (the planner pushing back on a result before it answers).
            is_critique = self.orch_state.gathered
            if is_critique and not self.orch_state.can_critique():
                next_input = (
                    "[runtime] Critique budget reached — do NOT dispatch again. Write the "
                    "best-effort final answer now and explicitly flag any unresolved "
                    "uncertainty (no DISPATCH/ASK line)."
                )
                continue

            valid = [(r, t) for (r, t) in turn.dispatches if r in self.subagents]
            unknown = [r for (r, _t) in turn.dispatches if r not in self.subagents]

            if turn.prose:
                await self._publish_message("planner", "principal", turn.prose, subkind="thinking")

            if not is_critique:
                if turn.plan_summary or len(turn.dispatches) > 1:
                    tasks_payload = [{"role": r, "task": t} for (r, t) in turn.dispatches]
                    await events.emit_plan_proposed(
                        self.run_id, turn.plan_summary or "", tasks_payload
                    )
                    self.prov.emit(
                        "plan.proposed",
                        actor="planner",
                        summary=turn.plan_summary or "",
                        tasks=tasks_payload,
                    )
            else:
                # The planner is pushing back on a prior result — record the critique.
                targets = [r for (r, _t) in valid]
                concern = turn.prose or turn.plan_summary or "a prior result needs checking"
                action = "verify" if any(r in ("qa", "reviewer") for r in targets) else "re-dispatch"
                round_no = self.orch_state.critique_used + 1
                await events.emit_critique_round(
                    round=round_no, concern=concern, action=action,
                    to=targets[0] if targets else None,
                )
                self.prov.emit(
                    "critique.round", actor="planner", round=round_no,
                    concern=concern, action=action, to=targets[0] if targets else None,
                )

            if not valid:
                next_input = (
                    f"[runtime] Unknown specialist(s): {', '.join(unknown)}. "
                    f"Available: {', '.join(self.subagents)}."
                )
                self.prov.emit("dispatch.invalid", actor="runtime", roles=unknown)
                continue

            # Independent dispatches run concurrently (governed by the LLM queue's
            # max_concurrency; raise it for agents on separate/cloud backends).
            round_idx = self.orch_state.critique_used if is_critique else 0
            results = await asyncio.gather(
                *(self._run_dispatch(r, t, round_idx) for (r, t) in valid)
            )
            if is_critique:
                self.orch_state.note_critique()
            else:
                self.orch_state.gathered = True

            parts = [f"[{role} reports]:\n{rep}" for (role, rep) in results]
            if unknown:
                parts.append(f"[runtime] Unknown specialist(s) ignored: {', '.join(unknown)}.")
            next_input = "\n\n".join(parts)

            # Critique nudge: make the planner vet the results before it answers.
            if self.orch_state.can_critique():
                remaining = self.orch_state.max_critique - self.orch_state.critique_used
                next_input += (
                    "\n\n[runtime] Now CRITICALLY evaluate these results for consistency, "
                    "plausibility, and completeness. If a factual claim needs independent "
                    "confirmation, DISPATCH `qa` to verify it; if a result looks wrong, "
                    "re-DISPATCH the specialist. If everything checks out, write the final "
                    f"synthesized answer with no directives. ({remaining} critique round(s) left.)"
                )
            else:
                next_input += (
                    "\n\n[runtime] Critique budget reached. Write the principal ONE synthesized "
                    "final answer now covering every part of the request, explicitly flagging "
                    "any unresolved uncertainty — with no DISPATCH or ASK line."
                )
        else:
            final_reply = (
                "[runtime] The planner did not converge on a final answer within the round "
                "budget. Please re-prompt or simplify the request."
            )
            await self._publish_message("planner", "principal", final_reply)
            self.prov.emit("turn.budget_exhausted", actor="runtime")
            self.orch_state.reset()

        return TurnResult(status=status, text=final_reply)
