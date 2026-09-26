"use client";

import { useEffect, useRef, useState } from "react";
import { API } from "./api";

/**
 * Subscribe to the API's change stream.
 *
 * The dashboard uses this to follow decisions; here it is only ever "something happened
 * on one of my threads" — a support agent replying, or an approval being resolved — and
 * the chat refetches its own conversation. No decision detail crosses over.
 *
 * `onTrace` is read through a ref so a caller can pass an inline closure without tearing
 * the subscription down and reopening it on every render.
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
