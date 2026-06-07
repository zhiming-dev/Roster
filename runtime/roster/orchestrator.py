"""Orchestrator — turns one principal message into a planner-led multi-agent exchange."""

from __future__ import annotations

import datetime as _dt
import logging
import re
from pathlib import Path
from typing import Any

from .agent import Agent
from .bus import bus
from .config import RuntimeConfig, load_config
from .provenance import ProvenanceLog, new_run_id, runs_dir
from .queue import LlmQueue
from .search import SearchProvider, build_search_provider

log = logging.getLogger("roster.orchestrator")

DISPATCH_RE = re.compile(
    r"^\s*DISPATCH\s*:\s*(?P<role>[a-z_][a-z0-9_-]*)\s*:\s*(?P<task>.+?)\s*$",
    re.IGNORECASE,
)


def runtime_preamble() -> str:
    """A dynamic preamble prepended to every agent's system prompt.

    Two jobs: (1) tell the model what *today* is, so a model whose training data
    predates the system clock stops treating recent dates as "the future"; and
    (2) be explicit that this MVP wires up NO tools, so agents must not fabricate
    live data / tool output.
    """
    now = _dt.datetime.now().astimezone()
    return (
        "## Current context\n\n"
        f"The current date is {now:%Y-%m-%d} ({now:%A}). Treat this as *today*. "
        "Any date on or before today is in the PAST — never call a past or present "
        "date 'the future'.\n\n"
        "You have **no tools** in this runtime: no web/internet access, no file "
        "system, no code execution, no live data feeds. You therefore CANNOT look "
        "up real-time or external facts (market prices, news, weather, scores, "
        "etc.). If a request needs such data, say so plainly and DO NOT invent "
        "specific numbers, quotes, headlines, or source citations. Offer what you "
        "genuinely can do — structure, methodology, which sources the principal "
        "should consult — instead of fabricating an answer that looks real."
    )


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

To dispatch, end your reply with EXACTLY one line in this form (no backticks, no prose
after it):

    DISPATCH:<role>:<one-line task for the specialist>

When you DISPATCH, the runtime invokes that specialist and feeds their reply back to you
as the next user turn, prefixed with `[<role> reports]:`. You may then dispatch again,
or — if you have enough — write your final reply to the principal with NO `DISPATCH:`
line, and the runtime will deliver it.

Hard rules:
- Maximum 3 dispatches per principal message. Stay concise.
- For simple conversational messages (greetings, status questions), DO NOT dispatch —
  just reply directly.
- Only dispatch to a specialist whose described expertise actually FITS the task. Match
  the work to the right role:
    · `e2e` drives a real browser against a RUNNING build — only after `coder` has landed
      a change. Never use it to check facts, prose, or research.
    · `qa` validates / fact-checks outputs (reports, claims, research findings) and can
      search the web to verify. Use it to vet a report's accuracy — NOT to run a browser.
    · `researcher` gathers live/external facts via web search.
"""
        + web_rule
        + """- Do not write a `DISPATCH:` line in the middle of your reply. It must be the last line.
- You never perform destructive actions yourself. If a specialist's task would be T3/T4
  (irreversible), say so to the principal and ask for explicit confirmation in chat
  before dispatching.
"""
    )


_SUBAGENT_HEAD = """\
## Runtime protocol (Roster MVP)

You are running inside the Roster runtime as a specialist sub-agent. The Planner has
dispatched a single task to you. Your reply goes back to the Planner, not to the human
principal. Be concise and structured:

