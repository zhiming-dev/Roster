"""Web page fetch — the `FETCH:` directive's backend (the runtime's second web tool).

Search returns titles and ~400-char snippets; FETCH opens ONE url and returns its actual
content — readable text for HTML pages, raw text for data endpoints (CSV/JSON/plain), and
extracted text for PDFs (reports, filings, papers). This is what lets a researcher verify
a claim against the page itself, or pull a structured series (e.g. FRED's
``fredgraph.csv``) instead of squinting at search snippets.

Pure-ish by design: :func:`extract_text`, :func:`pdf_extract_text` and :func:`check_url`
take bytes/strings so they can be unit-tested without a network; :class:`WebFetcher` owns
the httpx client.
"""

from __future__ import annotations

import html
import io
import ipaddress
import logging
import re
import urllib.parse
from dataclasses import dataclass

import httpx

log = logging.getLogger("roster.fetch")

DEFAULT_MAX_CHARS = 8_000
# Hard cap on bytes read off the wire, whatever the page claims — keeps a runaway
# download from ballooning memory before truncation to max_chars.
_MAX_DOWNLOAD_BYTES = 2_000_000

# Content types returned verbatim (capped) rather than HTML-stripped.
_RAW_TEXT_TYPES = (
    "text/plain",
    "text/csv",
    "application/json",
    "application/csv",
    "text/tab-separated-values",
    "application/xml",
    "text/xml",
)

_BLOCKED_HOSTS = frozenset({"localhost", "localhost.localdomain", "metadata.google.internal"})


class FetchError(RuntimeError):
    """A fetch failed in a way worth surfacing to the agent/operator."""


@dataclass
class FetchResult:
    url: str
    final_url: str
    status_code: int
    content_type: str
    text: str
    truncated: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "url": self.url,
            "finalUrl": self.final_url,
            "statusCode": self.status_code,
            "contentType": self.content_type,
            "chars": len(self.text),
            "truncated": self.truncated,
        }


def check_url(url: str) -> str:
    """Validate an agent-authored url; returns the cleaned url or raises :class:`FetchError`.

    Guards the obvious SSRF shapes — non-http(s) schemes, localhost and private/link-local
    IP literals — because the url comes from a model, not the operator. Lexical only (no
    DNS resolution), which matches the runtime's MVP threat model: the boundary gate, not
    this check, is the defense for agents with shell access.
    """
    cleaned = url.strip().strip("<>").strip("\"'`")
    parsed = urllib.parse.urlparse(cleaned)
    if parsed.scheme not in ("http", "https"):
        raise FetchError(f"only http(s) urls can be fetched, got scheme '{parsed.scheme or '?'}'")
    host = (parsed.hostname or "").lower()
    if not host:
        raise FetchError("url has no host")
    if host in _BLOCKED_HOSTS or host.endswith(".local") or host.endswith(".internal"):
        raise FetchError(f"host '{host}' is not fetchable (local/internal address)")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        pass  # a hostname, not an IP literal
    else:
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise FetchError(f"IP '{host}' is not fetchable (private/loopback/link-local)")
    return cleaned


_DROP_BLOCKS_RE = re.compile(
    r"<(script|style|noscript|svg|head|template)\b.*?</\1\s*>", re.S | re.I
)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
# Tags that end a line of text when stripped, so tables/paragraphs don't run together.
_BLOCK_TAG_RE = re.compile(
    r"</?(p|div|br|li|ul|ol|h[1-6]|tr|table|section|article|blockquote|pre|dt|dd)\b[^>]*>",
    re.I,
)
_TD_RE = re.compile(r"</(td|th)\s*>", re.I)
_TAG_RE = re.compile(r"<[^>]+>")


def extract_text(html_text: str) -> str:
    """Strip an HTML document down to its readable text.

    Deliberately simple (no DOM library): drop script/style/head blocks, keep line breaks
    at block-level tags and a tab between table cells, strip the rest of the tags, then
    collapse whitespace. Good enough to verify a claim or read a data table; not a
    layout-faithful render.
    """
    s = _COMMENT_RE.sub(" ", html_text)
    s = _DROP_BLOCKS_RE.sub(" ", s)
    s = _TD_RE.sub("\t", s)
    s = _BLOCK_TAG_RE.sub("\n", s)
    s = _TAG_RE.sub(" ", s)
    s = html.unescape(s)
    # Collapse intra-line whitespace but KEEP the tabs that separate table cells,
    # then collapse blank-line runs.
    lines = [
        "\t".join(" ".join(part.split()) for part in ln.split("\t")).strip("\t ")
        for ln in s.splitlines()
    ]
    out: list[str] = []
    for ln in lines:
        if ln:
            out.append(ln)
        elif out and out[-1]:
            out.append("")
    return "\n".join(out).strip()


# PDFs can be hundreds of pages; extracting them all is slow and futile when the output
# is capped anyway. ~40 pages comfortably covers the summary/data sections of a report.
_PDF_MAX_PAGES = 40


