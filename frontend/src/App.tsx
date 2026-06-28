import { MotionConfig } from "motion/react";
import { useEffect, useState } from "react";
import { useWebSocket } from "./api/useWebSocket";
import { ActivityPanel } from "./components/activity/ActivityPanel";
import { ChatView } from "./components/chat/ChatView";
import { Composer } from "./components/chat/Composer";
import { LineageGraph } from "./components/lineage/LineageGraph";
import { Sidebar } from "./components/Sidebar";
import { loadInitial } from "./store/actions";
import { handleEvent } from "./store/handleEvent";
import { useStore } from "./store/store";
import "./styles/app.css";

const BANNER: Record<string, string> = {
  connecting: "Connecting to the runtime…",
  reconnecting: "Reconnecting to the runtime…",
  closed: "Disconnected from the runtime.",
};

export function App() {
  const connection = useStore((s) => s.connection);
  const setConnection = useStore((s) => s.setConnection);
  const theme = useStore((s) => s.theme);
  const unread = useStore((s) => s.unread);
  const clearUnread = useStore((s) => s.clearUnread);
  const [activityOpen, setActivityOpen] = useState(false);

  useWebSocket({ onEvent: (e) => handleEvent(e, true), onConnection: setConnection });

  useEffect(() => {
    const resolved =
      theme === "system"
        ? matchMedia("(prefers-color-scheme: dark)").matches
          ? "dark"
          : "light"
        : theme;
    document.documentElement.setAttribute("data-theme", resolved);
  }, [theme]);

  useEffect(() => {
    void loadInitial();
  }, []);

  const toggleActivity = () =>
    setActivityOpen((open) => {
      if (!open) clearUnread();
      return !open;
    });

  return (
    <MotionConfig reducedMotion="user" transition={{ type: "spring", stiffness: 400, damping: 30 }}>
      <div className={`app-shell ${activityOpen ? "activity-open" : ""}`}>
        <Sidebar />

      <main className="workspace">
        {connection !== "open" && (
          <div className="banner" data-c={connection}>
            {BANNER[connection]}
          </div>
        )}

        <div className="workspace-top">
          <span className="spacer" />
          <button
            className={`activity-toggle ${activityOpen ? "on" : ""}`}
            onClick={toggleActivity}
          >
            Activity
            {unread > 0 && !activityOpen && <span className="badge">{unread}</span>}
          </button>
        </div>

        <LineageGraph />
        <ChatView />
        <Composer />
      </main>

      <ActivityPanel onClose={() => setActivityOpen(false)} />
      </div>
    </MotionConfig>
  );
}
