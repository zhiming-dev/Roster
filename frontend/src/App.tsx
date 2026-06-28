import { MotionConfig } from "motion/react";
import { useEffect, useState } from "react";
import { useWebSocket } from "./api/useWebSocket";
import { ActivityPanel } from "./components/activity/ActivityPanel";
import { ChatView } from "./components/chat/ChatView";
import { Composer } from "./components/chat/Composer";
import { LineageGraph } from "./components/lineage/LineageGraph";
import { SetupView } from "./components/setup/SetupView";
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
  const [view, setView] = useState<"chat" | "setup">("chat");

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
          <button
            className={`activity-toggle ${view === "setup" ? "on" : ""}`}
            onClick={() => setView((v) => (v === "setup" ? "chat" : "setup"))}
          >
            ⚙ Setup
          </button>
          <span className="spacer" />
          {view === "chat" && (
            <button
              className={`activity-toggle ${activityOpen ? "on" : ""}`}
              onClick={toggleActivity}
            >
              Activity
              {unread > 0 && !activityOpen && <span className="badge">{unread}</span>}
            </button>
          )}
        </div>

        {view === "setup" ? (
          <SetupView onClose={() => setView("chat")} />
        ) : (
          <>
            <LineageGraph />
            <ChatView />
            <Composer />
          </>
        )}
      </main>

      <ActivityPanel onClose={() => setActivityOpen(false)} />
      </div>
    </MotionConfig>
  );
}
