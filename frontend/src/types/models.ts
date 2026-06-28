// Domain primitives and DTOs shared across the app. These mirror the Python
// runtime's REST/WS payloads exactly (see runtime/roster/server.py, bus.py,
// store.py, search.py) so the UI consumes the backend contract without changes.

export type AgentStatusValue = "idle" | "queued" | "thinking" | "searching" | "error";
export type MessageSubkind = "message" | "thinking" | "task_assignment" | "task_result";
export type SearchPhase = "query" | "results" | "error";

export interface SearchResult {
  title: string;
  url: string;
  snippet: string;
}

// queue_stats() in runtime/roster/orchestrator.py
export interface QueueStats {
  max_concurrency: number;
  waiting: number;
  active: number;
  require_queue: string[];
  search: string | null;
}

// One agent from GET /api/agents (provider fields come from provider.public_dict()).
export interface AgentInfo {
  name: string;
  role: string;
  status: AgentStatusValue;
  queued: boolean;
  queue_waiting: number;
  search: boolean;
  tools: string[];
  description: string;
  system_prompt_chars: number;
  provider: string;
  endpoint: string;
  model: string;
  auth: string;
  emoji: string;
  color: string | null;
}

// One row from GET /api/conversations (store._list_conversations).
export interface ConversationSummary {
  id: string;
  title: string;
  created_at: number;
  updated_at: number;
  messages: number;
}

// ---- UI-derived models (not wire shapes) ----

export interface ChatMessage {
  id: string;
  side: "user" | "agent";
  author: string; // "you" or the agent name
  role: string; // role used for color coding
  content: string;
  error?: boolean;
  ts: number;
  trace?: TraceItem[]; // collapsible per-answer process record
}

export type ActivityCategory = "message" | "search" | "error";

export interface ActivityItem {
  id: string;
  ts: number;
  category: ActivityCategory;
  subkind: string; // message subkind, search phase, or "error"
  from: string;
  to?: string;
  label: string; // short tag, e.g. "task assignment" or "search · results"
  role: string; // for color
  body: string;
  results?: SearchResult[];
}

export interface LineageNode {
  key: string; // "you" or the agent name
  name: string;
  role: string;
  status: AgentStatusValue;
  emoji: string;
  color: string | null; // custom hex, or null → role theme color
  you?: boolean;
}

export interface LineageEdge {
  id: string; // `${from}|${to}`
  from: string;
  to: string;
}

// A structured step in the orchestration trace — shown live in chat and kept as a
// collapsible record under each answer. `plan`/`critique` render as rich cards; the
// rest as one-line steps.
export type TraceItem =
  | { id: string; kind: "thinking"; role: string; text: string }
  | { id: string; kind: "plan"; summary: string; tasks: { role: string; task: string }[] }
  | { id: string; kind: "dispatch"; role: string }
  | {
      id: string;
      kind: "search";
      agent: string;
      role: string;
      phase: SearchPhase;
      text: string;
      tone?: "error";
    }
  | { id: string; kind: "result"; role: string }
  | { id: string; kind: "critique"; round: number; concern: string; action: string; to: string | null };

type DistribOmit<T, K extends keyof T> = T extends unknown ? Omit<T, K> : never;
export type NewTraceItem = DistribOmit<TraceItem, "id">;

export type ConnectionState = "connecting" | "open" | "reconnecting" | "closed";
export type ThemePref = "light" | "dark" | "system";
