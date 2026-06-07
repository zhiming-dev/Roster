---
name: researcher-runner
description: "Procedure the Researcher agent follows to answer a question with web search: plan queries, search, cross-check, and return a source-cited synthesis. Use when a task needs current or external facts."
argument-hint: "<research question from the Planner>"
---

# Researcher runner

The runbook for the **Researcher** sub-agent. The runtime injects the concrete
`SEARCH:` tool protocol into your system prompt; this skill is the *method* you apply.

## Procedure

1. **Decompose the question.** Identify the specific facts you need (e.g. index level +
   % change for three indexes, plus the top drivers). One search rarely covers all of
   it.
2. **Search iteratively.** Issue a focused query, read the results, then refine. Prefer
   2–3 narrow queries over one broad one. You have a budget of 3 searches per turn.
3. **Cross-check.** When a number matters, try to see it in more than one result. Note
   disagreements rather than silently picking one.
4. **Synthesize with citations.** Map each material claim to the URL it came from. Keep
   it tight.
5. **Declare gaps.** Anything you could not verify goes in an explicit "could not verify"
   line. Never paper over a gap with a plausible guess.

## Query tips

- Put dates in ISO form and include the year (`2026-06-05`).
- For markets/news, name the source class you want (`Reuters`, `site:cnbc.com`).
- If the first results are low quality, reformulate — don't settle for noise.

## Anti-patterns (do not do these)

- Returning a confident table of numbers with **no** source URLs.
- Treating today's or a past date as "the future" and refusing to look.
- Expanding scope into a general essay the Planner didn't ask for.
- Fabricating a result when search fails — report the failure instead.
