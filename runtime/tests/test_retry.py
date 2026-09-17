"""Graceful-failure tests (regressions from the 2026-07-16 backtest run):

- transient provider errors (429/timeout/5xx) retry with backoff instead of failing the
  specialist's whole task;
- non-retriable errors (auth, content filter) surface immediately;
- duplicate DISPATCH lines collapse to one execution.
"""

import types

import pytest

from roster.agent import MAX_LLM_ATTEMPTS, Agent
from roster.orchestrator import MAX_CRITIQUE, Run
from roster.providers import ProviderError
from roster.run_state import OrchestrationState

# ---- provider retry ---------------------------------------------------------------


class _FlakyProvider:
    """Fails ``failures`` times with the given error, then answers."""

    def __init__(self, failures: int, error: ProviderError):
        self.failures = failures
        self.error = error
        self.calls = 0
        self.provider = "fake"
        self.target = "fake-model"
        self.endpoint = "local"

    async def chat(self, history):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error
        return "recovered answer"

    async def health(self):
        return {"ok": True}


def _agent(provider):
    cfg = types.SimpleNamespace(
        name="coder",
        role="coder",
        provider=types.SimpleNamespace(provider="fake", target="fake-model", endpoint="local"),
    )
    return Agent(cfg=cfg, provider=provider, history=[{"role": "system", "content": "sys"}])


async def test_rate_limit_is_retried_until_success():
    provider = _FlakyProvider(
        2, ProviderError("rate-limited (429)", retry_after=0.01, retriable=True)
    )
    agent = _agent(provider)
    reply = await agent.chat("do the thing")
    assert reply == "recovered answer"
    assert provider.calls == 3
    assert agent.status == "idle"  # no error state left behind


async def test_retries_are_bounded_then_surface():
    provider = _FlakyProvider(
        99, ProviderError("rate-limited (429)", retry_after=0.01, retriable=True)
    )
    agent = _agent(provider)
    with pytest.raises(ProviderError):
        await agent.chat("do the thing")
    assert provider.calls == MAX_LLM_ATTEMPTS  # bounded, not infinite


async def test_non_retriable_error_fails_fast():
    provider = _FlakyProvider(99, ProviderError("Azure auth failed (401)"))
    agent = _agent(provider)
    with pytest.raises(ProviderError):
        await agent.chat("do the thing")
    assert provider.calls == 1  # no pointless retries on auth/content errors


# ---- duplicate dispatch dedup -------------------------------------------------------


class _FakeProv:
    def emit(self, *args, **kwargs):
        pass


class _FakeAgent:
    def __init__(self, replies, target="fake"):
        self._replies = list(replies)
        self.cfg = types.SimpleNamespace(
            name=target, provider=types.SimpleNamespace(target=target)
        )
        self.executor = None
        self.seen = []

    async def chat(self, text):
        self.seen.append(text)
        return self._replies.pop(0) if self._replies else "(no more replies)"


def _bare_run():
    run = object.__new__(Run)
    run.run_id = "run_test"
    run.prov = _FakeProv()
    run.orch_state = OrchestrationState(max_critique=MAX_CRITIQUE)
    run.pending_approvals = []
    run._round = None
    run._surfaced_prop_id = None
    run._dispatched_roles = set()
    return run


async def test_identical_dispatch_lines_run_once():
    run = _bare_run()
    task = "backtest 2008 vs the last 3 months"
    run.planner = _FakeAgent(
        [f"PLAN: quant\nDISPATCH:coder:{task}\nDISPATCH:coder:{task}", "Final answer."],
        target="planner-model",
    )
    coder = _FakeAgent(["report written"])
    run.subagents = {"coder": coder}

    result = await run.handle_principal_message("run the backtest")

    assert result.status == "done"
    assert len(coder.seen) == 1  # the duplicate line did not double the work
    assert run.planner.seen[1].count("[coder reports]") == 1


async def test_distinct_tasks_to_same_role_still_fan_out():
    run = _bare_run()
    run.planner = _FakeAgent(
        ["DISPATCH:coder:part A\nDISPATCH:coder:part B", "Final."],
        target="planner-model",
    )
    coder = _FakeAgent(["A done", "B done"])
    run.subagents = {"coder": coder}

    await run.handle_principal_message("do A and B")
    assert len(coder.seen) == 2  # dedup only collapses IDENTICAL (role, task) pairs
