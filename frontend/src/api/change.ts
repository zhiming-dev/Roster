import { ApiError } from "./client";
import type { CodeChange } from "../types/change";
import type { PendingApprovalUi } from "../types/models";

export interface ChangeResponse {
  runId: string;
  change: CodeChange | null;
  workspaceReady?: boolean;
  workspaceError?: string | null;
  approval?: PendingApprovalUi | null;
}

async function request(url: string, body?: unknown): Promise<ChangeResponse> {
  const response = await fetch(url, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw new ApiError(data.error || "Request failed", response.status);
  return data;
}

export const changeApi = {
  get: () => request("/api/change"),
  start: (goal: string, testCommand: string) => request("/api/change", { goal, testCommand }),
  decide: (gateId: string, decision: "approve" | "reject") =>
    request(`/api/change/${encodeURIComponent(gateId)}`, { decision }),
  decideAction: (propId: string, decision: "approve" | "reject") =>
    request(`/api/approvals/${encodeURIComponent(propId)}`, { decision }),
};
