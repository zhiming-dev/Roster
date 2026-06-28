// The discriminated union of live/replayed events. Every bus event is
// `{ kind, ts, ...payload }` (runtime/roster/bus.py:publish).

import type {
  AgentStatusValue,
  MessageSubkind,
  QueueStats,
  SearchPhase,
  SearchResult,
} from "./models";

interface BaseEvent {
  kind: string;
  ts: number;
}

export interface UserMessageEvent extends BaseEvent {
  kind: "user.message";
  from: string;
  to: string;
  content: string;
}

export interface AgentMessageEvent extends BaseEvent {
  kind: "agent.message";
  subkind?: MessageSubkind;
  from: string;
  to: string;
  content: string;
}

export interface AgentStatusEvent extends BaseEvent {
  kind: "agent.status";
  agent: string;
  role: string;
  provider: string;
  model: string;
  endpoint: string;
  status: AgentStatusValue;
  queued: boolean;
  search: boolean;
  queue_waiting?: number;
  queue_active?: number;
  queue_max?: number;
  query?: string;
  error?: string;
}

export interface ToolSearchEvent extends BaseEvent {
  kind: "tool.search";
  agent: string;
  phase: SearchPhase;
  query: string;
  count?: number;
  results?: SearchResult[];
  error?: string;
}

export interface RuntimeErrorEvent extends BaseEvent {
  kind: "runtime.error";
  scope?: string;
  error: string;
}

export interface RunStartedEvent extends BaseEvent {
  kind: "run.started";
  runId: string;
  queue: QueueStats;
}

// Orchestration events (spec 001). Emitted by runtime/roster/events.py.
export interface PlanProposedEvent extends BaseEvent {
  kind: "plan.proposed";
  runId: string;
  summary: string;
  tasks: { role: string; task: string }[];
}

export interface TaskDispatchedEvent extends BaseEvent {
  kind: "task.dispatched";
  from: string;
  to: string;
  task: string;
  round: number;
}

export interface CritiqueRoundEvent extends BaseEvent {
  kind: "critique.round";
  round: number;
  concern: string;
  action: string; // "verify" | "re-dispatch"
  to: string | null;
}

export interface ClarificationRequestedEvent extends BaseEvent {
  kind: "clarification.requested";
  question: string;
}

export interface ClarificationAnsweredEvent extends BaseEvent {
  kind: "clarification.answered";
  answer: string;
}

export type RosterEvent =
  | UserMessageEvent
  | AgentMessageEvent
  | AgentStatusEvent
  | ToolSearchEvent
  | RuntimeErrorEvent
  | RunStartedEvent
  | PlanProposedEvent
  | TaskDispatchedEvent
  | CritiqueRoundEvent
  | ClarificationRequestedEvent
  | ClarificationAnsweredEvent;

const KNOWN_KINDS = new Set([
  "user.message",
  "agent.message",
  "agent.status",
  "tool.search",
  "runtime.error",
  "run.started",
  "plan.proposed",
  "task.dispatched",
  "critique.round",
  "clarification.requested",
  "clarification.answered",
]);

// Narrow an unknown JSON value (a /ws frame or a replayed event) to a RosterEvent,
// or null if it isn't a kind we handle. Forward-compatible: unknown kinds ignored.
export function parseEvent(raw: unknown): RosterEvent | null {
  if (raw && typeof raw === "object" && "kind" in raw) {
    const kind = (raw as { kind: unknown }).kind;
    if (typeof kind === "string" && KNOWN_KINDS.has(kind)) {
      return raw as RosterEvent;
    }
  }
  return null;
}
