import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api } from "@/lib/api-client";

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

describe("api.uploadDocument", () => {
  it("sends a multipart FormData body without a manual Content-Type header", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        document_id: "abc123",
        kind: "txt",
        layout: { page_count: null, multi_column: false, has_tables: false, has_images: false, has_text_boxes: false, has_repeating_header_footer: false },
        ocr_used: false,
        text_length: 10,
        resume_summary: null,
        cached: false,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const file = new File(["hello"], "resume.txt", { type: "text/plain" });
    const result = await api.uploadDocument(file, "resume", "session-1");

    expect(result.document_id).toBe("abc123");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/v1/documents");
    expect(init.body).toBeInstanceOf(FormData);
    // The browser sets Content-Type (with the multipart boundary) itself; the client must not.
    expect((init.headers as Record<string, string>)["Content-Type"]).toBeUndefined();
    expect((init.headers as Record<string, string>)["X-Session-Id"]).toBe("session-1");
    expect(init.credentials).toBe("omit");

    const form = init.body as FormData;
    expect(form.get("file")).toBeInstanceOf(File);
    expect(form.get("kind")).toBe("resume");
  });

  it("raises a typed ApiError on a validation failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            error: {
              code: "UNSUPPORTED_FILE_TYPE",
              category: "validation",
              message: "Only PDF, DOCX and TXT files are supported.",
              retryable: false,
              request_id: "req-1",
            },
          },
          { status: 422 },
        ),
      ),
    );

    const file = new File(["hello"], "resume.exe", { type: "application/octet-stream" });
    await expect(api.uploadDocument(file, "resume", "session-1")).rejects.toMatchObject({
      code: "UNSUPPORTED_FILE_TYPE",
    });
  });

  it("propagates aborts instead of masking them as network errors", async () => {
    const abortError = new DOMException("aborted", "AbortError");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(abortError));
    const file = new File(["hello"], "resume.txt", { type: "text/plain" });
    await expect(api.uploadDocument(file, "resume", "session-1")).rejects.toBe(abortError);
  });
});

describe("api.analyzeResume", () => {
  it("posts the document id as JSON with the session header", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ overall: 88, components: {}, degraded: [], methodology: {} }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await api.analyzeResume("doc-1", "session-1");

    expect(result.overall).toBe(88);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({ document_id: "doc-1" });
    expect((init.headers as Record<string, string>)["X-Session-Id"]).toBe("session-1");
  });

  it("surfaces a not-found analysis target as a typed ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            error: {
              code: "NOT_FOUND",
              category: "validation",
              message: "The requested item does not exist in this session.",
              retryable: false,
              request_id: "req-2",
            },
          },
          { status: 404 },
        ),
      ),
    );

    const error = (await api
      .analyzeResume("missing", "session-1")
      .catch((e: unknown) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe("NOT_FOUND");
  });
});
