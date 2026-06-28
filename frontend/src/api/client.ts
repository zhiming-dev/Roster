// Typed REST client for the Python runtime. Relative URLs work in both prod
// (FastAPI serves the SPA) and dev (Vite proxies /api → :8765).

import type { RosterEvent } from "../types/events";
import type { AgentInfo, ConversationSummary, QueueStats } from "../types/models";

export class ApiError extends Error {
  status: number;
  kind?: string;
  constructor(message: string, status: number, kind?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.kind = kind;
  }
}

async function getJson<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new ApiError(`HTTP ${r.status}`, r.status);
  return (await r.json()) as T;
}

async function postJson<T>(url: string): Promise<T> {
  const r = await fetch(url, { method: "POST" });
  if (!r.ok) throw new ApiError(`HTTP ${r.status}`, r.status);
  return (await r.json()) as T;
}

export interface AgentsResponse {
  runId: string;
  queue: QueueStats;
  agents: AgentInfo[];
}
export interface QueueResponse {
  runId: string;
  queue: QueueStats;
}
export interface ConversationsResponse {
  conversations: ConversationSummary[];
  active: string | null;
}
export interface ConversationEventsResponse {
  id: string;
  events: RosterEvent[];
  active?: string | null;
}

export const api = {
  getAgents: () => getJson<AgentsResponse>("/api/agents"),
  getQueue: () => getJson<QueueResponse>("/api/queue"),
  listConversations: () => getJson<ConversationsResponse>("/api/conversations"),
  getConversation: (id: string) =>
    getJson<ConversationEventsResponse>(`/api/conversations/${encodeURIComponent(id)}`),
  activateConversation: (id: string) =>
    postJson<ConversationEventsResponse>(
      `/api/conversations/${encodeURIComponent(id)}/activate`,
    ),
  reset: () => postJson<{ runId: string }>("/api/reset"),

  async deleteConversation(id: string): Promise<{ ok: boolean; active: string | null }> {
    const r = await fetch(`/api/conversations/${encodeURIComponent(id)}`, {
      method: "DELETE",
    });
    if (!r.ok) throw new ApiError(`HTTP ${r.status}`, r.status);
    return (await r.json()) as { ok: boolean; active: string | null };
  },

  // POST /api/chat resolves with the planner's final reply, or throws ApiError
  // carrying the backend's {error, kind} on a 4xx/5xx.
  async sendChat(message: string): Promise<{ reply: string; runId: string }> {
    const r = await fetch("/api/chat", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ message }),
    });
    let data: { reply?: string; runId?: string; error?: string; kind?: string };
    try {
      data = (await r.json()) as typeof data;
    } catch {
      throw new ApiError(`HTTP ${r.status}`, r.status);
    }
    if (!r.ok || data.error) {
      throw new ApiError(data.error || `HTTP ${r.status}`, r.status, data.kind);
    }
    return { reply: data.reply ?? "", runId: data.runId ?? "" };
  },
};
