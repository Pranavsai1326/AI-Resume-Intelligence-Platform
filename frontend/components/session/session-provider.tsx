"use client";

/**
 * Session lifecycle on the client.
 *
 * Responsibilities: start or rejoin a session, keep it alive while the tab is in use, count down
 * to expiry, and signal the server when the page goes away.
 *
 * That signal is explicitly not the deletion mechanism. `pagehide` does not fire on a crash, a
 * forced kill, a shutdown or a network drop, so the server expires the session on its own
 * schedule regardless (PRIVACY_ARCHITECTURE.md section 3).
 */

import * as React from "react";

import {
  ApiError,
  api,
  beaconReleaseSession,
  type SessionInfo,
  type SessionMode,
} from "@/lib/api-client";
import { sessionIdStorage, useSessionStore } from "@/stores/session-store";

/** Well inside the 60-minute idle TTL, so a brief network failure is not fatal. */
const HEARTBEAT_INTERVAL_MS = 5 * 60 * 1000;

interface SessionContextValue {
  start: (mode: SessionMode) => Promise<SessionInfo | null>;
  end: () => Promise<void>;
  restart: () => Promise<SessionInfo | null>;
}

const SessionContext = React.createContext<SessionContextValue | null>(null);

export function useSessionActions(): SessionContextValue {
  const context = React.useContext(SessionContext);
  if (!context) {
    throw new Error("useSessionActions must be used within <SessionProvider>");
  }
  return context;
}

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const store = useSessionStore;
  const setStarting = useSessionStore((s) => s.setStarting);
  const setActive = useSessionStore((s) => s.setActive);
  const setExpired = useSessionStore((s) => s.setExpired);
  const setError = useSessionStore((s) => s.setError);
  const reset = useSessionStore((s) => s.reset);
  const tick = useSessionStore((s) => s.tick);

  const handleFailure = React.useCallback(
    (error: unknown) => {
      if (error instanceof ApiError) {
        if (error.isSessionGone) {
          setExpired();
          return;
        }
        setError(error.message);
        return;
      }
      setError("Something went wrong. Please try again.");
    },
    [setError, setExpired],
  );

  const start = React.useCallback(
    async (mode: SessionMode) => {
      setStarting();
      try {
        const info = await api.createSession(mode);
        setActive(info);
        return info;
      } catch (error) {
        handleFailure(error);
        return null;
      }
    },
    [handleFailure, setActive, setStarting],
  );

  const end = React.useCallback(async () => {
    const { sessionId } = store.getState();
    reset();
    if (!sessionId) return;
    try {
      await api.endSession(sessionId);
    } catch {
      // The session still expires server-side; a failed teardown call changes nothing.
    }
  }, [reset, store]);

  const restart = React.useCallback(async () => {
    const mode = store.getState().info?.mode ?? sessionIdStorage.read().mode ?? "candidate";
    return start(mode);
  }, [start, store]);

  // Rejoin an existing session after a reload, rather than orphaning it on the server.
  React.useEffect(() => {
    const { id } = sessionIdStorage.read();
    if (!id || store.getState().status !== "idle") return;

    const controller = new AbortController();
    setStarting();
    api
      .getSession(id, controller.signal)
      .then(setActive)
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        if (error instanceof ApiError && error.isSessionGone) {
          // Nothing to recover: clear the stale id and present a clean start.
          reset();
          return;
        }
        handleFailure(error);
      });
    return () => controller.abort();
  }, [handleFailure, reset, setActive, setStarting, store]);

  // Heartbeat while the tab is in use.
  React.useEffect(() => {
    const beat = () => {
      const { sessionId, status } = store.getState();
      if (!sessionId || status !== "active" || document.visibilityState !== "visible") return;
      api.heartbeat(sessionId).then(setActive).catch(handleFailure);
    };

    const interval = window.setInterval(beat, HEARTBEAT_INTERVAL_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible") beat();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [handleFailure, setActive, store]);

  // Local countdown so the remaining time stays truthful between server responses.
  React.useEffect(() => {
    const interval = window.setInterval(tick, 1000);
    return () => window.clearInterval(interval);
  }, [tick]);

  // Release on page teardown. `pagehide` cannot distinguish a closed tab from a reload, which
  // is exactly why this releases rather than destroys - see `beaconReleaseSession`.
  React.useEffect(() => {
    const onPageHide = (event: PageTransitionEvent) => {
      // A persisted page may be restored from the back/forward cache: leave it untouched.
      if (event.persisted) return;
      const { sessionId } = store.getState();
      if (sessionId) beaconReleaseSession(sessionId);
    };
    window.addEventListener("pagehide", onPageHide);
    return () => window.removeEventListener("pagehide", onPageHide);
  }, [store]);

  const value = React.useMemo<SessionContextValue>(
    () => ({ start, end, restart }),
    [end, restart, start],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}
