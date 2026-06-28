from roster.protocol import is_final, parse_planner_turn


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
