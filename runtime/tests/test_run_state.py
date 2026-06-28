from roster.run_state import OrchestrationState, RunStatus


def test_fanout_budget_is_bounded():
    s = OrchestrationState(max_fanouts=2)
    assert s.can_fanout()
    s.note_fanout()
    assert s.can_fanout()
    s.note_fanout()
    assert not s.can_fanout()


def test_critique_budget_is_bounded():
    s = OrchestrationState(max_critique=2)
    s.note_critique()
    s.note_critique()
    assert not s.can_critique()


def test_suspend_then_resume_returns_to_phase():
    s = OrchestrationState()
    s.suspend(RunStatus.CRITIQUING)
    assert s.awaiting_input
    assert s.status == RunStatus.AWAITING_INPUT
    assert s.resume() == RunStatus.CRITIQUING
    assert s.status == RunStatus.CRITIQUING
    assert not s.awaiting_input
