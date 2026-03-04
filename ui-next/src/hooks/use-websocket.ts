"use client";

import { useEffect, useRef, useState, useCallback } from "react";

export function useWebSocket(url: string | null) {
  const [messages, setMessages] = useState<string[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  const clear = useCallback(() => setMessages([]), []);

  useEffect(() => {
    if (!url) return;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);
    ws.onmessage = (event) => {
      setMessages((prev) => [...prev.slice(-500), event.data]);
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [url]);

  return { messages, connected, clear };
}
