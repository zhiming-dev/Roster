import type { Transition } from "motion/react";

// Shared spring presets — the "Q弹" feel. Components override per-use as needed.
export const springy: Transition = { type: "spring", stiffness: 520, damping: 24 };
export const bouncy: Transition = { type: "spring", stiffness: 460, damping: 16 };
export const soft: Transition = { type: "spring", stiffness: 360, damping: 30 };
