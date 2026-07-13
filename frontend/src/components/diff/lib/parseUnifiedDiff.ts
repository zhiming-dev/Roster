// Pure unified-diff parser (spec 004, T023): `git diff` text → files → hunks → lines,
// with old/new line numbers for the DiffView gutters. No DOM, no store — unit-testable.

import type { DiffStatus } from "../../../types/models";

export interface DiffLine {
  type: "add" | "del" | "context";
  oldNo: number | null; // null for added lines
  newNo: number | null; // null for deleted lines
  text: string; // without the +/-/space prefix
}

export interface DiffHunk {
  header: string; // the raw @@ line (incl. any function context)
  lines: DiffLine[];
}

export interface DiffFile {
  path: string; // new path (or old path when deleted)
  oldPath: string;
  status: DiffStatus;
  additions: number;
  deletions: number;
  binary: boolean;
  hunks: DiffHunk[];
}

const HUNK_RE = /^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/;

/** Strip git's `a/` / `b/` prefix (also handles quoted paths). */
function cleanPath(p: string): string {
  let s = p.trim();
  if (s.startsWith('"') && s.endsWith('"')) s = s.slice(1, -1);
  if (s.startsWith("a/") || s.startsWith("b/")) s = s.slice(2);
  return s;
}

function newFile(): DiffFile {
  return {
    path: "",
    oldPath: "",
    status: "modified",
    additions: 0,
    deletions: 0,
    binary: false,
    hunks: [],
  };
}

export function parseUnifiedDiff(patch: string): DiffFile[] {
  const files: DiffFile[] = [];
  let file: DiffFile | null = null;
  let hunk: DiffHunk | null = null;
  let oldNo = 0;
  let newNo = 0;
  let oldLeft = 0; // remaining lines the hunk header promised — guards against
  let newLeft = 0; // swallowing trailing junk (e.g. the split's final "") as context

  for (const line of (patch || "").split("\n")) {
    if (line.startsWith("diff --git ")) {
      // `diff --git a/<old> b/<new>` — split on ` b/` to survive spaces in paths.
      file = newFile();
      files.push(file);
      hunk = null;
      const rest = line.slice("diff --git ".length);
      const cut = rest.lastIndexOf(" b/");
      if (cut >= 0) {
        file.oldPath = cleanPath(rest.slice(0, cut));
        file.path = cleanPath(rest.slice(cut + 1));
      } else {
        file.path = file.oldPath = cleanPath(rest);
      }
      continue;
    }
    if (!file) continue;

    if (line.startsWith("new file mode")) {
      file.status = "added";
    } else if (line.startsWith("deleted file mode")) {
      file.status = "deleted";
    } else if (line.startsWith("rename from ")) {
      file.status = "renamed";
      file.oldPath = cleanPath(line.slice("rename from ".length));
    } else if (line.startsWith("rename to ")) {
      file.status = "renamed";
      file.path = cleanPath(line.slice("rename to ".length));
    } else if (line.startsWith("Binary files ") || line === "GIT binary patch") {
      file.binary = true;
    } else if (line.startsWith("--- ")) {
      const p = line.slice(4);
      if (p !== "/dev/null") file.oldPath = cleanPath(p);
    } else if (line.startsWith("+++ ")) {
      const p = line.slice(4);
      if (p !== "/dev/null") file.path = cleanPath(p);
      else file.path = file.oldPath; // deleted file: show its old path
    } else {
      const m = HUNK_RE.exec(line);
      if (m) {
        oldNo = parseInt(m[1], 10);
        oldLeft = m[2] !== undefined ? parseInt(m[2], 10) : 1;
        newNo = parseInt(m[3], 10);
        newLeft = m[4] !== undefined ? parseInt(m[4], 10) : 1;
        hunk = { header: line, lines: [] };
        file.hunks.push(hunk);
      } else if (hunk && (oldLeft > 0 || newLeft > 0)) {
        if (line.startsWith("+")) {
          hunk.lines.push({ type: "add", oldNo: null, newNo: newNo++, text: line.slice(1) });
          file.additions++;
          newLeft--;
        } else if (line.startsWith("-")) {
          hunk.lines.push({ type: "del", oldNo: oldNo++, newNo: null, text: line.slice(1) });
          file.deletions++;
          oldLeft--;
        } else if (line.startsWith(" ") || line === "") {
          hunk.lines.push({
            type: "context",
            oldNo: oldNo++,
            newNo: newNo++,
            text: line.slice(1),
          });
          oldLeft--;
          newLeft--;
        }
        // `\ No newline at end of file` and anything else: ignored, not a content line.
      }
    }
  }
  return files;
}
