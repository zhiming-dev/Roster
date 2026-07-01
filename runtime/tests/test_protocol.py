from roster.protocol import is_final, parse_planner_turn, parse_tool_call


def test_multiple_dispatches_are_parsed_for_parallel_fanout():
    turn = parse_planner_turn(
        "Let's split this.\n"
        "PLAN: three timeframes\n"
        "DISPATCH:researcher:NASDAQ 10-day\n"
        "DISPATCH:researcher:NASDAQ 30-day\n"
        "DISPATCH:researcher:NASDAQ 200-day"
    )
    assert turn.plan_summary == "three timeframes"
    assert turn.dispatches == [
        ("researcher", "NASDAQ 10-day"),
        ("researcher", "NASDAQ 30-day"),
        ("researcher", "NASDAQ 200-day"),
    ]
    assert turn.ask is None
    assert not is_final(turn)


def test_ask_takes_precedence_over_dispatch():
    turn = parse_planner_turn("ASK: which exchange did you mean?\nDISPATCH:researcher:x")
    assert turn.ask == "which exchange did you mean?"
    assert turn.dispatches == []
    assert not is_final(turn)


def test_plain_reply_is_final():
    turn = parse_planner_turn("Here is your synthesized report. All done.")
    assert is_final(turn)
    assert turn.prose.startswith("Here is your synthesized report")


def test_prose_excludes_directive_lines():
    turn = parse_planner_turn("Quick thought before dispatching.\nDISPATCH:qa:verify the figures")
    assert turn.prose == "Quick thought before dispatching."
    assert turn.dispatches == [("qa", "verify the figures")]


# --- subagent tool-call protocol (spec 004, T004) ----------------------------


def test_no_directive_is_a_final_answer():
    assert parse_tool_call("Here is the result. Nothing more to do.") is None
    assert parse_tool_call("") is None


def test_read_directive_is_parsed():
    call = parse_tool_call("Let me look at the util first.\nREAD: src/util.py")
    assert call is not None and call.ok
    assert call.kind == "read" and call.path == "src/util.py"


def test_read_strips_surrounding_quotes():
    assert parse_tool_call('READ: "src/app.py"').path == "src/app.py"
    assert parse_tool_call("READ: `src/app.py`").path == "src/app.py"


def test_read_without_path_is_malformed():
    call = parse_tool_call("READ:")
    assert call is not None and not call.ok and call.kind == "read"


def test_exec_directive_is_parsed():
    call = parse_tool_call("Now I'll run the tests.\nEXEC: pytest -q")
    assert call is not None and call.ok
    assert call.kind == "exec" and call.command == "pytest -q"


def test_exec_without_command_is_malformed():
    call = parse_tool_call("EXEC:   ")
    assert call is not None and not call.ok and call.kind == "exec"


def test_edit_directive_with_fenced_body_is_parsed():
    reply = "I'll add the helper.\nEDIT: src/util.py\n```python\ndef ok():\n    return True\n```"
    call = parse_tool_call(reply)
    assert call is not None and call.ok
    assert call.kind == "edit" and call.path == "src/util.py"
    assert call.body == 'def ok():\n    return True\n'


def test_edit_body_ignores_the_language_tag():
    call = parse_tool_call("EDIT: a.txt\n```\nhello\n```")
    assert call is not None and call.ok and call.body == "hello\n"


def test_edit_supports_an_empty_file_body():
    call = parse_tool_call("EDIT: empty.txt\n```\n```")
    assert call is not None and call.ok and call.kind == "edit" and call.body == ""


def test_edit_without_a_fenced_block_is_malformed():
    call = parse_tool_call("EDIT: src/util.py")
    assert call is not None and not call.ok and call.kind == "edit"
    assert "fenced" in (call.error or "").lower()


def test_a_fenced_block_not_at_the_end_is_not_a_directive():
    # A code sample in prose (with trailing text after it) is not a trailing EDIT directive.
    reply = "Here is an example:\nEDIT: x.py\n```\nprint(1)\n```\nBut I won't apply it yet."
    assert parse_tool_call(reply) is None
