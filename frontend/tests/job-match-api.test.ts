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

describe("api.createJobFromText", () => {
  it("posts the JD text as JSON with the session header", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        job_id: "job-1",
        job: { title: "Backend Engineer", requirements: [], responsibilities: [], raw_text: "..." },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await api.createJobFromText("Requirements\n- Python", "session-1");

    expect(result.job_id).toBe("job-1");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/v1/jobs");
    expect(JSON.parse(init.body as string)).toEqual({ text: "Requirements\n- Python" });
    expect((init.headers as Record<string, string>)["X-Session-Id"]).toBe("session-1");
  });

  it("surfaces a validation failure as a typed ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            error: {
              code: "VALIDATION_FAILED",
              category: "validation",
              message: "The job description text is empty.",
              retryable: false,
              request_id: "req-1",
            },
          },
          { status: 422 },
        ),
      ),
    );

    const error = (await api
      .createJobFromText("", "session-1")
      .catch((e: unknown) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe("VALIDATION_FAILED");
  });
});

describe("api.matchResumeToJob", () => {
  it("posts document_id and job_id as JSON with the session header", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        overall: 82,
        components: {},
        degraded: [],
        methodology: {},
        skill_gaps: { entries: [], semantic_available: false },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await api.matchResumeToJob("doc-1", "job-1", "session-1");

    expect(result.overall).toBe(82);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/v1/match");
    expect(JSON.parse(init.body as string)).toEqual({ document_id: "doc-1", job_id: "job-1" });
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
              request_id: "req-2",
            },
          },
          { status: 404 },
        ),
      ),
    );

    const error = (await api
      .matchResumeToJob("missing", "job-1", "session-1")
      .catch((e: unknown) => e)) as ApiError;
    expect(error.code).toBe("NOT_FOUND");
  });
});
