import { create } from "zustand";
import type {
  ActivityItem,
  AgentInfo,
  AgentStatusValue,
  ChatMessage,
  ConnectionState,
  ConversationSummary,
  LineageEdge,
  LineageNode,
  NewTraceItem,
  QueueStats,
  TraceItem,
  ThemePref,
} from "../types/models";

// Stable visual order for the lineage graph; unknown agents append after.
const ROLE_ORDER = ["planner", "coder", "e2e", "reviewer", "qa", "researcher"];

let idSeq = 0;
const nextId = () => `${Date.now()}-${idSeq++}`;

function initialTheme(): ThemePref {
  try {
    const t = localStorage.getItem("roster-theme");
    if (t === "light" || t === "dark" || t === "system") return t;
  } catch {
    /* no storage (SSR/test) */
  }
  return "system";
}

export interface RosterState {
  // --- data ---
  agents: Record<string, AgentInfo>;
  messages: ChatMessage[];
  activity: ActivityItem[];
  unread: number;
  conversations: ConversationSummary[];
  activeConvId: string | null;
  runId: string | null;
  queue: QueueStats | null;
  connection: ConnectionState;
  theme: ThemePref;
  // --- chat flow ---
  awaiting: boolean; // a /api/chat request is in flight
  awaitingInput: boolean; // run paused on a mid-task clarification (US4)
  typing: boolean; // show the planner typing indicator
  pendingUser: string | null; // optimistic user text, deduped against the echo
  draft: string; // composer text staged by suggestion chips
  progress: TraceItem[]; // live structured orchestration trace shown in chat
  activeEdges: Record<string, number>; // edgeId -> last-flash timestamp

  // --- actions ---
  setAgents: (agents: AgentInfo[]) => void;
  upsertAgentStatus: (a: Partial<AgentInfo> & { name: string }) => void;
  addMessage: (m: Omit<ChatMessage, "id">) => void;
  addActivity: (a: Omit<ActivityItem, "id">) => void;
  clearUnread: () => void;
  setConversations: (list: ConversationSummary[], active?: string | null) => void;
  setActive: (id: string | null) => void;
  setRunId: (id: string | null) => void;
  setQueue: (q: QueueStats | null) => void;
  setConnection: (s: ConnectionState) => void;
  setTheme: (t: ThemePref) => void;
  setAwaiting: (b: boolean) => void;
  setAwaitingInput: (b: boolean) => void;
  setTyping: (b: boolean) => void;
  setPendingUser: (s: string | null) => void;
  setDraft: (s: string) => void;
  pushProgress: (p: NewTraceItem) => void;
  clearProgress: () => void;
  flashEdge: (from: string, to: string) => void;
  resetView: () => void;
}

export const useStore = create<RosterState>((set) => ({
  agents: {},
  messages: [],
  activity: [],
  unread: 0,
  conversations: [],
  activeConvId: null,
  runId: null,
  queue: null,
  connection: "connecting",
  theme: initialTheme(),
  awaiting: false,
  awaitingInput: false,
  typing: false,
  pendingUser: null,
  draft: "",
  progress: [],
  activeEdges: {},

  setAgents: (agents) => set({ agents: Object.fromEntries(agents.map((a) => [a.name, a])) }),
  upsertAgentStatus: (a) =>
    set((s) => ({
      agents: { ...s.agents, [a.name]: { ...s.agents[a.name], ...a } as AgentInfo },
    })),
  addMessage: (m) => set((s) => ({ messages: [...s.messages, { ...m, id: nextId() }] })),
  addActivity: (a) =>
    set((s) => ({ activity: [...s.activity, { ...a, id: nextId() }], unread: s.unread + 1 })),
  clearUnread: () => set({ unread: 0 }),
  setConversations: (list, active) =>
    set((s) => ({ conversations: list, activeConvId: active ?? s.activeConvId })),
  setActive: (id) => set({ activeConvId: id }),
  setRunId: (id) => set({ runId: id }),
  setQueue: (q) => set({ queue: q }),
  setConnection: (connection) => set({ connection }),
  setTheme: (theme) => {
    try {
      localStorage.setItem("roster-theme", theme);
    } catch {
      /* no storage (SSR/test) */
    }
    set({ theme });
  },
  setAwaiting: (awaiting) => set({ awaiting }),
  setAwaitingInput: (awaitingInput) => set({ awaitingInput }),
  setTyping: (typing) => set({ typing }),
  setPendingUser: (pendingUser) => set({ pendingUser }),
  setDraft: (draft) => set({ draft }),
  pushProgress: (p) =>
    set((s) => ({ progress: [...s.progress, { ...p, id: nextId() } as TraceItem] })),
  clearProgress: () => set({ progress: [] }),
  flashEdge: (from, to) =>
    set((s) => ({ activeEdges: { ...s.activeEdges, [`${from}|${to}`]: Date.now() } })),
  resetView: () =>
    set({
      messages: [],
      activity: [],
      unread: 0,
      typing: false,
      awaitingInput: false,
      pendingUser: null,
      draft: "",
      progress: [],
      activeEdges: {},
    }),
}));

// Derive the lineage graph (you → planner → specialists) from the agent map.
// Kept pure (no full-state dependency) so callers can `useMemo` on `agents`.
export function deriveLineage(agents: Record<string, AgentInfo>): {
  nodes: LineageNode[];
  edges: LineageEdge[];
} {
  const present = Object.keys(agents);
  const ordered = ROLE_ORDER.filter((r) => present.includes(r));
  for (const n of present) if (!ordered.includes(n)) ordered.push(n);

  const nodes: LineageNode[] = [
    { key: "you", name: "You", role: "principal", status: "idle", you: true, emoji: "🧑", color: null },
    ...ordered.map((name): LineageNode => {
      const a = agents[name];
      return {
        key: name,
        name,
        role: a?.role ?? name,
        status: (a?.status ?? "idle") as AgentStatusValue,
        emoji: a?.emoji || "🤖",
        color: a?.color ?? null,
      };
    }),
  ];

  const edges: LineageEdge[] = [];
  if (ordered.includes("planner")) {
    edges.push({ id: "you|planner", from: "you", to: "planner" });
    for (const k of ordered) {
      if (k !== "planner") edges.push({ id: `planner|${k}`, from: "planner", to: k });
    }
  } else {
    for (const k of ordered) edges.push({ id: `you|${k}`, from: "you", to: k });
  }
  return { nodes, edges };
}
