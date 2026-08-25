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

describe("api.listResumeVersions", () => {
  it("requests versions for the given document with the session header", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse([
        {
          version_id: "v1",
          label: "Original",
          source: "original",
          created_at: "2026-01-01T00:00:00Z",
          based_on_version_id: null,
        },
      ]),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await api.listResumeVersions("doc-1", "session-1");

    expect(result).toHaveLength(1);
    expect(result[0]?.label).toBe("Original");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/v1/resume/versions?document_id=doc-1");
    expect((init.headers as Record<string, string>)["X-Session-Id"]).toBe("session-1");
  });
});

describe("api.rewriteText", () => {
  it("posts the honest unavailable response through untouched", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          before: "Built the service.",
          after: null,
          fact_guard_findings: [],
          available: false,
          unavailable_reason: "AI writing is not configured on this deployment.",
        }),
      ),
    );

    const result = await api.rewriteText("doc-1", "bullet", "Built the service.", "session-1");

    expect(result.available).toBe(false);
    expect(result.unavailable_reason).toBe("AI writing is not configured on this deployment.");
  });

  it("surfaces a not-found target as a typed ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            error: {
              code: "NOT_FOUND",
              category: "validation",
              message: "No document with that id exists in this session.",
              retryable: false,
              request_id: "req-1",
            },
          },
          { status: 404 },
        ),
      ),
    );

    const error = (await api
      .rewriteText("missing", "bullet", "x", "session-1")
      .catch((e: unknown) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe("NOT_FOUND");
  });
});

describe("api.applyTailorProposals", () => {
  it("posts only the given proposals and returns the created version", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        version_id: "v2",
        document_id: "doc-1",
        label: "Tailored",
        source: "ai_tailored",
        created_at: "2026-01-01T00:00:00Z",
        based_on_version_id: "v1",
        resume: {
          contact: { full_name: null, email: null, phone: null, location: null, links: [] },
          summary: null,
          experience: [],
          education: [],
          skills: [],
          projects: [],
          certifications: [],
          custom_sections: [],
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const version = await api.applyTailorProposals(
      { documentId: "doc-1", versionId: "v1", label: "Tailored", proposals: [] },
      "session-1",
    );

    expect(version.source).toBe("ai_tailored");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/v1/tailor/apply");
    expect(JSON.parse(init.body as string)).toEqual({
      document_id: "doc-1",
      version_id: "v1",
      label: "Tailored",
      proposals: [],
    });
  });
});

describe("api.exportResume", () => {
  it("reads the filename from Content-Disposition and returns a blob", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(new Blob(["docx-bytes"]), {
        status: 200,
        headers: {
          "Content-Type":
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          "Content-Disposition": 'attachment; filename="original.docx"',
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await api.exportResume("doc-1", "docx", "session-1", "v1");

    expect(result.filename).toBe("original.docx");
    expect(result.blob.size).toBeGreaterThan(0);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/v1/export");
    expect(JSON.parse(init.body as string)).toEqual({
      document_id: "doc-1",
      version_id: "v1",
      format: "docx",
    });
  });

  it("falls back to a generic filename when the header is missing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(new Blob(["pdf-bytes"]), { status: 200 })),
    );

    const result = await api.exportResume("doc-1", "pdf", "session-1");
    expect(result.filename).toBe("resume.pdf");
  });
});
