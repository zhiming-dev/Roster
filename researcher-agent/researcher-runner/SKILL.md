---
name: researcher-runner
description: "Procedure the Researcher agent follows to answer a question with web search + page fetch: plan queries, search, open the promising pages, cross-check, and return a source-cited synthesis. Use when a task needs current or external facts."
argument-hint: "<research question from the Planner>"
---

# Researcher runner

The runbook for the **Researcher** sub-agent. The runtime injects the concrete
`SEARCH:` / `FETCH:` tool protocols into your system prompt; this skill is the *method*
you apply.

## Procedure

1. **Decompose the question.** Identify the specific facts you need (e.g. index level +
   % change for three indexes, plus the top drivers). One search rarely covers all of
   it.
2. **Search to locate, FETCH to read.** A search result is a lead: when one looks like it
   holds the answer, FETCH its url and take the fact from the page itself — never from
   the snippet. If you already know where the data lives (an official stats page, FRED,
   a filing), skip the search and FETCH the source directly. Budget: 3 searches and 6
   fetches per turn — spend fetches before extra searches.
3. **Cross-check.** When a number matters, try to see it in more than one fetched source.
   Note disagreements rather than silently picking one.
4. **Synthesize with citations.** Map each material claim to the URL it came from. Keep
   it tight.
5. **Declare gaps.** Anything you could not verify goes in an explicit "could not verify"
   line. Never paper over a gap with a plausible guess.

## Query & fetch tips

- Put dates in ISO form and include the year (`2026-06-05`).
- For markets/news, name the source class you want (`Reuters`, `site:cnbc.com`).
- A search engine returns pages, not data points — never expect a query like
  `"index value on 2026-04-12"` to answer itself; find the data's home and FETCH it.
- Data endpoints beat articles: e.g. any FRED series is plain CSV at
  `https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIES>`.
- If the first results are low quality, reformulate — don't settle for noise.

## Anti-patterns (do not do these)

- Returning a confident table of numbers with **no** source URLs.
- Citing a page you never fetched — a snippet is a lead, not evidence.
- Reporting "the data exists at <url> but I could not extract it" without having FETCHed
  that url.
- Treating today's or a past date as "the future" and refusing to look.
- Expanding scope into a general essay the Planner didn't ask for.
- Fabricating a result when search fails — report the failure instead.
