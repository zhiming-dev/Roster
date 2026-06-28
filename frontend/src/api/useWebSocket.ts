import { useEffect, useRef } from "react";
import { parseEvent, type RosterEvent } from "../types/events";
import type { ConnectionState } from "../types/models";

interface Options {
  onEvent: (evt: RosterEvent) => void;
  onConnection?: (state: ConnectionState) => void;
}

// Reconnecting WebSocket to the runtime's /ws live feed. Same-origin in prod
// (FastAPI), proxied by Vite in dev. Exponential backoff capped at 5s. Callbacks
// are held in refs so reconnection logic never re-subscribes on every render.
export function useWebSocket({ onEvent, onConnection }: Options): void {
  const onEventRef = useRef(onEvent);
  const onConnRef = useRef(onConnection);
  onEventRef.current = onEvent;
  onConnRef.current = onConnection;

  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    let backoff = 500;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const setConn = (s: ConnectionState) => onConnRef.current?.(s);

    const connect = () => {
      if (closed) return;
      const proto = location.protocol === "https:" ? "wss:" : "ws:";
      ws = new WebSocket(`${proto}//${location.host}/ws`);
      ws.onopen = () => {
        backoff = 500;
        setConn("open");
      };
      ws.onmessage = (msg) => {
        try {
          const evt = parseEvent(JSON.parse(msg.data));
          if (evt) onEventRef.current(evt);
        } catch {
          /* ignore malformed frame */
        }
      };
      ws.onclose = () => {
        if (closed) return;
        setConn("reconnecting");
        timer = setTimeout(connect, backoff);
        backoff = Math.min(backoff * 2, 5000);
      };
      ws.onerror = () => ws?.close();
    };

    setConn("connecting");
    connect();

    return () => {
      closed = true;
      if (timer) clearTimeout(timer);
      ws?.close();
    };
  }, []);
}
