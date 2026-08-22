import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiRequest, beaconReleaseSession } from "@/lib/api-client";

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("apiRequest", () => {
  it("sends the session id as a header and never as a cookie", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await apiRequest("/v1/session", { sessionId: "abc123" });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Record<string, string>)["X-Session-Id"]).toBe("abc123");
    expect(init.credentials).toBe("omit");
  });

  it("omits the session header when there is no session", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await apiRequest("/health");

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Record<string, string>)["X-Session-Id"]).toBeUndefined();
  });

  it("maps the error envelope to a typed ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            error: {
              code: "SESSION_EXPIRED",
              category: "session",
              message: "Your temporary session has ended.",
              retryable: false,
              request_id: "req-42",
            },
          },
          { status: 410 },
        ),
      ),
    );

    await expect(apiRequest("/v1/session")).rejects.toMatchObject({
      code: "SESSION_EXPIRED",
      category: "session",
      requestId: "req-42",
      status: 410,
    });
  });

  it("flags session-gone errors so the UI can stop cleanly", async () => {
    const error = new ApiError({
      code: "SESSION_EXPIRED",
      category: "session",
      message: "gone",
      retryable: false,
      requestId: null,
      status: 410,
    });
    expect(error.isSessionGone).toBe(true);
  });

  it("degrades gracefully when the response body is not JSON", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("<html>502</html>", { status: 502 })),
    );

    const error = (await apiRequest("/health").catch((e: unknown) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe("UNEXPECTED_ERROR");
    expect(error.message).not.toContain("<html>");
  });

  it("reports a network failure as retryable rather than crashing", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    const error = (await apiRequest("/health").catch((e: unknown) => e)) as ApiError;
    expect(error.category).toBe("network");
    expect(error.retryable).toBe(true);
  });

  it("returns undefined for 204 responses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    await expect(apiRequest("/v1/session")).resolves.toBeUndefined();
  });

  it("propagates aborts instead of masking them as network errors", async () => {
    const abortError = new DOMException("aborted", "AbortError");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(abortError));
    await expect(apiRequest("/health")).rejects.toBe(abortError);
  });
});

describe("beaconReleaseSession", () => {
  it("sends a CORS-safelisted text/plain body so no preflight is needed on unload", () => {
    const sendBeacon = vi.fn().mockReturnValue(true);
    vi.stubGlobal("navigator", { sendBeacon });

    expect(beaconReleaseSession("abc123")).toBe(true);

    const [url, blob] = sendBeacon.mock.calls[0] as [string, Blob];
    expect(url).toContain("/v1/session/release");
    // Blob normalises the type to lower case; MIME types are case-insensitive.
    expect(blob.type.toLowerCase()).toBe("text/plain;charset=utf-8");
  });

  it("reports failure when the browser has no sendBeacon", () => {
    vi.stubGlobal("navigator", {});
    expect(beaconReleaseSession("abc123")).toBe(false);
  });
});
