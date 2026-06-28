"""Loop-level tests for decompose → parallel fan-out → critique → synthesize, plus the
mid-task clarification suspend/resume.

Runs under the runtime venv (needs the package's runtime deps installed). It bypasses
`Run.__init__` (which loads config and builds real providers) via `object.__new__` and wires
fake agents, so the orchestration logic is exercised without a live model.
"""

import types

from roster.orchestrator import MAX_CRITIQUE, Run
from roster.run_state import OrchestrationState


class _FakeProv:
    def emit(self, *args, **kwargs):
        pass


def _cfg(target):
    return types.SimpleNamespace(name=target, provider=types.SimpleNamespace(target=target))


class _FakeAgent:
    def __init__(self, replies, target="fake"):
        self._replies = list(replies)
        self.cfg = _cfg(target)
        self.seen = []

    async def chat(self, text):
        self.seen.append(text)
        return self._replies.pop(0) if self._replies else "(no more replies)"


def _bare_run():
    run = object.__new__(Run)
    run.run_id = "run_test"
    run.prov = _FakeProv()
    run.orch_state = OrchestrationState(max_critique=MAX_CRITIQUE)
    return run


async def test_fanout_then_synthesize():
    run = _bare_run()
    run.planner = _FakeAgent(
        [
            "PLAN: two parts\nDISPATCH:researcher:part A\nDISPATCH:researcher:part B",
            "Final synthesized answer covering A and B.",
        ],
        target="planner-model",
    )
    researcher = _FakeAgent(["result A", "result B"], target="r-model")
    run.subagents = {"researcher": researcher}

    result = await run.handle_principal_message("do A and B")

    assert result.status == "done"
    assert "Final synthesized answer" in result.text
    # Both sub-tasks were dispatched (parallel fan-out to the same specialist).
    assert len(researcher.seen) == 2
    # The planner's synthesis turn received both reports folded together.
    assert "[researcher reports]" in run.planner.seen[1]


async def test_simple_message_answers_directly():
    run = _bare_run()
    run.planner = _FakeAgent(["Hello! How can the team help?"], target="planner-model")
    run.subagents = {}

    result = await run.handle_principal_message("hi")

    assert result.status == "done"
    assert "Hello" in result.text
    assert len(run.planner.seen) == 1


async def test_critique_round_before_answering():
    run = _bare_run()
    # Turn 1: fan-out. Turn 2: the planner distrusts the result and escalates to qa
    # (a critique round). Turn 3: synthesize the verified answer.
    run.planner = _FakeAgent(
        [
            "PLAN: one figure\nDISPATCH:researcher:get the figure",
            "That figure looks inconsistent — verify it.\nDISPATCH:qa:verify the figure",
            "Final answer: the verified figure is 42.",
        ],
        target="planner-model",
    )
    researcher = _FakeAgent(["The figure is 999 (suspicious)."])
    qa = _FakeAgent(["Verified: the correct figure is 42."])
    run.subagents = {"researcher": researcher, "qa": qa}

    result = await run.handle_principal_message("get and check the figure")

    assert "verified" in result.text.lower()
    # The planner did NOT deliver the suspect result; it opened a critique round to qa.
    assert len(qa.seen) == 1
    assert len(run.planner.seen) == 3


async def test_critique_budget_is_bounded():
    run = _bare_run()
    # The planner keeps trying to re-dispatch; the runtime caps critique rounds at 2.
    run.planner = _FakeAgent(
        [
            "DISPATCH:researcher:gather",
            "still unsure\nDISPATCH:qa:check 1",
            "still unsure\nDISPATCH:qa:check 2",
            "still unsure\nDISPATCH:qa:check 3",  # refused — budget reached
            "Best-effort answer, with caveats.",
        ],
        target="planner-model",
    )
    researcher = _FakeAgent(["r"])
    qa = _FakeAgent(["a", "b", "c"])
    run.subagents = {"researcher": researcher, "qa": qa}

    result = await run.handle_principal_message("go")

    assert "Best-effort" in result.text
    assert len(qa.seen) == 2  # exactly two critique rounds; the third was refused


async def test_ask_suspends_then_resumes():
    run = _bare_run()
    run.planner = _FakeAgent(
        [
            "I need to know which exchange.\nASK: NASDAQ or NYSE?",
            # fed the answer, the planner proceeds with the same run:
            "Thanks.\nDISPATCH:researcher:NASDAQ trend",
            "Final report for NASDAQ.",
        ],
        target="planner-model",
    )
    researcher = _FakeAgent(["nasdaq up 1%"])
    run.subagents = {"researcher": researcher}

    first = await run.handle_principal_message("analyze the index")
    assert first.status == "awaiting_input"
    assert "NASDAQ or NYSE" in first.text
    assert run.orch_state.awaiting_input

    second = await run.handle_principal_message("NASDAQ")
    assert second.status == "done"
    assert "Final report" in second.text
    assert not run.orch_state.awaiting_input
    # The task resumed (researcher ran once) rather than restarting from scratch.
    assert len(researcher.seen) == 1
