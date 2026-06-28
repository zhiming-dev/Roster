// The event reducer: maps one backend event (live or replayed) to store
// mutations. Also builds the per-turn progress trace (shown live in chat, then
// attached to the answer as a collapsible record).

import type {
  AgentMessageEvent,
  RosterEvent,
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
      s.setAwaitingInput(true);
      break;
    }
    case "task.dispatched":
    case "clarification.answered":
      // Surfaced via agent.message / critique paths; no extra progress line.
      break;
  }
}