def pdf_extract_text(raw: bytes, max_pages: int = _PDF_MAX_PAGES) -> str:
    """Extract text from PDF bytes, page by page, up to ``max_pages``.

    Raises :class:`FetchError` on an unparseable document (encrypted, corrupt) so the
    agent hears an honest failure instead of an empty page.
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover — pypdf is a declared dependency
        raise FetchError(
            "PDF support unavailable: pypdf is not installed in the RUNTIME'S Python "
            "environment. Operator fix: activate runtime/.venv and run "
            "`pip install -r requirements.txt`, then restart the server (the server may "
            "currently be running under a different interpreter)"
        ) from exc
    try:
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted:
            # Try the empty password (common for "secured" but readable PDFs).
            try:
                reader.decrypt("")
            except Exception as exc:  # noqa: BLE001
                raise FetchError("PDF is encrypted and cannot be read") from exc
        total = len(reader.pages)
        pages: list[str] = []
        for i, page in enumerate(reader.pages):
            if i >= max_pages:
                pages.append(f"[... {total - max_pages} more pages not extracted ...]")
                break
            pages.append(page.extract_text() or "")
    except FetchError:
        raise
    except Exception as exc:  # noqa: BLE001 — pypdf raises a zoo of parse errors
        raise FetchError(f"could not parse PDF: {exc}") from exc
    text = "\n\n".join(p.strip() for p in pages if p.strip())
    if not text:
        raise FetchError(
            "PDF parsed but contained no extractable text (likely a scanned/image PDF)"
        )
    return text


def cap_data_text(text: str, max_chars: int) -> tuple[str, bool]:
    """Cap raw data (CSV/JSON/plain) keeping the head AND the tail.

    Time series are almost always oldest-first, so a head-only cut would hand the agent
    1990 and silently drop this quarter — the exact rows it asked for. Keep the header/
    start for context and spend most of the budget on the freshest rows at the end.
    """
    if len(text) <= max_chars:
        return text, False
    head_budget = max_chars // 4
    tail_budget = max_chars - head_budget
    head = text[:head_budget]
    tail = text[-tail_budget:]
    omitted = len(text) - head_budget - tail_budget
    marker = f"\n... [{omitted} chars omitted from the middle] ...\n"
    return head + marker + tail, True


def format_fetch_result(r: FetchResult) -> str:
    """Render one fetched page compactly for feeding back into an LLM turn."""
    header = f"Fetched {r.final_url} (HTTP {r.status_code}, {r.content_type or 'unknown type'})"
    if r.final_url != r.url:
        header += f" [redirected from {r.url}]"
    if not r.text:
        return header + "\nThe page had no extractable text content."
    body = r.text
    if r.truncated:
        body += "\n\n[content truncated — cite only what appears above]"
    return f"{header}\n---\n{body}"


class WebFetcher:
    """Fetch one url and return its readable text. One shared instance per run."""

    name = "httpx"

    def __init__(self, timeout_s: float = 20.0, max_chars: int = DEFAULT_MAX_CHARS) -> None:
        self.max_chars = max_chars
        # An HONEST client identity, not a spoofed browser UA: sites with bot detection
        # (e.g. FRED behind Akamai) hang or block a "Chrome" whose TLS/header fingerprint
        # doesn't match a real Chrome, while a plain declared client passes.
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s, connect=5.0),
            headers={
                "User-Agent": "roster-runtime/0.1 (research agent; +https://localhost)",
                "Accept": "text/html,application/xhtml+xml,text/csv,application/json,"
                "text/plain;q=0.9,*/*;q=0.8",
            },
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch(self, url: str) -> FetchResult:
        cleaned = check_url(url)
        try:
            async with self._client.stream("GET", cleaned) as resp:
                content_type = (resp.headers.get("content-type") or "").split(";")[0].strip()
                raw = bytearray()
                async for chunk in resp.aiter_bytes():
                    raw.extend(chunk)
                    if len(raw) >= _MAX_DOWNLOAD_BYTES:
                        break
        except httpx.HTTPError as exc:
            raise FetchError(f"request failed for {cleaned}: {exc}") from exc

        is_pdf = content_type == "application/pdf" or bytes(raw[:5]) == b"%PDF-"
        if is_pdf:
            text = pdf_extract_text(bytes(raw))
            truncated = len(text) > self.max_chars
            if truncated:
                text = text[: self.max_chars]
            return FetchResult(
                url=cleaned,
                final_url=str(resp.url),
                status_code=resp.status_code,
                content_type="application/pdf",
                text=text,
                truncated=truncated,
            )

        if content_type and not (
            content_type.startswith("text/") or content_type in _RAW_TEXT_TYPES
        ) and not content_type.endswith(("+json", "+xml")):
            return FetchResult(
                url=cleaned,
                final_url=str(resp.url),
                status_code=resp.status_code,
                content_type=content_type,
                text=f"[non-text content: {content_type}, {len(raw)} bytes — cannot render]",
            )

        charset = resp.charset_encoding or "utf-8"
        try:
            decoded = raw.decode(charset, errors="replace")
        except LookupError:
            decoded = raw.decode("utf-8", errors="replace")

        if content_type in ("", "text/html"):
            # An article's lead is its substance — a head-only cut keeps what matters.
            text = extract_text(decoded)
            truncated = len(text) > self.max_chars
            if truncated:
                text = text[: self.max_chars]
        else:
            # Raw data (CSV/JSON/plain): keep head + TAIL, where the freshest rows live.
            text, truncated = cap_data_text(decoded.strip(), self.max_chars)
        return FetchResult(
            url=cleaned,
            final_url=str(resp.url),
            status_code=resp.status_code,
            content_type=content_type,
            text=text,
            truncated=truncated,
        )
