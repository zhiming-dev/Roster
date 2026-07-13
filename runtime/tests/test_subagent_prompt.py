"""Pure tests for the subagent prompt + capability helpers (spec 004, T012)."""

from roster.orchestrator import build_subagent_suffix, wants_file_tools


def test_tools_section_appears_only_with_tools():
    with_tools = build_subagent_suffix(can_search=False, can_use_tools=True)
    assert "File & shell tools" in with_tools
    assert "EDIT:" in with_tools and "EXEC:" in with_tools and "READ:" in with_tools
    assert "File & shell tools" not in build_subagent_suffix(can_search=False, can_use_tools=False)


def test_search_section_is_independent_of_tools():
    s = build_subagent_suffix(can_search=True, can_use_tools=False)
    assert "Web search tool" in s and "File & shell tools" not in s
    both = build_subagent_suffix(can_search=True, can_use_tools=True)
    assert "Web search tool" in both and "File & shell tools" in both


def test_the_would_do_fabrication_language_is_gone():
    for cs in (True, False):
        for ct in (True, False):
            assert "WOULD do" not in build_subagent_suffix(can_search=cs, can_use_tools=ct)


def test_wants_file_tools():
    assert wants_file_tools(["read", "edit"]) is True
    assert wants_file_tools(["execute"]) is True
    assert wants_file_tools(["EDIT"]) is True  # case-insensitive
    assert wants_file_tools(["search"]) is False
    assert wants_file_tools([]) is False
