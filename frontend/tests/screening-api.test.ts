import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api-client";

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

describe("api.createScreening", () => {
  it("posts the job id and returns the created context", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        screening_id: "s1",
        job_id: "j1",
        created_at: "2026-01-01T00:00:00Z",
        candidate_ids: [],
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await api.createScreening("j1", "session-1");

    expect(result.screening_id).toBe("s1");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/v1/screening");
    expect(JSON.parse(init.body as string)).toEqual({ job_id: "j1" });
  });
});

describe("api.uploadCandidates", () => {
  it("sends every file under the 'files' field and returns candidate ids", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ candidate_ids: ["c1", "c2"] }));
    vi.stubGlobal("fetch", fetchMock);

    const files = [
      new File(["a"], "a.txt", { type: "text/plain" }),
      new File(["b"], "b.txt", { type: "text/plain" }),
    ];
    const result = await api.uploadCandidates("s1", files, "session-1");

    expect(result.candidate_ids).toEqual(["c1", "c2"]);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/v1/screening/s1/candidates");
    const form = init.body as FormData;
    expect(form.getAll("files")).toHaveLength(2);
    expect((init.headers as Record<string, string>)["X-Session-Id"]).toBe("session-1");
  });
});

describe("api.getScreeningRanking", () => {
  it("builds query params only for provided fields", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ total: 0, candidates: [] }));
    vi.stubGlobal("fetch", fetchMock);

    await api.getScreeningRanking("s1", "session-1", { minScore: 50, limit: 5 });

    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url).toContain("min_score=50");
    expect(url).toContain("limit=5");
    expect(url).not.toContain("offset");
  });

  it("requests without a query string when no params are given", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ total: 0, candidates: [] }));
    vi.stubGlobal("fetch", fetchMock);

    await api.getScreeningRanking("s1", "session-1");

    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url.endsWith("/v1/screening/s1/ranking")).toBe(true);
  });
});

describe("api.setShortlisted", () => {
  it("posts the candidate id and desired flag", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        candidate_id: "c1",
        shortlisted: true,
        redaction: { applied: true, fields: ["name"] },
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
        match: {
          overall: 80,
          components: {},
          degraded: [],
          methodology: {},
          skill_gaps: { entries: [], semantic_available: false },
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await api.setShortlisted("s1", "c1", true, "session-1");

    expect(result.shortlisted).toBe(true);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/v1/screening/s1/shortlist");
    expect(JSON.parse(init.body as string)).toEqual({ candidate_id: "c1", shortlisted: true });
  });
});
