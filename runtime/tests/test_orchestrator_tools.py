"""Integration test for executor wiring in Run.__init__ (spec 004, T012).

Builds a real ``Run`` against the ``runtime_config`` fixture (which points at the fixture git
repo and the real agent .md files), then asserts the Coder is wired with a worktree-backed
executor while a non-tool specialist is not. No model is called — only construction is exercised.
"""

from roster.orchestrator import Run


async def test_coder_gets_a_worktree_backed_executor(git_repo, runtime_config):
    run = Run(runtime_config(target_repo=git_repo))
    try:
        assert run._worktree is not None
        assert run._worktree.branch.startswith("feat/")
        assert run.subagents["coder"].executor is not None
        assert run.subagents["researcher"].executor is None  # no file/shell grant
        coder_prompt = run.subagents["coder"].history[0]["content"]
        assert "File & shell tools" in coder_prompt
        assert "WOULD do" not in coder_prompt
    finally:
        await run.aclose()


async def test_no_target_repo_means_tools_are_unavailable(git_repo, runtime_config):
    run = Run(runtime_config(target_repo=None))
    try:
        assert run._worktree is None
        assert run.subagents["coder"].executor is None
        assert "File & shell tools" not in run.subagents["coder"].history[0]["content"]
    finally:
        await run.aclose()
