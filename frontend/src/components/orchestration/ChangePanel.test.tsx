import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { changeApi } from "../../api/change";
import { handleEvent } from "../../store/handleEvent";
import { useStore } from "../../store/store";
import type { CodeChange } from "../../types/change";
import { ChangePanel } from "./ChangePanel";

vi.mock("../../api/change", () => ({ changeApi: { get: vi.fn(), start: vi.fn(), decide: vi.fn(), decideAction: vi.fn() } }));
vi.mock("../../store/actions", () => ({ refreshConversations: vi.fn().mockResolvedValue(undefined) }));

const plan: CodeChange = {
  id: "change_test", runId: "run_test", phase: "plan", goal: "Change VALUE to 2",
  testCommand: "python verify.py", baseCommit: "a".repeat(40), gateId: "plan_test",
  message: "Review the plan before approving",
  plan: { notes: "Change src/app.py only", tasks: [{ id: "task_1", assigneeRole: "coder", description: "Change VALUE", successCriteria: "VALUE is 2" }] },
};

beforeEach(() => {
  vi.resetAllMocks();
  useStore.getState().resetView();
  useStore.setState({ runId: "run_test", awaiting: false, connection: "open" });
});

describe("Code change decisions", () => {
  it("requires a test command before preparing a plan", async () => {
    vi.mocked(changeApi.get).mockResolvedValue({ runId: "run_test", change: null, workspaceReady: true });
    vi.mocked(changeApi.start).mockImplementation(async () => {
      vi.mocked(changeApi.get).mockResolvedValue({ runId: "run_test", change: plan, workspaceReady: true });
      return { runId: "run_test", change: plan };
    });
    render(<ChangePanel />);
    fireEvent.change(screen.getByLabelText("What should change?"), { target: { value: plan.goal } });
    expect(screen.getByRole("button", { name: "Prepare plan" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Test command"), { target: { value: plan.testCommand } });
    await waitFor(() => expect(screen.getByRole("button", { name: "Prepare plan" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Prepare plan" }));
    expect(await screen.findByRole("button", { name: "Approve plan and run" })).toBeVisible();
    expect(changeApi.start).toHaveBeenCalledWith(plan.goal, plan.testCommand);
    expect(changeApi.decide).not.toHaveBeenCalled();
    expect(screen.queryByRole("link", { name: "Download approved patch" })).not.toBeInTheDocument();
  });

  it("uses distinct gates and offers a download only after diff approval", async () => {
    const diff: CodeChange = { ...plan, phase: "diff", gateId: "prop_diff", message: "Review the diff", patch: "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-old\n+new\n" };
    vi.mocked(changeApi.get).mockResolvedValue({ runId: "run_test", change: plan });
    vi.mocked(changeApi.decide).mockImplementation(async (gateId) => {
      const next: CodeChange = gateId === plan.gateId ? diff : { ...diff, phase: "delivered", downloadUrl: "/api/changes/run_test/patch" };
      vi.mocked(changeApi.get).mockResolvedValue({ runId: "run_test", change: next });
      return { runId: "run_test", change: next };
    });
    render(<ChangePanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Approve plan and run" }));
    fireEvent.click(await screen.findByRole("button", { name: "Approve diff and prepare patch" }));
    expect(await screen.findByRole("link", { name: "Download approved patch" })).toHaveAttribute("href", "/api/changes/run_test/patch");
    expect(changeApi.decide).toHaveBeenNthCalledWith(1, "plan_test", "approve");
    expect(changeApi.decide).toHaveBeenNthCalledWith(2, "prop_diff", "approve");
  });

  it("keeps a failed approval visible and shows the server error", async () => {
    vi.mocked(changeApi.get).mockResolvedValue({ runId: "run_test", change: plan });
    vi.mocked(changeApi.decide).mockRejectedValue(new Error("Decision is stale"));
    render(<ChangePanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Approve plan and run" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Decision is stale");
    await waitFor(() => expect(screen.getByRole("button", { name: "Approve plan and run" })).toBeEnabled());
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("ignores workflow events from another conversation", () => {
    handleEvent({ kind: "change.state", runId: "run_other", ts: 0, change: plan });
    expect(useStore.getState().change).toBeNull();
    handleEvent({ kind: "change.state", runId: "run_test", ts: 1, change: plan });
    expect(useStore.getState().change?.gateId).toBe("plan_test");
    useStore.getState().resetView();
    expect(useStore.getState().change).toBeNull();
  });
});
