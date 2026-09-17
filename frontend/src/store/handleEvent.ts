// The event reducer: maps one backend event (live or replayed) to store
// mutations. Also builds the per-turn progress trace (shown live in chat, then
// attached to the answer as a collapsible record).

import type {
  AgentMessageEvent,
  RosterEvent,
  ToolCalcEvent,
  ToolExecEvent,
  ToolFetchEvent,
  ToolFileEvent,
  ToolMcpEvent,
  ToolSearchEvent,
} from "../types/events";
import type { ActivityItem } from "../types/models";
import { useStore } from "./store";

function roleOf(name: string): string {
  if (name === "principal") return "principal";
  return useStore.getState().agents[name]?.role ?? name;
}

const nodeName = (name: string) => (name === "principal" ? "you" : name);

// First non-empty line, truncated — keeps the planner's verbose "thinking" to one line.
function firstLine(s: string, max = 150): string {
  const line =
    (s || "")
      .split("\n")
      .map((l) => l.trim())
      .find((l) => l.length > 0) ?? "";
  return line.length > max ? line.slice(0, max - 1) + "…" : line;
}

function activityFromMessage(evt: AgentMessageEvent, sub: string): Omit<ActivityItem, "id"> {
  return {
    ts: evt.ts,
    category: "message",
    subkind: sub,
    from: evt.from,
    to: evt.to,
    label: sub.replace("_", " "),
    role: roleOf(evt.from),
    body: evt.content || "",
  };
}

function activityFromFile(evt: ToolFileEvent): Omit<ActivityItem, "id"> {
  let body = "";
  if (evt.phase === "read") body = evt.path ?? "";
  else if (evt.phase === "write") body = evt.path ?? "";
  else if (evt.phase === "diff") {
    const adds = (evt.files ?? []).reduce((n, f) => n + f.additions, 0);
    const dels = (evt.files ?? []).reduce((n, f) => n + f.deletions, 0);
    body = `${evt.files?.length ?? 0} file(s) changed, +${adds} −${dels}`;
  }
  return {
    ts: evt.ts,
    category: "tool",
    subkind: evt.phase,
    from: evt.agent,
    label: `file · ${evt.phase}`,
    role: roleOf(evt.agent),
    body,
    files: evt.files,
    patch: evt.patch,
  };
}

function activityFromExec(evt: ToolExecEvent): Omit<ActivityItem, "id"> {
  const body =
    evt.phase === "command"
      ? `$ ${evt.command}`
      : evt.timedOut
        ? `$ ${evt.command} — timed out`
        : `$ ${evt.command} — exit ${evt.exitCode ?? "?"}`;
  return {
    ts: evt.ts,
    category: "tool",
    subkind: evt.phase,
    from: evt.agent,
    label: `shell · ${evt.phase}`,
    role: roleOf(evt.agent),
    body,
  };
}

function activityFromSearch(evt: ToolSearchEvent): Omit<ActivityItem, "id"> {
  let body = "";
  if (evt.phase === "query") body = `“${evt.query}”`;
  else if (evt.phase === "results") body = `${evt.count ?? 0} results for “${evt.query}”`;
  else if (evt.phase === "error") body = `error for “${evt.query}”: ${evt.error ?? ""}`;
  return {
    ts: evt.ts,
    category: "search",
    subkind: evt.phase,
    from: evt.agent,
    label: `search · ${evt.phase}`,
    role: roleOf(evt.agent),
    body,
    results: evt.results,
  };
}

