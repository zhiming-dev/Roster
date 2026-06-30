import { motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { sendMessage } from "../../store/actions";
import { useStore } from "../../store/store";
import styles from "./chat.module.css";

export function Composer() {
  const awaiting = useStore((s) => s.awaiting);
  const awaitingInput = useStore((s) => s.awaitingInput);
  const draft = useStore((s) => s.draft);
  const setDraft = useStore((s) => s.setDraft);
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  // A suggestion chip stages text in the store; pull it into the input.
  useEffect(() => {
    if (draft) {
      setValue(draft);
      setDraft("");
      ref.current?.focus();
    }
  }, [draft, setDraft]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }, [value]);

  const submit = () => {
    const t = value.trim();
    if (!t || awaiting) return;
    setValue("");
    void sendMessage(t);
  };

  return (
    <div className={styles.composer}>
      <div className={styles.rail}>
        <div className={`${styles.box} ${awaitingInput ? styles.boxAwait : ""}`}>
          <textarea
            ref={ref}
            className={styles.input}
            rows={1}
            placeholder={awaitingInput ? "Answer the planner…" : "Message the Planner…"}
            value={value}
            disabled={awaiting}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
          />
          <motion.button
            className={styles.send}
            disabled={awaiting || !value.trim()}
            onClick={submit}
            aria-label="Send"
            whileHover={{ scale: 1.06 }}
            whileTap={{ scale: 0.9 }}
          >
            ↑
          </motion.button>
        </div>
        <div className={styles.hint}>You talk to the Planner — it dispatches the specialists.</div>
      </div>
    </div>
  );
}
