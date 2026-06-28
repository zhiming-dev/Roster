# Parity Checklist — React SPA vs legacy `dashboard.html`

Derived from `runtime/static/dashboard.html`. US1 (T012–T021) is "done" only when every
row is ✅ against a running runtime. Status below reflects the implementation; the
runtime-verified column is filled when checked end-to-end against `python -m roster`.

| # | Feature (legacy dashboard) | React implementation | Impl |
|---|---|---|---|
| 1 | Sidebar brand + "New chat" (→ POST /api/reset) | `components/Sidebar.tsx` + `store/actions.newChat` | ✅ |
| 2 | Conversation history list (title, msg count, relative time) | `Sidebar` `ConversationItem` + `timeAgo` | ✅ |
| 3 | Open a conversation (activate + replay events) | `actions.openConversation` → `replay()` | ✅ |
| 4 | Delete a conversation (confirm) | `Sidebar` delete + `actions.deleteConversation` | ✅ |
| 5 | Active conversation highlight | `convActive` class on `activeConvId` | ✅ |
| 6 | Run id + queue chip in footer | `Sidebar` footer (queue derived from agent statuses) | ✅ |
| 7 | Light / dark / system theme + toggle | `store.theme` + `App` `data-theme` effect + `Sidebar` toggle | ✅ |
| 8 | Agent lineage graph (you → planner → specialists) | `lineage/LineageGraph.tsx` (ported layout) | ✅ |
| 9 | Per-agent live status (idle/queued/thinking/searching/error) | `lineage/AgentNode.tsx` `data-st` | ✅ |
| 10 | Active-edge flow animation on traffic | `flashEdge` + `.edge.active` flow keyframes | ✅ |
| 11 | Chat: user / agent bubbles | `chat/ChatView.tsx` `MessageBubble` | ✅ |
| 12 | Typing indicator while the planner works | `store.typing` + `Typing` | ✅ |
| 13 | Error bubble on chat failure | `actions.sendMessage` catch → error message | ✅ |
| 14 | Empty state with suggestion chips (fill composer) | `Empty` → `store.draft` → `Composer` | ✅ |
| 15 | Composer: autosize, Enter to send, Shift+Enter newline, disabled while awaiting | `chat/Composer.tsx` | ✅ |
| 16 | Optimistic user bubble + echo dedupe | `sendMessage` + `handleEvent` pendingUser | ✅ |
| 17 | Activity panel (collapsible) with unread badge | `activity/ActivityPanel.tsx` + `App` toggle + `store.unread` | ✅ |
| 18 | Activity events: message subkinds, search query/results/error, runtime errors | `handleEvent` → `ActivityItem` + `ActivityEvent` | ✅ |
| 19 | Search results rendered with clickable URLs | `ActivityEvent` results list with `<a>` | ✅ |
| 20 | Live updates via /ws | `api/useWebSocket` → `handleEvent(_, true)` | ✅ |
| 21 | Event replay when opening a conversation | `actions.replay` → `handleEvent(_, false)` | ✅ |
| 22 | Run banner / run id display | `Sidebar` run id (+ `run.started` handling) | ✅ |
| 23 | **Disconnected/reconnecting visible** (improves on legacy silent retry) | `App` connection banner (SC-006) | ✅ |

Unit-tested: the event reducer (`store/handleEvent.test.ts`) covers rows 11–12, 16, 17–18, 9.

End-to-end (Playwright `tests/smoke.spec.ts`) and the runtime-verified column require running
`npm run dev` + `python -m roster`; pending a live runtime in this environment.
