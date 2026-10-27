import { useCallback, useEffect, useRef, useState } from "react";

import { errorMessage } from "../lib/format";

export interface Resource<T> {
  data: T | undefined;
  error: string | null;
  refresh: () => Promise<void>;
}

/**
 * Loads data on mount and whenever `key` changes, optionally refreshing on an interval.
 * Pass `undefined` as the interval to stop polling.
 */
export function useResource<T>(
  load: () => Promise<T>,
  key: string,
  intervalMs?: number,
): Resource<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<string | null>(null);
  const loadRef = useRef(load);
  const requestId = useRef(0);
  loadRef.current = load;

  const refresh = useCallback(async () => {
    const currentRequest = ++requestId.current;
    try {
      const result = await loadRef.current();
      if (currentRequest === requestId.current) {
        setData(result);
        setError(null);
      }
    } catch (caught) {
      if (currentRequest === requestId.current) {
        setError(errorMessage(caught));
      }
    }
  }, []);

  useEffect(() => {
    requestId.current += 1;
    setData(undefined);
    void refresh();
    return () => {
      requestId.current += 1;
    };
  }, [key, refresh]);

  useEffect(() => {
    if (!intervalMs) {
      return undefined;
    }
    const timer = window.setInterval(() => void refresh(), intervalMs);
    return () => window.clearInterval(timer);
  }, [intervalMs, key, refresh]);

  return { data, error, refresh };
}

/** Wraps an async action with pending and error state for buttons and forms. */
export function useAction() {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async (action: () => Promise<unknown>): Promise<boolean> => {
    setPending(true);
    setError(null);
    try {
      await action();
      return true;
    } catch (caught) {
      setError(errorMessage(caught));
      return false;
    } finally {
      setPending(false);
    }
  }, []);

  return { pending, error, run, clearError: () => setError(null) };
}
