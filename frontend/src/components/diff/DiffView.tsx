// VS Code-style unified diff renderer (spec 004, T024): per-file cards with a status
// badge, +adds/−dels counts, line-number gutters, and +/−/context coloring. Collapsible;
// oversized or binary content degrades to a one-line summary (with a raw-patch fallback).

import { useMemo, useState } from "react";
import type { FileDiffSummary } from "../../types/models";
import styles from "./diff.module.css";
import type { DiffFile } from "./lib/parseUnifiedDiff";
import { parseUnifiedDiff } from "./lib/parseUnifiedDiff";

// Beyond these bounds a file renders collapsed with a raw-patch fallback instead of a
// line grid — keeps a generated-lockfile-sized diff from freezing the timeline.
const MAX_RENDER_LINES = 600;

const STATUS_LABEL: Record<string, string> = {
  added: "A",
  modified: "M",
  deleted: "D",
  renamed: "R",
};

function FileCard({ file, defaultOpen }: { file: DiffFile; defaultOpen: boolean }) {
  const lineCount = file.hunks.reduce((n, h) => n + h.lines.length, 0);
  const oversized = lineCount > MAX_RENDER_LINES;
  const [open, setOpen] = useState(defaultOpen && !oversized);
  const [showRaw, setShowRaw] = useState(false);

  const title =
    file.status === "renamed" && file.oldPath !== file.path
      ? `${file.oldPath} → ${file.path}`
      : file.path;

  return (
    <div className={styles.file}>
      <button
        className={styles.fileHead}
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <span className={styles.chev}>{open ? "▾" : "▸"}</span>
        <span className={`${styles.badge} ${styles[file.status]}`}>
          {STATUS_LABEL[file.status] ?? "M"}
        </span>
        <span className={styles.path}>{title}</span>
        <span className={styles.counts}>
          {file.additions > 0 && <span className={styles.adds}>+{file.additions}</span>}
          {file.deletions > 0 && <span className={styles.dels}>−{file.deletions}</span>}
        </span>
      </button>
      {open &&
        (file.binary ? (
          <div className={styles.note}>Binary file — no textual diff.</div>
        ) : oversized && !showRaw ? (
          <div className={styles.note}>
            {lineCount.toLocaleString()} lines — too large to render as a grid.{" "}
            <button className={styles.rawToggle} onClick={() => setShowRaw(true)}>
              Show raw patch
            </button>
          </div>
        ) : oversized && showRaw ? (
          <pre className={styles.raw}>
            {file.hunks.map((h) => [h.header, ...h.lines.map((l) => l.text)].join("\n")).join("\n")}
          </pre>
        ) : (
          <div className={styles.lines} role="table" aria-label={`Diff of ${file.path}`}>
            {file.hunks.map((h, hi) => (
              <div key={hi}>
                <div className={styles.hunk}>{h.header}</div>
                {h.lines.map((l, li) => (
                  <div key={li} className={`${styles.lineRow} ${styles[l.type]}`}>
                    <span className={styles.gutter}>{l.oldNo ?? ""}</span>
                    <span className={styles.gutter}>{l.newNo ?? ""}</span>
                    <span className={styles.sign}>
                      {l.type === "add" ? "+" : l.type === "del" ? "−" : " "}
                    </span>
                    <span className={styles.code}>{l.text}</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        ))}
    </div>
  );
}

export function DiffView({
  patch,
  files,
  truncated,
  defaultOpen = true,
}: {
  patch: string;
  files?: FileDiffSummary[]; // backend per-file summary — the fallback when parsing fails
  truncated?: boolean;
  defaultOpen?: boolean;
}) {
  const parsed = useMemo(() => parseUnifiedDiff(patch), [patch]);

  if (parsed.length === 0) {
    // Unparseable or truncated-to-nothing patch: fall back to the backend's summary.
    const summary = (files ?? [])
      .map((f) => `${f.path} (+${f.additions} −${f.deletions})`)
      .join(", ");
    return <div className={styles.note}>{summary || "No textual change."}</div>;
  }
  return (
    <div className={styles.diff}>
      {parsed.map((f) => (
        <FileCard key={`${f.oldPath}→${f.path}`} file={f} defaultOpen={defaultOpen} />
      ))}
      {truncated && <div className={styles.note}>Patch truncated by the runtime size cap.</div>}
    </div>
  );
}
