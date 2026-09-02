import { useCallback, useEffect, useRef, useState } from "react";

export interface TimedNotice {
  id: number;
  message: string;
}

export function useTimedNotices(durationMs = 5000) {
  const [notices, setNotices] = useState<TimedNotice[]>([]);
  const nextId = useRef(1);
  const timers = useRef(new Map<number, number>());

  const dismissNotice = useCallback((id: number) => {
    const timer = timers.current.get(id);
    if (timer !== undefined) window.clearTimeout(timer);
    timers.current.delete(id);
    setNotices((current) => current.filter((notice) => notice.id !== id));
  }, []);

  const pushNotice = useCallback((message: string) => {
    const id = nextId.current++;
    setNotices((current) => [...current, { id, message }]);
    timers.current.set(id, window.setTimeout(() => {
      timers.current.delete(id);
      setNotices((current) => current.filter((notice) => notice.id !== id));
    }, durationMs));
  }, [durationMs]);

  useEffect(() => () => {
    timers.current.forEach((timer) => window.clearTimeout(timer));
    timers.current.clear();
  }, []);

  return { notices, pushNotice, dismissNotice };
}
