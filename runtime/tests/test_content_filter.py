"""Content-filter graceful handling (regression: 2026-07-16 backtest run).

Azure Prompt Shields blocked the coder's completion with label 'Jailbreak' twice; the raw
JSON dump reached the planner and the principal. Blocks must surface as a clean,
actionable message that names the operator fix and warns against verbatim retries.
"""

from roster.providers.base import ProviderError, content_filter_detail, content_filter_error

# The exact shape Azure returned in the failing run (trimmed).
_AZURE_CHOICE_BLOCK = {
    "id": "chatcmpl-cbf71526296d4de2a82305cb9da29",
    "model": "",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": ""},
            "finish_reason": "content_filter",
            "content_filter_results": {
                "error": {
                    "code": "content_filter",
                    "message": "Response content blocked by label 'Jailbreak'.",
                }
            },
        }
    ],
    "usage": {"prompt_tokens": 10025, "total_tokens": 10025},
}

# The other shape: a top-level error object (Azure 400 on the *prompt* side).
_AZURE_ERROR_BLOCK = {
    "error": {
        "code": "content_filter",
        "message": "The response was filtered due to the prompt triggering content management policy.",
    }
}


def test_detects_choice_level_block():
    detail = content_filter_detail(_AZURE_CHOICE_BLOCK)
    assert detail == "Response content blocked by label 'Jailbreak'."


def test_detects_top_level_error_block():
    detail = content_filter_detail(_AZURE_ERROR_BLOCK)
    assert detail is not None and "content management policy" in detail


def test_normal_response_is_not_flagged():
    ok = {"choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}]}
    assert content_filter_detail(ok) is None
    assert content_filter_detail(None) is None
    assert content_filter_detail("nonsense") is None


def test_error_message_is_actionable_not_a_json_dump():
    err = content_filter_error("Azure", "Response content blocked by label 'Jailbreak'.")
    assert isinstance(err, ProviderError)
    text = str(err)
    assert "Jailbreak" in text
    assert "Annotate only" in text  # names the concrete operator fix
    assert "retrying the same request will fail the same way" in text
    assert "{" not in text  # no raw JSON reaches the planner/principal
    assert not err.retriable  # deterministic block — never burn retries on it
