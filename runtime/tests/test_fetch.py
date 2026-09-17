"""Unit tests for the FETCH tool's pure parts (roster/fetch.py) and the agent's
FETCH: directive loop — no network; the fetcher is faked at the Agent seam."""

import types

import pytest

from roster.agent import MAX_FETCHES_PER_TURN, Agent
from roster.fetch import (
    FetchError,
    FetchResult,
    cap_data_text,
    check_url,
    extract_text,
    format_fetch_result,
    pdf_extract_text,
)

# ---- check_url: only public http(s) targets are fetchable --------------------------


def test_check_url_accepts_public_http():
    assert check_url("https://fred.stlouisfed.org/series/SP500").startswith("https://")
    assert check_url("http://example.com/a?b=c") == "http://example.com/a?b=c"


def test_check_url_strips_wrapping_quotes_and_brackets():
    assert check_url("<https://example.com/x>") == "https://example.com/x"
    assert check_url("'https://example.com/x'") == "https://example.com/x"


@pytest.mark.parametrize(
    "bad",
    [
        "ftp://example.com/file",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "https://localhost/admin",
        "http://127.0.0.1:8765/",
        "http://10.0.0.5/internal",
        "http://192.168.1.1/router",
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/computeMetadata/",
        "https://myhost.local/x",
        "notaurl",
    ],
)
def test_check_url_rejects_non_public_targets(bad):
    with pytest.raises(FetchError):
        check_url(bad)


# ---- extract_text: HTML → readable text ---------------------------------------------


def test_extract_text_drops_scripts_and_keeps_structure():
    html = (
        "<html><head><title>T</title><style>.x{}</style></head><body>"
        "<script>var a=1;</script>"
        "<h1>Header</h1><p>First &amp; second.</p>"
        "<table><tr><td>2026-07-09</td><td>7575.39</td></tr></table>"
        "</body></html>"
    )
    text = extract_text(html)
    assert "var a=1" not in text
    assert ".x{}" not in text
    assert "Header" in text
    assert "First & second." in text
    # Table cells stay on one line, separated — a data row remains readable.
    assert "2026-07-09\t7575.39" in text.replace(" \t", "\t")


def test_extract_text_collapses_blank_runs():
    text = extract_text("<div>a</div><br><br><br><div>b</div>")
    assert text.splitlines().count("") <= 1


# ---- pdf_extract_text ----------------------------------------------------------------


def _mini_pdf(text: str) -> bytes:
    """Hand-build a minimal single-page PDF containing ``text`` (valid xref included)."""
    stream = f"BT /F1 24 Tf 72 700 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref_pos = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objs) + 1,
        xref_pos,
    )
    return bytes(out)


def test_pdf_extract_text_reads_page_text():
    assert "Crisis Report 2008" in pdf_extract_text(_mini_pdf("Crisis Report 2008"))


def test_pdf_extract_text_rejects_garbage():
    with pytest.raises(FetchError):
        pdf_extract_text(b"%PDF-1.4 this is not really a pdf")


# ---- cap_data_text: raw data keeps its TAIL (the freshest rows) ---------------------


def test_cap_data_text_keeps_header_and_latest_rows():
    rows = ["date,value"] + [f"2026-{m:02d}-01,{m}" for m in range(1, 13)] * 200
    text = "\n".join(rows)
    capped, truncated = cap_data_text(text, 1000)
    assert truncated
    assert capped.startswith("date,value")  # head kept for context
    assert capped.endswith("2026-12-01,12")  # tail (latest data) kept
    assert "chars omitted from the middle" in capped
    assert len(capped) <= 1000 + 60  # marker overhead only


def test_cap_data_text_short_input_untouched():
    assert cap_data_text("a,b\n1,2", 1000) == ("a,b\n1,2", False)


# ---- format_fetch_result -------------------------------------------------------------


def test_format_fetch_result_marks_truncation_and_redirect():
    r = FetchResult(
        url="http://a.com",
        final_url="https://a.com/landed",
        status_code=200,
        content_type="text/html",
        text="body text",
        truncated=True,
    )
    out = format_fetch_result(r)
    assert "https://a.com/landed" in out and "redirected from http://a.com" in out
    assert "truncated" in out
    assert "body text" in out


# ---- the FETCH: directive loop (fake provider + fake fetcher) ------------------------


class _ScriptedProvider:
    def __init__(self, replies):
        self._replies = list(replies)
        self.provider = "fake"
        self.target = "fake-model"
        self.endpoint = "local"
        self.seen: list[list[str]] = []

    async def chat(self, history):
        self.seen.append([m["content"] for m in history])
        return self._replies.pop(0) if self._replies else "done."

    async def health(self):
        return {"ok": True}


class _FakeFetcher:
    def __init__(self, text="PAGE CONTENT 42", fail=False):
        self._text = text
        self._fail = fail
        self.fetched: list[str] = []

    async def fetch(self, url):
        self.fetched.append(url)
        if self._fail:
            raise FetchError("boom")
        return FetchResult(
            url=url, final_url=url, status_code=200, content_type="text/html", text=self._text
        )

    async def aclose(self):
        pass


def _agent(replies, fetcher):
    cfg = types.SimpleNamespace(
        name="researcher",
        role="researcher",
        provider=types.SimpleNamespace(provider="fake", target="fake-model", endpoint="local"),
    )
    provider = _ScriptedProvider(replies)
    return (
        Agent(cfg=cfg, provider=provider, fetcher=fetcher,
              history=[{"role": "system", "content": "sys"}]),
        provider,
    )


async def test_fetch_directive_feeds_page_content_back():
    fetcher = _FakeFetcher()
    agent, provider = _agent(
        ["Let me open it.\nFETCH: https://example.com/data", "The value is 42."], fetcher
    )
    reply = await agent.chat("what does the page say?")
    assert reply == "The value is 42."
    assert fetcher.fetched == ["https://example.com/data"]
    # The page's real content was fed back before the second model call.
    assert any("[fetched]" in m and "PAGE CONTENT 42" in m for m in provider.seen[1])


async def test_fetch_error_feeds_corrective_message_not_crash():
    agent, provider = _agent(
        ["FETCH: https://example.com/x", "Could not read the page."], _FakeFetcher(fail=True)
    )
    reply = await agent.chat("open it")
    assert reply == "Could not read the page."
    assert any("[fetch error]" in m and "boom" in m for m in provider.seen[1])


async def test_fetch_budget_forces_final_answer():
    replies = [f"FETCH: https://example.com/{i}" for i in range(MAX_FETCHES_PER_TURN + 1)]
    replies.append("final answer after budget")
    fetcher = _FakeFetcher()
    agent, provider = _agent(replies, fetcher)
    reply = await agent.chat("fetch forever")
    assert reply == "final answer after budget"
    assert len(fetcher.fetched) == MAX_FETCHES_PER_TURN
    assert any("FETCH budget exhausted" in m for m in provider.seen[-1])


async def test_no_fetcher_means_fetch_line_is_a_plain_answer():
    agent, provider = _agent(["FETCH: https://example.com/x"], fetcher=None)
    reply = await agent.chat("hi")
    assert reply == "FETCH: https://example.com/x"  # not parsed as a directive
    assert len(provider.seen) == 1
