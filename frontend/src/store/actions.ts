// Side-effecting flows that combine the REST client, the event reducer, and the
// store. Components call these; they keep async/replay logic out of the views.

import { api } from "../api/client";
import type { RosterEvent } from "../types/events";
import { handleEvent } from "./handleEvent";
import { useStore } from "./store";

function replay(events: RosterEvent[]): void {
  const s = useStore.getState();
  s.resetView();
  for (const e of events) handleEvent(e, false);
}

export async function refreshConversations(): Promise<void> {
  const s = useStore.getState();
  const c = await api.listConversations();
  s.setConversations(c.conversations, c.active ?? s.activeConvId);
}

export async function loadInitial(): Promise<void> {
  const s = useStore.getState();
  try {
    const a = await api.getAgents();
    s.setAgents(a.agents);
    s.setRunId(a.runId);
    s.setQueue(a.queue);
    s.setActive(a.runId);
    const c = await api.listConversations();
    s.setConversations(c.conversations, c.active ?? a.runId);
    if (a.runId) {
      const ev = await api.getConversation(a.runId);
      replay(ev.events);
    }
  } catch {
    /* backend not up yet — the WS hook keeps retrying and a banner is shown */
  }
}

export async function newChat(): Promise<void> {
  const s = useStore.getState();
  try {
    const r = await api.reset();
    s.setRunId(r.runId);
    s.setActive(r.runId);
    s.resetView();
    await refreshConversations();
  } catch {
    /* ignore — surfaced via connection banner */
  }
}

export async function openConversation(id: string): Promise<void> {
  const s = useStore.getState();
  if (id === s.activeConvId) return;
  try {
    const r = await api.activateConversation(id);
    s.setActive(id);
    s.setRunId(id);
    replay(r.events);
    await refreshConversations();
  } catch {
    /* ignore */
  }
}

export async function deleteConversation(id: string): Promise<void> {
  const s = useStore.getState();
  try {
    const r = await api.deleteConversation(id);
    if (id === s.activeConvId) {
      s.setActive(r.active);
      s.setRunId(r.active);
      s.resetView();
    }
    await refreshConversations();
  } catch {
    /* ignore */
  }
}

export async function sendMessage(text: string): Promise<void> {
  const s = useStore.getState();
  const t = text.trim();
  if (!t || s.awaiting) return;
  s.setPendingUser(t);
  s.addMessage({ side: "user", author: "you", role: "principal", content: t, ts: Date.now() / 1000 });
  s.clearProgress();
  s.setAwaitingInput(false);
  s.setTyping(true);
  s.setAwaiting(true);
  try {
    // The planner's final reply arrives over /ws as an agent.message to the
    // principal (the reducer renders it and clears typing). We only need the POST
    // to surface transport/runtime errors.
    await api.sendChat(t);
    await refreshConversations(); // title/updated_at may have changed
  } catch (e) {
    s.setTyping(false);
    const msg = e instanceof Error ? e.message : String(e);
    s.addMessage({
      side: "agent",
      author: "planner",
      role: "planner",
      content: "⚠︎ " + msg,
      error: true,
      ts: Date.now() / 1000,
    });
  } finally {
    s.setAwaiting(false);
  }
}
