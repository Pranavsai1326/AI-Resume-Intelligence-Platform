import { beforeEach, describe, expect, it } from "vitest";

import type { SessionInfo } from "@/lib/api-client";
import { sessionIdStorage, useSessionStore } from "@/stores/session-store";

const INFO: SessionInfo = {
  session_id: "session-abc",
  mode: "candidate",
  created_at: "2026-08-22T10:00:00Z",
  last_activity_at: "2026-08-22T10:00:00Z",
  expires_at: "2026-08-22T11:00:00Z",
  hard_expires_at: "2026-08-22T18:00:00Z",
  idle_ttl_seconds: 3600,
  absolute_ttl_seconds: 28800,
  counters: { documents: 0, analyses: 0, ai_calls: 0, ai_tokens: 0 },
};

beforeEach(() => {
  window.sessionStorage.clear();
  useSessionStore.getState().reset();
});

describe("session store", () => {
  it("starts empty", () => {
    const state = useSessionStore.getState();
    expect(state.sessionId).toBeNull();
    expect(state.status).toBe("idle");
  });

  it("activates a session and tracks the countdown", () => {
    useSessionStore.getState().setActive(INFO);
    const state = useSessionStore.getState();
    expect(state.sessionId).toBe("session-abc");
    expect(state.status).toBe("active");
    expect(state.secondsRemaining).toBe(3600);
  });

  it("expires locally when the countdown runs out", () => {
    useSessionStore.setState({ status: "active", info: INFO, sessionId: "x", secondsRemaining: 1 });
    useSessionStore.getState().tick();
    expect(useSessionStore.getState().status).toBe("expired");
    expect(useSessionStore.getState().sessionId).toBeNull();
  });

  it("does not count down when no session is active", () => {
    useSessionStore.setState({ status: "idle", secondsRemaining: 10 });
    useSessionStore.getState().tick();
    expect(useSessionStore.getState().secondsRemaining).toBe(10);
  });

  it("clears everything on reset", () => {
    useSessionStore.getState().setActive(INFO);
    useSessionStore.getState().reset();
    const state = useSessionStore.getState();
    expect(state.sessionId).toBeNull();
    expect(state.info).toBeNull();
    expect(state.status).toBe("idle");
  });
});

describe("session id storage", () => {
  it("keeps only the id and mode in sessionStorage - never content", () => {
    useSessionStore.getState().setActive(INFO);

    const keys = Object.keys(window.sessionStorage);
    expect(keys.sort()).toEqual(["ri.session_id", "ri.session_mode"]);
    expect(sessionIdStorage.read()).toEqual({ id: "session-abc", mode: "candidate" });
  });

  it("never writes to localStorage", () => {
    useSessionStore.getState().setActive(INFO);
    // The lint rule that bans persistent storage has to be lifted for the one test whose whole
    // purpose is to prove the ban holds.
    // eslint-disable-next-line no-restricted-properties
    expect(window.localStorage.length).toBe(0);
  });

  it("clears the stored id when the session expires", () => {
    useSessionStore.getState().setActive(INFO);
    useSessionStore.getState().setExpired();
    expect(sessionIdStorage.read().id).toBeNull();
    expect(window.sessionStorage.length).toBe(0);
  });

  it("ignores an unrecognised stored mode", () => {
    window.sessionStorage.setItem("ri.session_id", "abc");
    window.sessionStorage.setItem("ri.session_mode", "administrator");
    expect(sessionIdStorage.read().mode).toBeNull();
  });
});