// Trim a url for one-line display: drop the scheme, keep host + tail of the path.
function shortUrl(url: string, max = 80): string {
  const u = (url || "").replace(/^https?:\/\//, "");
  return u.length > max ? u.slice(0, max - 1) + "…" : u;
}

function activityFromFetch(evt: ToolFetchEvent): Omit<ActivityItem, "id"> {
  let body = "";
  if (evt.phase === "request") body = evt.url;
  else if (evt.phase === "result")
    body = `${evt.finalUrl ?? evt.url} — HTTP ${evt.statusCode ?? "?"}, ${evt.chars ?? 0} chars${evt.truncated ? " (truncated)" : ""}`;
  else if (evt.phase === "error") body = `error for ${evt.url}: ${evt.error ?? ""}`;
  return {
    ts: evt.ts,
    category: "search",
    subkind: evt.phase,
    from: evt.agent,
    label: `fetch · ${evt.phase}`,
    role: roleOf(evt.agent),
    body,
  };
}

function activityFromCalc(evt: ToolCalcEvent): Omit<ActivityItem, "id"> {
  const body =
    evt.phase === "result" ? `${evt.expr} = ${evt.result ?? ""}` : `${evt.expr} — ${evt.error ?? "error"}`;
  return {
    ts: evt.ts,
    category: "tool",
    subkind: evt.phase,
    from: evt.agent,
    label: `calc · ${evt.phase}`,
    role: roleOf(evt.agent),
    body,
  };
}

function activityFromMcp(evt: ToolMcpEvent): Omit<ActivityItem, "id"> {
  let body = evt.tool;
  if (evt.phase === "result") body = `${evt.tool} — ${evt.chars ?? 0} chars`;
  else if (evt.phase === "error") body = `${evt.tool} — ${evt.error ?? "error"}`;
  return {
    ts: evt.ts,
    category: "tool",
    subkind: evt.phase,
    from: evt.agent,
    label: `tool · ${evt.phase}`,
    role: roleOf(evt.agent),
    body,
  };
}

export function handleEvent(evt: RosterEvent, live = true): void {
  const s = useStore.getState();
  switch (evt.kind) {
    case "user.message": {
      s.flashEdge("you", "planner");
      s.setAwaitingInput(false); // a new user turn — no longer paused on a question
      if (live && s.pendingUser !== null && evt.content === s.pendingUser) {
        s.setPendingUser(null); // the echo of our optimistic bubble
      } else {
        s.addMessage({
          side: "user",
          author: "you",
          role: "principal",
          content: evt.content,
          ts: evt.ts,
        });
      }
      break;
    }
    case "agent.message": {
      if (evt.from && evt.to) s.flashEdge(nodeName(evt.from), nodeName(evt.to));
      const sub = evt.subkind ?? "message";
      if (evt.to === "principal" && sub === "message") {
        // The planner's reply (or its mid-task question). Attach the accumulated
        // progress trace so it stays as a collapsible record under the bubble.
        const trace = s.progress;
        if (live) s.setTyping(false);
        s.clearProgress();
        const from = evt.from || "planner";
        s.addMessage({
          side: "agent",
          author: from,
          role: roleOf(from),
          content: evt.content || "",
          ts: evt.ts,
          trace: trace.length ? trace : undefined,
        });
      } else {
        s.addActivity(activityFromMessage(evt, sub));
        if (sub === "thinking") {
          s.pushProgress({ kind: "thinking", role: roleOf(evt.from), text: firstLine(evt.content) });
        } else if (sub === "task_assignment") {
          s.pushProgress({ kind: "dispatch", role: evt.to });
        } else if (sub === "task_result") {
          s.pushProgress({ kind: "result", role: evt.from });
        }
      }
      break;
    }
    case "agent.status": {
      s.upsertAgentStatus({
        name: evt.agent,
        role: evt.role,
        status: evt.status,
        queued: evt.queued,
        search: evt.search,
        provider: evt.provider,
        model: evt.model,
        endpoint: evt.endpoint,
        queue_waiting: evt.queue_waiting ?? 0,
      });
      break;
    }
    case "tool.search": {
      s.addActivity(activityFromSearch(evt));
      const r = roleOf(evt.agent);
      if (evt.phase === "query") {
        s.pushProgress({ kind: "search", agent: evt.agent, role: r, phase: "query", text: firstLine(evt.query, 60) });
      } else if (evt.phase === "results") {
        s.pushProgress({ kind: "search", agent: evt.agent, role: r, phase: "results", text: `${evt.count ?? 0} results` });
      } else if (evt.phase === "error") {
        s.pushProgress({ kind: "search", agent: evt.agent, role: r, phase: "error", text: "rate-limited", tone: "error" });
      }
      break;
    }
    case "tool.fetch": {
      s.addActivity(activityFromFetch(evt));
      const r = roleOf(evt.agent);
      if (evt.phase === "request") {
        s.pushProgress({ kind: "fetch", agent: evt.agent, role: r, phase: "request", text: shortUrl(evt.url) });
      } else if (evt.phase === "result") {
        s.pushProgress({ kind: "fetch", agent: evt.agent, role: r, phase: "result", text: `${evt.chars ?? 0} chars from ${shortUrl(evt.finalUrl ?? evt.url, 60)}` });
      } else if (evt.phase === "error") {
        s.pushProgress({ kind: "fetch", agent: evt.agent, role: r, phase: "error", text: `failed: ${shortUrl(evt.url, 60)}`, tone: "error" });
      }
      break;
    }
    case "tool.calc": {
      s.addActivity(activityFromCalc(evt));
      const r = roleOf(evt.agent);
      if (evt.phase === "result") {
        s.pushProgress({ kind: "calc", agent: evt.agent, role: r, text: `${firstLine(evt.expr, 60)} = ${firstLine(evt.result ?? "", 40)}` });
      } else {
        s.pushProgress({ kind: "calc", agent: evt.agent, role: r, text: `calc failed: ${firstLine(evt.error ?? "", 60)}`, tone: "error" });
      }
      break;
    }
    case "tool.mcp": {
      s.addActivity(activityFromMcp(evt));
      const r = roleOf(evt.agent);
      if (evt.phase === "call") {
        s.pushProgress({ kind: "mcp", agent: evt.agent, role: r, phase: "call", text: evt.tool });
      } else if (evt.phase === "result") {
        s.pushProgress({ kind: "mcp", agent: evt.agent, role: r, phase: "result", text: `${evt.tool} → ${evt.chars ?? 0} chars` });
      } else {
        s.pushProgress({ kind: "mcp", agent: evt.agent, role: r, phase: "error", text: `${evt.tool} failed`, tone: "error" });
      }
      break;
    }
    case "runtime.error": {
      if (live) s.setTyping(false);
      s.setAwaitingInput(false);
      s.clearProgress();
      s.addActivity({
        ts: evt.ts,
        category: "error",
        subkind: "error",
        from: "runtime",
        label: "error",
        role: "principal",
        body: (evt.scope ? `[${evt.scope}] ` : "") + (evt.error || ""),
      });
      break;
    }
    case "run.started": {
      if (evt.runId) s.setRunId(evt.runId);
      if (evt.queue) s.setQueue(evt.queue);
      break;
    }
    case "plan.proposed": {
      s.pushProgress({ kind: "plan", summary: evt.summary, tasks: evt.tasks });
      break;
    }
    case "critique.round": {
      s.pushProgress({
        kind: "critique",
        round: evt.round,
        concern: evt.concern,
        action: evt.action,
        to: evt.to,
      });
      break;
    }
    case "clarification.requested": {
      s.setClarification(evt.question);
      break;
    }
    // ---- tool execution + the approval gate (spec 004, US3) ----
    case "tool.file": {
      s.addActivity(activityFromFile(evt));
      const r = roleOf(evt.agent);
      if (evt.phase === "read") {
        s.pushProgress({ kind: "file", agent: evt.agent, role: r, phase: "read", path: evt.path, text: `${evt.agent} read ${evt.path ?? ""}` });
      } else if (evt.phase === "write") {
        s.pushProgress({ kind: "file", agent: evt.agent, role: r, phase: "write", path: evt.path, text: `${evt.agent} wrote ${evt.path ?? ""}` });
      } else if (evt.phase === "diff" && evt.patch) {
        const adds = (evt.files ?? []).reduce((n, f) => n + f.additions, 0);
        const dels = (evt.files ?? []).reduce((n, f) => n + f.deletions, 0);
        s.pushProgress({
          kind: "diff",
          agent: evt.agent,
          role: r,
          files: evt.files ?? [],
          patch: evt.patch,
          truncated: evt.truncated,
          text: `${evt.files?.length ?? 0} file(s) changed, +${adds} −${dels}`,
        });
      }
      break;
    }
    case "tool.exec": {
      s.addActivity(activityFromExec(evt));
      const r = roleOf(evt.agent);
      if (evt.phase === "command") {
        s.pushProgress({ kind: "exec", agent: evt.agent, role: r, command: evt.command, text: `$ ${firstLine(evt.command, 80)}` });
      } else {
        const failed = evt.timedOut || (evt.exitCode ?? 0) !== 0;
        s.pushProgress({
          kind: "exec",
          agent: evt.agent,
          role: r,
          command: evt.command,
          exitCode: evt.exitCode,
          text: evt.timedOut ? `$ ${firstLine(evt.command, 60)} — timed out` : `$ ${firstLine(evt.command, 60)} — exit ${evt.exitCode ?? "?"}`,
          tone: failed ? "error" : undefined,
        });
      }
      break;
    }
    case "approval.requested": {
      s.setApproval({
        propId: evt.propId,
        agent: evt.agent,
        tier: evt.tier,
        action: evt.action,
        summary: evt.summary,
      });
      s.addActivity({
        ts: evt.ts,
        category: "approval",
        subkind: "requested",
        from: evt.agent,
        label: `approval · ${evt.tier}`,
        role: roleOf(evt.agent),
        body: `${evt.action} — ${evt.summary}`,
      });
      s.pushProgress({
        kind: "approval",
        agent: evt.agent,
        role: roleOf(evt.agent),
        propId: evt.propId,
        tier: evt.tier,
        action: evt.action,
        summary: evt.summary,
        text: `${evt.agent} needs approval: ${firstLine(evt.action, 60)}`,
      });
      break;
    }
    case "approval.resolved": {
      s.markApprovalDecision(evt.propId, evt.decision);
      const current = useStore.getState().approval;
      if (current?.propId === evt.propId) s.setApproval(null);
      s.addActivity({
        ts: evt.ts,
        category: "approval",
        subkind: evt.decision,
        from: "principal",
        label: `approval · ${evt.decision}`,
        role: "principal",
        body: evt.propId,
      });
      break;
    }
    case "task.dispatched":
    case "clarification.answered":
      // Surfaced via agent.message / critique paths; no extra progress line.
      break;
  }
}
