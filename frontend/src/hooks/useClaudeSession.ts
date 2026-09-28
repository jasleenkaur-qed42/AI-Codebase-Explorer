import { useEffect, useState } from 'react';
import type { SessionEvent } from '../types';

export function useClaudeSession() {
  const [latestEvent, setLatestEvent] = useState<SessionEvent | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const source = new EventSource('/api/session/stream');
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.onmessage = (message) => {
      setLatestEvent(JSON.parse(message.data) as SessionEvent);
    };
    return () => source.close();
  }, []);

  return { latestEvent, connected };
}
