import { useEffect, useRef, useState, useCallback } from 'react';

export interface WsEvent {
  type: string;
  workflow_id?: string;
  run_id?: string;
  timestamp?: string;
  data?: any;
}

export function useWebSocket(runId: string | null) {
  const [events, setEvents] = useState<WsEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!runId) return;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}/ws/events?run_id=${runId}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (e) => {
      try {
        const event: WsEvent = JSON.parse(e.data);
        setEvents(prev => [...prev, event]);
      } catch {}
    };

    // Keep alive ping
    const ping = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send('ping');
    }, 30000);

    return () => {
      clearInterval(ping);
      ws.close();
    };
  }, [runId]);

  const clearEvents = useCallback(() => setEvents([]), []);
  return { events, connected, clearEvents };
}