- Restate the task in one line.
- Describe what you did (or, in this MVP where most tools are not wired up, what you
  WOULD do and what you'd need to actually do it).
- Return a short, structured result the Planner can act on.
"""

_SUBAGENT_SEARCH = """\

## Web search tool

You CAN search the web. To do so, end a reply with EXACTLY one line:

    SEARCH: <your search query>

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


def build_subagent_suffix(can_search: bool) -> str:
    middle = _SUBAGENT_SEARCH if can_search else ""
    return _SUBAGENT_HEAD + middle + _SUBAGENT_TAIL

MAX_DISPATCHES_PER_TURN = 3


class Run:
    """One conversation = one run. Holds the planner + sub-agents + provenance."""

    def __init__(self, config_path: str | Path) -> None:
        self.run_id = new_run_id()
        self.prov = ProvenanceLog(runs_dir(), self.run_id)
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

        def _queue_for(name: str) -> LlmQueue | None:
            return self.llm_queue if name in require else None

        def _search_for(agent_cfg: Any) -> SearchProvider | None:
            if self.search_provider is None:
                return None
            return self.search_provider if "search" in agent_cfg.tools else None

        preamble = runtime_preamble()

        # Specialist metadata for the planner's (dynamic) dispatch menu.
        specialists: list[tuple[str, str, bool]] = []
        for name, agent_cfg in cfg.agents.items():
            if name == "planner":
                continue
            blurb = _ROLE_BLURBS.get(
                agent_cfg.role, (agent_cfg.description or agent_cfg.role)[:80]
            )
            specialists.append((name, blurb, _search_for(agent_cfg) is not None))

        planner_suffix = preamble + "\n\n" + build_planner_suffix(specialists)

        planner_cfg = cfg.agents["planner"]
        self.planner = Agent.from_config(
            planner_cfg,
            runtime_suffix=planner_suffix,
            queue=_queue_for("planner"),
            search=_search_for(planner_cfg),
            search_max_results=cfg.search.max_results,
        )
        self.subagents: dict[str, Agent] = {
            name: Agent.from_config(
                agent_cfg,
                runtime_suffix=(
                    preamble
                    + "\n\n"
                    + build_subagent_suffix(_search_for(agent_cfg) is not None)
                ),
                queue=_queue_for(name),
                search=_search_for(agent_cfg),
                search_max_results=cfg.search.max_results,
            )
            for name, agent_cfg in cfg.agents.items()
            if name != "planner"
        }
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

    def _parse_dispatch(self, reply: str) -> tuple[str | None, str | None, str]:
        """Return (role, task, reply_without_dispatch_line)."""
        lines = reply.rstrip().splitlines()
        if not lines:
            return None, None, reply
        m = DISPATCH_RE.match(lines[-1])
        if not m:
            return None, None, reply
        role = m.group("role").lower()
        task = m.group("task").strip()
        pre = "\n".join(lines[:-1]).rstrip()
        return role, task, pre

    async def handle_principal_message(self, user_text: str) -> str:
        await bus.publish(
            "user.message", **{"from": "principal", "to": "planner", "content": user_text}
        )
        self.prov.emit("principal.message", actor="principal", content=user_text)

        next_input = user_text
        final_reply = ""

        for turn in range(MAX_DISPATCHES_PER_TURN + 1):
            reply = await self.planner.chat(next_input)
            self.prov.emit(
                "planner.reply",
                actor="planner",
                turn=turn,
                model=self.planner.cfg.provider.target,
                content=reply,
            )

            role, task, pre = self._parse_dispatch(reply)

            if role is None:
                await self._publish_message("planner", "principal", reply)
                final_reply = reply
                break

            if role not in self.subagents:
                # Planner dispatched to an unknown specialist — feed back as error.
                err = (
                    f"[runtime] Unknown specialist '{role}'. Available: "
                    f"{', '.join(self.subagents)}."
                )
                if pre:
                    await self._publish_message("planner", "principal", pre)
                next_input = err
                self.prov.emit("dispatch.invalid", actor="runtime", role=role, task=task)
                continue

            if pre:
                # Planner included a thought before dispatch — surface it.
                await self._publish_message("planner", "principal", pre, subkind="thinking")

            await self._publish_message(
                "planner", role, task, subkind="task_assignment"
            )
            self.prov.emit(
                "task.dispatched", actor="planner", to=role, task=task
            )

            subagent = self.subagents[role]
            sub_reply = await subagent.chat(task)
            self.prov.emit(
                "task.result",
                actor=role,
                model=subagent.cfg.provider.target,
                content=sub_reply,
            )
            await self._publish_message(role, "planner", sub_reply, subkind="task_result")

            next_input = f"[{role} reports]:\n{sub_reply}"

            if turn == MAX_DISPATCHES_PER_TURN - 1:
                next_input += (
                    "\n\n[runtime] You have one dispatch left this turn. "
                    "Wrap up and give the principal your final answer with no DISPATCH line."
                )
        else:
            # Loop exhausted without a final answer.
            final_reply = (
                "[runtime] Dispatch budget exhausted before the planner produced a "
                "final reply. Please re-prompt or simplify the request."
            )
            await self._publish_message("planner", "principal", final_reply)
            self.prov.emit("turn.budget_exhausted", actor="runtime")

        return final_reply
