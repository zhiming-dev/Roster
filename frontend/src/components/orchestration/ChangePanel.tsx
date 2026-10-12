import { useEffect, useState } from "react";
import { changeApi } from "../../api/change";
import { refreshConversations } from "../../store/actions";
import { useStore } from "../../store/store";
import { DiffView } from "../diff/DiffView";
import styles from "./change.module.css";

const phases = ["Plan", "Coder", "Reviewer", "Tests", "Diff review", "Patch"];
const phaseIndex: Record<string, number> = {
  planning: 0, plan: 0, coding: 1, action: 1, reviewing: 2, testing: 3, diff: 4, delivered: 5,
};

export function ChangePanel() {
  const change = useStore((s) => s.change);
  const setChange = useStore((s) => s.setChange);
  const approval = useStore((s) => s.approval);
  const setApproval = useStore((s) => s.setApproval);
  const runId = useStore((s) => s.runId);
  const connection = useStore((s) => s.connection);
  const awaiting = useStore((s) => s.awaiting);
  const setAwaiting = useStore((s) => s.setAwaiting);
  const [goal, setGoal] = useState("");
  const [command, setCommand] = useState("");
  const [error, setError] = useState("");
  const [workspace, setWorkspace] = useState<string | null>("Checking workspace…");

  useEffect(() => {
    let cancelled = false;
    void changeApi.get().then((data) => {
      if (cancelled || data.runId !== useStore.getState().runId) return;
      setChange(data.change);
      setApproval(data.approval ?? null);
      setWorkspace(data.workspaceReady ? null : data.workspaceError || "Set a target repository in Setup, then apply it to a new chat.");
    }).catch((e: Error) => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, [runId, connection, setChange, setApproval]);

  const perform = async (operation: () => Promise<unknown>) => {
    if (awaiting) return;
    setError("");
    setAwaiting(true);
    try {
      await operation();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      try {
        const data = await changeApi.get();
        if (data.runId === useStore.getState().runId) {
          setChange(data.change);
          setApproval(data.approval ?? null);
        }
        await refreshConversations();
      } catch { /* A transport error is already visible above. */ }
      setAwaiting(false);
    }
  };

  const deciding = change?.phase === "plan" || change?.phase === "diff";
  const activeIndex = phaseIndex[change?.phase ?? "planning"];

  return (
    <section className={styles.panel} aria-label="Code change">
      <h2>Code change</h2>
      <p>Approve a plan, inspect the verified diff, then download your patch.</p>
      <ol className={styles.steps}>
        {phases.map((phase, index) => (
          <li key={phase} aria-current={change && index === activeIndex ? "step" : undefined}>{phase}</li>
        ))}
      </ol>
      {error && <p role="alert" className={styles.error}>{error}</p>}
      {!change ? (
        <form onSubmit={(event) => { event.preventDefault(); void perform(() => changeApi.start(goal, command)); }}>
          {workspace && <p role="status">{workspace}</p>}
          <label>What should change?
            <textarea required value={goal} onChange={(event) => setGoal(event.target.value)} disabled={awaiting} rows={4} />
          </label>
          <label>Test command
            <input required value={command} onChange={(event) => setCommand(event.target.value)} disabled={awaiting} placeholder="For example: python -m pytest" />
          </label>
          <p>The command runs from the repository root and must return a failing exit code when tests fail.</p>
          <button disabled={awaiting || !!workspace || !goal.trim() || !command.trim()} type="submit">Prepare plan</button>
        </form>
      ) : (
        <>
          <p role="status"><strong>{change.message}</strong></p>
          <h3>Request</h3><p className={styles.text}>{change.goal}</p>
          {change.plan && <details open={change.phase === "plan"}>
            <summary>Implementation plan</summary>
            <pre>{change.plan.notes}</pre>
            <ol>{change.plan.tasks.map((task) => <li key={task.id}><strong>{task.assigneeRole}</strong>: {task.successCriteria}</li>)}</ol>
          </details>}
          <p>Approved test command: <code>{change.testCommand}</code></p>
          {change.review && <details open={change.phase === "blocked"}><summary>Reviewer findings</summary><pre>{change.review}</pre></details>}
          {change.testResult && <details open={change.phase === "blocked"}>
            <summary>Test evidence · exit {change.testResult.exit_code ?? "unavailable"}{change.testResult.timed_out ? " · timed out" : ""}</summary>
            <pre>{change.testResult.stdout}{"\n"}{change.testResult.stderr}</pre>
          </details>}
          {change.patch && <><h3>Diff</h3><DiffView patch={change.patch} /></>}
          {deciding && change.gateId && <div className={styles.actions}>
            <button disabled={awaiting} onClick={() => void perform(() => changeApi.decide(change.gateId!, "approve"))}>
              {change.phase === "plan" ? "Approve plan and run" : "Approve diff and prepare patch"}
            </button>
            <button disabled={awaiting} onClick={() => void perform(() => changeApi.decide(change.gateId!, "reject"))}>Reject</button>
          </div>}
          {change.phase === "action" && approval && <div className={styles.actions}>
            <p>{approval.summary}</p><pre>{approval.action}</pre>
            <button disabled={awaiting} onClick={() => void perform(() => changeApi.decideAction(approval.propId, "approve"))}>Approve action</button>
            <button disabled={awaiting} onClick={() => void perform(() => changeApi.decideAction(approval.propId, "reject"))}>Reject action</button>
          </div>}
          {change.phase === "delivered" && change.downloadUrl && <div className={styles.delivery}>
            <a href={change.downloadUrl} download="change.patch">Download approved patch</a>
            <p>Apply from a clean checkout of commit <code>{change.baseCommit}</code>.</p>
            <pre>{"git apply --check /path/to/change.patch\ngit apply /path/to/change.patch"}</pre>
          </div>}
          {["blocked", "rejected", "delivered"].includes(change.phase) && <p>Start a new chat for another change or a revised request. The current worktree is preserved.</p>}
        </>
      )}
    </section>
  );
}
