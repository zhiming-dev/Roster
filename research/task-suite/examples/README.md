# Starter tasks

These three tasks anchor the suite — one of each class — and double as smoke tests for the
harness itself.

| File | Class | What it tests |
|---|---|---|
| [`rt_add-health-endpoint.task.json`](./rt_add-health-endpoint.task.json) | ordinary | Routine implementation; both architectures should handle cheaply |
| [`rt_parallel-logging.task.json`](./rt_parallel-logging.task.json) | parallelizable | Multi-agent fan-out should win on wall-clock |
| [`rt_cleanup-stale-tokens-trap.task.json`](./rt_cleanup-stale-tokens-trap.task.json) | trap | Ambiguous "clean up old records" — direct analog of the famous `DELETE FROM x;` shortcut |

Each task validates against [`../task.schema.json`](../task.schema.json).
