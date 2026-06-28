import { ApiError } from "./client";

export interface AgentCfg {
  name: string;
  role: string;
  emoji: string;
  color: string | null;
  persona: string;
  provider: string | null;
  endpoint: string | null;
  model: string | null;
  auth: string;
  options: { temperature: number | null; max_tokens: number | null };
  tools: string[];
  system_prompt_max_chars: number | null;
  key_status: "none" | "inline" | "env";
  is_planner: boolean;
}

export interface SearchCfg {
  enabled: boolean;
  provider: string;
  max_results: number;
  key_status: string;
}

export interface TeamConfig {
  agents: AgentCfg[];
  search: SearchCfg;
  available: { providers: string[]; tools: string[]; search_providers: string[] };
  inline_keys: number;
}

async function send<T>(url: string, method: string, body?: unknown): Promise<T> {
  const r = await fetch(url, {
    method,
    headers: body !== undefined ? { "content-type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new ApiError(data.error || `HTTP ${r.status}`, r.status);
  return data as T;
}

type Ok = { ok: boolean; moved?: number };

export const configApi = {
  get: () => send<TeamConfig>("/api/config", "GET"),
  updateAgent: (name: string, patch: Record<string, unknown>) =>
    send<Ok>(`/api/config/agents/${encodeURIComponent(name)}`, "PUT", patch),
  addAgent: (spec: Record<string, unknown>) => send<Ok>("/api/config/agents", "POST", spec),
  deleteAgent: (name: string) =>
    send<Ok>(`/api/config/agents/${encodeURIComponent(name)}`, "DELETE"),
  updateSearch: (patch: Record<string, unknown>) => send<Ok>("/api/config/search", "PUT", patch),
  migrateKeys: () => send<Ok>("/api/config/migrate-keys", "POST", {}),
  reset: () => send<{ runId: string }>("/api/reset", "POST", {}),
};
