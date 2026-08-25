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

describe("api.generateCoverLetter", () => {
  it("posts document/job/version ids and returns the honest unavailable response through untouched", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        salutation: null,
        body_paragraphs: [],
        closing: null,
        fact_guard_findings: [],
        available: false,
        unavailable_reason: "AI writing is not configured on this deployment.",
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await api.generateCoverLetter("doc-1", "job-1", "session-1", "v1");

    expect(result.available).toBe(false);
    expect(result.unavailable_reason).toBe("AI writing is not configured on this deployment.");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/v1/cover-letter");
    expect(JSON.parse(init.body as string)).toEqual({
      document_id: "doc-1",
      job_id: "job-1",
      version_id: "v1",
    });
  });
});

describe("api.generateInterviewQuestions", () => {
  it("returns the questions and fact-guard findings untouched", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          questions: [
            {
              question: "Tell me about the migration.",
              category: "technical",
              rationale: "You mention it in your experience.",
              grounded_in: "Migrated the billing pipeline",
              fact_guard_findings: [],
            },
          ],
          available: true,
          unavailable_reason: null,
        }),
      ),
    );

    const result = await api.generateInterviewQuestions("doc-1", "job-1", "session-1");

    expect(result.available).toBe(true);
    expect(result.questions).toHaveLength(1);
    expect(result.questions[0]?.category).toBe("technical");
  });
});

describe("api.getLearningPriorities", () => {
  it("requests priorities and returns the ranked list", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        priorities: [
          {
            skill: "docker",
            requirement_text: "Docker",
            importance: "required",
            bucket: "missing",
            reason: "Not found anywhere in your resume - the most direct gap to close.",
          },
        ],
        semantic_available: false,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await api.getLearningPriorities("doc-1", "job-1", "session-1");

    expect(result.priorities).toHaveLength(1);
    expect(result.priorities[0]?.skill).toBe("docker");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/v1/learning-priorities");
    expect(JSON.parse(init.body as string)).toEqual({
      document_id: "doc-1",
      job_id: "job-1",
      version_id: null,
    });
  });
});
