import { motion } from "motion/react";
import { useStore } from "../store/store";
import styles from "./ThemeToggle.module.css";

export function ThemeToggle() {
  const theme = useStore((s) => s.theme);
  const setTheme = useStore((s) => s.setTheme);
  const dark =
    theme === "dark" ||
    (theme === "system" &&
      typeof matchMedia !== "undefined" &&
      matchMedia("(prefers-color-scheme: dark)").matches);

  return (
    <button
      className={styles.toggle}
      data-dark={dark}
      onClick={() => setTheme(dark ? "light" : "dark")}
      aria-label="Toggle light / dark"
      title="Toggle appearance"
    >
      <motion.span
        className={styles.knob}
        layout
        transition={{ type: "spring", stiffness: 620, damping: 26 }}
      >
        {dark ? "☾" : "☀"}
      </motion.span>
    </button>
  );
}
