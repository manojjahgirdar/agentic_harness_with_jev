"use client";

import { useEffect, useRef, useState } from "react";
import { API } from "./api";

/**
 * Subscribe to the API's decision stream.
 *
 * `onTrace` is handed the threads that just changed; the caller decides whether any of
 * them are on screen. The handler is read through a ref so a caller can pass an inline
 * closure without tearing the subscription down and reopening it on every render.
 */
export function useTraceStream(onTrace: (threads: string[]) => void) {
  const [connected, setConnected] = useState(false);
  const handlerRef = useRef(onTrace);

  useEffect(() => {
    handlerRef.current = onTrace;
  }, [onTrace]);

  useEffect(() => {
    const source = new EventSource(`${API}/api/events`);

    source.addEventListener("hello", () => setConnected(true));
    source.addEventListener("trace", (event) => {
      setConnected(true);
      const data = JSON.parse((event as MessageEvent).data) as { threads: string[] };
      handlerRef.current(data.threads ?? []);
    });
    source.onerror = () => setConnected(false);

    return () => source.close();
  }, []);

  return connected;
}
