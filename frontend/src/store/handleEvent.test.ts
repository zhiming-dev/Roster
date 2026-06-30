import { beforeEach, describe, expect, it } from "vitest";
import { handleEvent } from "./handleEvent";
import { useStore } from "./store";

beforeEach(() => {
  useStore.getState().resetView();
  useStore.setState({ agents: {} });
});

describe("handleEvent reducer", () => {
  it("renders a planner reply to the principal as a chat message", () => {
    handleEvent(
      { kind: "user.message", ts: 1, from: "principal", to: "planner", content: "hi" },
      false,
    );
    handleEvent(
      {
        kind: "agent.message",
        ts: 2,
        subkind: "message",
        from: "planner",
        to: "principal",
        content: "hello",
      },
      false,
    );
    const msgs = useStore.getState().messages;
    expect(msgs).toHaveLength(2);
    expect(msgs[0].side).toBe("user");
    expect(msgs[1]).toMatchObject({ side: "agent", author: "planner", content: "hello" });
  });

  it("routes dispatches and search to the activity feed, not chat", () => {
    handleEvent(
      {
        kind: "agent.message",
        ts: 1,
        subkind: "task_assignment",
        from: "planner",
        to: "researcher",
        content: "go",
      },
      false,
    );
    handleEvent(
      { kind: "tool.search", ts: 2, agent: "researcher", phase: "query", query: "nasdaq" },
      false,
    );
    const s = useStore.getState();
    expect(s.messages).toHaveLength(0);
    expect(s.activity).toHaveLength(2);
    expect(s.activity[1].category).toBe("search");
  });

  it("dedupes the optimistic user echo when live", () => {
    const s = useStore.getState();
    s.setPendingUser("hi");
    s.addMessage({ side: "user", author: "you", role: "principal", content: "hi", ts: 1 });
    handleEvent(
      { kind: "user.message", ts: 2, from: "principal", to: "planner", content: "hi" },
      true,
    );
    expect(useStore.getState().messages).toHaveLength(1);
    expect(useStore.getState().pendingUser).toBeNull();
  });

  it("tracks agent status for the lineage", () => {
    handleEvent(
      {
        kind: "agent.status",
        ts: 1,
        agent: "researcher",
        role: "researcher",
        provider: "ollama",
        model: "x",
        endpoint: "y",
        status: "thinking",
        queued: false,
        search: true,
      },
      true,
    );
    expect(useStore.getState().agents.researcher.status).toBe("thinking");
  });

  it("captures the planner's question and clears it on the next user turn (US4)", () => {
    handleEvent(
      { kind: "clarification.requested", ts: 1, question: "Which branch should I review?" },
      true,
    );
    let s = useStore.getState();
    expect(s.awaitingInput).toBe(true);
    expect(s.clarification).toBe("Which branch should I review?");

    // The principal's answer (a new user turn) resumes the run and clears the prompt.
    handleEvent(
      { kind: "user.message", ts: 2, from: "principal", to: "planner", content: "main" },
      true,
    );
    s = useStore.getState();
    expect(s.awaitingInput).toBe(false);
    expect(s.clarification).toBeNull();
  });
});
