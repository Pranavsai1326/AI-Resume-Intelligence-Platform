/**
 * Client session state.
 *
 * In-memory only. There is deliberately no persistence middleware: resume, job-description and
 * candidate data must never reach `localStorage` or IndexedDB (PRIVACY_ARCHITECTURE.md section 4).
 *
 * The one thing that does survive a reload is the session *id*, kept in `sessionStorage`. That
 * is technical metadata, not content - and it is what lets a page refresh rejoin the session the
 * user already started instead of silently orphaning it on the server until it expires.
 */

import { create } from "zustand";

import type { SessionInfo, SessionMode } from "@/lib/api-client";

const SESSION_ID_KEY = "ri.session_id";
const SESSION_MODE_KEY = "ri.session_mode";

export type SessionStatus = "idle" | "starting" | "active" | "expired" | "error";

interface SessionState {
  sessionId: string | null;
  info: SessionInfo | null;
  status: SessionStatus;
  error: string | null;
  /** Seconds until the idle deadline, recomputed locally between server responses. */
  secondsRemaining: number;

  setStarting: () => void;
  setActive: (info: SessionInfo) => void;
  setExpired: () => void;
  setError: (message: string) => void;
  tick: () => void;
  reset: () => void;
}

/** Session id persistence, guarded so it is safe during server rendering. */
export const sessionIdStorage = {
  read(): { id: string | null; mode: SessionMode | null } {
    if (typeof window === "undefined") return { id: null, mode: null };
    try {
      const mode = window.sessionStorage.getItem(SESSION_MODE_KEY);
      return {
        id: window.sessionStorage.getItem(SESSION_ID_KEY),
        mode: mode === "candidate" || mode === "recruiter" ? mode : null,
      };
    } catch {
      // Storage can be unavailable (private mode, blocked cookies). Not fatal: the session
      // simply does not survive a reload.
      return { id: null, mode: null };
    }
  },
  write(id: string, mode: SessionMode): void {
    if (typeof window === "undefined") return;
    try {
      window.sessionStorage.setItem(SESSION_ID_KEY, id);
      window.sessionStorage.setItem(SESSION_MODE_KEY, mode);
    } catch {
      /* non-fatal */
    }
  },
  clear(): void {
    if (typeof window === "undefined") return;
    try {
      window.sessionStorage.removeItem(SESSION_ID_KEY);
      window.sessionStorage.removeItem(SESSION_MODE_KEY);
    } catch {
      /* non-fatal */
    }
  },
};

export const useSessionStore = create<SessionState>((set, get) => ({
  sessionId: null,
  info: null,
  status: "idle",
  error: null,
  secondsRemaining: 0,

  setStarting: () => set({ status: "starting", error: null }),

  setActive: (info) => {
    sessionIdStorage.write(info.session_id, info.mode);
    set({
      sessionId: info.session_id,
      info,
      status: "active",
      error: null,
      secondsRemaining: info.idle_ttl_seconds,
    });
  },

  setExpired: () => {
    sessionIdStorage.clear();
    set({
      sessionId: null,
      info: null,
      status: "expired",
      error: null,
      secondsRemaining: 0,
    });
  },

  setError: (message) => set({ status: "error", error: message }),

  tick: () => {
    const { status, secondsRemaining } = get();
    if (status !== "active") return;
    const next = Math.max(0, secondsRemaining - 1);
    if (next === 0) {
      get().setExpired();
      return;
    }
    set({ secondsRemaining: next });
  },

  reset: () => {
    sessionIdStorage.clear();
    set({
      sessionId: null,
      info: null,
      status: "idle",
      error: null,
      secondsRemaining: 0,
    });
  },
}));
