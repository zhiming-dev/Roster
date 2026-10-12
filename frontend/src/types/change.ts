export interface CodeChange {
  id: string;
  runId: string;
  phase: "planning" | "plan" | "coding" | "action" | "reviewing" | "testing" | "diff" | "delivered" | "rejected" | "blocked";
  goal: string;
  testCommand: string;
  baseCommit: string;
  message: string;
  gateId?: string;
  plan?: {
    notes: string;
    tasks: { id: string; assigneeRole: string; description: string; successCriteria: string }[];
  };
  patch?: string;
  patchHash?: string;
  review?: string;
  testResult?: { exit_code: number | null; stdout: string; stderr: string; timed_out: boolean };
  downloadUrl?: string;
}
