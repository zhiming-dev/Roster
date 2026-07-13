import { describe, expect, it } from "vitest";
import { parseUnifiedDiff } from "./parseUnifiedDiff";

const MODIFY = `diff --git a/src/app.py b/src/app.py
index 1234567..89abcde 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,3 +1,4 @@ def main():
 VALUE = 1
-OLD = True
+NEW = True
+ADDED = 2
 END = None
`;

const ADD = `diff --git a/src/helper.py b/src/helper.py
new file mode 100644
index 0000000..abc1234
--- /dev/null
+++ b/src/helper.py
@@ -0,0 +1,2 @@
+def help():
+    return 1
`;

const DELETE = `diff --git a/gone.txt b/gone.txt
deleted file mode 100644
index abc1234..0000000
--- a/gone.txt
+++ /dev/null
@@ -1,1 +0,0 @@
-bye
`;

const RENAME = `diff --git a/old_name.py b/new_name.py
similarity index 92%
rename from old_name.py
rename to new_name.py
index 1234567..89abcde 100644
--- a/old_name.py
+++ b/new_name.py
@@ -1,2 +1,2 @@
 keep
-x = 1
+x = 2
`;

const BINARY = `diff --git a/logo.png b/logo.png
new file mode 100644
index 0000000..abc1234
Binary files /dev/null and b/logo.png differ
`;

describe("parseUnifiedDiff", () => {
  it("parses a modification with correct line numbers", () => {
    const [f] = parseUnifiedDiff(MODIFY);
    expect(f.path).toBe("src/app.py");
    expect(f.status).toBe("modified");
    expect(f.additions).toBe(2);
    expect(f.deletions).toBe(1);
    expect(f.hunks).toHaveLength(1);
    const lines = f.hunks[0].lines;
    expect(lines[0]).toEqual({ type: "context", oldNo: 1, newNo: 1, text: "VALUE = 1" });
    expect(lines[1]).toEqual({ type: "del", oldNo: 2, newNo: null, text: "OLD = True" });
    expect(lines[2]).toEqual({ type: "add", oldNo: null, newNo: 2, text: "NEW = True" });
    expect(lines[3]).toEqual({ type: "add", oldNo: null, newNo: 3, text: "ADDED = 2" });
    expect(lines[4]).toEqual({ type: "context", oldNo: 3, newNo: 4, text: "END = None" });
  });

  it("parses an added file", () => {
    const [f] = parseUnifiedDiff(ADD);
    expect(f.path).toBe("src/helper.py");
    expect(f.status).toBe("added");
    expect(f.additions).toBe(2);
    expect(f.deletions).toBe(0);
    expect(f.hunks[0].lines.every((l) => l.type === "add")).toBe(true);
  });

  it("parses a deleted file and keeps its old path", () => {
    const [f] = parseUnifiedDiff(DELETE);
    expect(f.path).toBe("gone.txt");
    expect(f.status).toBe("deleted");
    expect(f.deletions).toBe(1);
  });

  it("parses a rename with both paths", () => {
    const [f] = parseUnifiedDiff(RENAME);
    expect(f.status).toBe("renamed");
    expect(f.oldPath).toBe("old_name.py");
    expect(f.path).toBe("new_name.py");
    expect(f.additions).toBe(1);
    expect(f.deletions).toBe(1);
  });

  it("flags binary files without hunks", () => {
    const [f] = parseUnifiedDiff(BINARY);
    expect(f.binary).toBe(true);
    expect(f.hunks).toHaveLength(0);
  });

  it("parses multiple files from one patch", () => {
    const files = parseUnifiedDiff(MODIFY + ADD);
    expect(files).toHaveLength(2);
    expect(files.map((f) => f.path)).toEqual(["src/app.py", "src/helper.py"]);
  });

  it("returns [] for empty or non-diff input", () => {
    expect(parseUnifiedDiff("")).toEqual([]);
    expect(parseUnifiedDiff("hello world")).toEqual([]);
  });
});
