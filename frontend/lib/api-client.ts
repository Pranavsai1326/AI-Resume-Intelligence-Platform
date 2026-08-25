/**
 * Backend client.
 *
 * Every request carries the session id in the `X-Session-Id` header - never a cookie, which is
 * what keeps CSRF off the table. Error envelopes from the API are turned into typed `ApiError`
 * instances so the UI can react to a category rather than parsing messages.
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export type ErrorCategory =
  | "validation"
  | "session"
  | "rate_limit"
  | "unavailable"
  | "timeout"
  | "internal"
  | "network";

export class ApiError extends Error {
  readonly code: string;
  readonly category: ErrorCategory;
  readonly retryable: boolean;
  readonly requestId: string | null;
  readonly status: number;

  constructor(init: {
    code: string;
    category: ErrorCategory;
    message: string;
    retryable: boolean;
    requestId: string | null;
    status: number;
  }) {
    super(init.message);
    this.name = "ApiError";
    this.code = init.code;
    this.category = init.category;
    this.retryable = init.retryable;
    this.requestId = init.requestId;
    this.status = init.status;
  }

  /** The session is gone server-side; the UI must stop and offer a fresh start. */
  get isSessionGone(): boolean {
    return this.code === "SESSION_EXPIRED" || this.code === "SESSION_REQUIRED";
  }
}

const NETWORK_ERROR = new ApiError({
  code: "NETWORK_UNREACHABLE",
  category: "network",
  message: "Could not reach the server. Check your connection and try again.",
  retryable: true,
  requestId: null,
  status: 0,
});

export type SessionMode = "candidate" | "recruiter";

export interface SessionInfo {
  session_id: string;
  mode: SessionMode;
  created_at: string;
  last_activity_at: string;
  expires_at: string;
  hard_expires_at: string;
  idle_ttl_seconds: number;
  absolute_ttl_seconds: number;
  counters: {
    documents: number;
    analyses: number;
    ai_calls: number;
    ai_tokens: number;
  };
}

export interface ReadyInfo {
  ready: boolean;
  session_store: string;
  session_store_reachable: boolean;
  capabilities: Record<string, boolean>;
}

export type DocumentKind = "pdf" | "docx" | "txt";

export interface LayoutSignals {
  page_count: number | null;
  multi_column: boolean;
  has_tables: boolean;
  has_images: boolean;
  has_text_boxes: boolean;
  has_repeating_header_footer: boolean;
}

export interface ResumeSummary {
  has_name: boolean;
  has_email: boolean;
  has_phone: boolean;
  has_summary: boolean;
  experience_entries: number;
  education_entries: number;
  skill_groups: number;
  project_entries: number;
  certification_entries: number;
  custom_sections: number;
}

export interface DocumentUploadResponse {
  document_id: string;
  kind: DocumentKind;
  layout: LayoutSignals;
  ocr_used: boolean;
  text_length: number;
  resume_summary: ResumeSummary | null;
  cached: boolean;
}

export type EvidenceSeverity = "positive" | "info" | "warning";

export interface Evidence {
  message: string;
  severity: EvidenceSeverity;
}

export interface ComponentScore {
  key: string;
  label: string;
  score: number;
  weight: number;
  available: boolean;
  evidence: Evidence[];
  explanation: string;
}

export interface ResumeHealthResult {
  overall: number;
  components: Record<string, ComponentScore>;
  degraded: string[];
  methodology: Record<string, string>;
}

export type RequirementImportance = "required" | "preferred" | "optional";
export type RequirementKind =
  | "skill"
  | "soft_skill"
  | "experience"
  | "education"
  | "certification"
  | "responsibility";
export type EducationLevel = "none" | "associate" | "bachelor" | "master" | "phd";

export interface Requirement {
  text: string;
  kind: RequirementKind;
  importance: RequirementImportance;
  keywords: string[];
  min_years: number | null;
  education_level: EducationLevel | null;
}

export interface JobDescription {
  title: string | null;
  requirements: Requirement[];
  responsibilities: string[];
  raw_text: string;
}

export interface CreateJobResponse {
  job_id: string;
  job: JobDescription;
}

export type SkillGapBucket = "strong" | "moderate" | "missing" | "insufficient_evidence";

export interface SkillGapEntry {
  skill: string;
  requirement_text: string;
  importance: RequirementImportance;
  bucket: SkillGapBucket;
  evidence: string;
}

export interface SkillGapResult {
  entries: SkillGapEntry[];
  semantic_available: boolean;
}

export interface JobMatchResult {
  overall: number;
  components: Record<string, ComponentScore>;
  degraded: string[];
  methodology: Record<string, string>;
  skill_gaps: SkillGapResult;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  sessionId?: string | null;
  signal?: AbortSignal;
}

async function toApiError(response: Response): Promise<ApiError> {
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  const envelope =
    payload && typeof payload === "object" && "error" in payload
      ? (payload as { error: Record<string, unknown> }).error
      : null;

  return new ApiError({
    code: typeof envelope?.code === "string" ? envelope.code : "UNEXPECTED_ERROR",
    category: (typeof envelope?.category === "string"
      ? envelope.category
      : "internal") as ErrorCategory,
    message:
      typeof envelope?.message === "string"
        ? envelope.message
        : "Something went wrong. Please try again.",
    retryable: envelope?.retryable === true,
    requestId:
      typeof envelope?.request_id === "string"
        ? envelope.request_id
        : response.headers.get("X-Request-Id"),
    status: response.status,
  });
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, sessionId, signal } = options;

  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (sessionId) headers["X-Session-Id"] = sessionId;

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
      // No cookies are used, so no credentials are ever sent.
      credentials: "omit",
      cache: "no-store",
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw NETWORK_ERROR;
  }

  if (!response.ok) throw await toApiError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/**
 * Multipart upload. Deliberately bypasses `apiRequest`: a file upload must not set
 * `Content-Type` itself (the browser sets it, including the multipart boundary) and must send a
 * `FormData` body rather than JSON.
 */
async function uploadDocument(
  file: File,
  kind: "resume" | "job_description",
  sessionId: string,
  signal?: AbortSignal,
): Promise<DocumentUploadResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("kind", kind);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/v1/documents`, {
      method: "POST",
      headers: { "X-Session-Id": sessionId },
      body: form,
      signal,
      credentials: "omit",
      cache: "no-store",
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw NETWORK_ERROR;
  }

  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as DocumentUploadResponse;
}

export const api = {
  createSession: (mode: SessionMode, signal?: AbortSignal) =>
    apiRequest<SessionInfo>("/v1/session", { method: "POST", body: { mode }, signal }),

  getSession: (sessionId: string, signal?: AbortSignal) =>
    apiRequest<SessionInfo>("/v1/session", { sessionId, signal }),

  heartbeat: (sessionId: string, signal?: AbortSignal) =>
    apiRequest<SessionInfo>("/v1/session/heartbeat", { method: "POST", sessionId, signal }),

  endSession: (sessionId: string) =>
    apiRequest<void>("/v1/session", { method: "DELETE", sessionId }),

  ready: (signal?: AbortSignal) => apiRequest<ReadyInfo>("/ready", { signal }),

  uploadDocument,

  analyzeResume: (documentId: string, sessionId: string, signal?: AbortSignal) =>
    apiRequest<ResumeHealthResult>("/v1/analysis/resume", {
      method: "POST",
      body: { document_id: documentId },
      sessionId,
      signal,
    }),

  deleteDocument: (documentId: string, sessionId: string) =>
    apiRequest<void>(`/v1/documents/${documentId}`, { method: "DELETE", sessionId }),

  createJobFromText: (text: string, sessionId: string, signal?: AbortSignal) =>
    apiRequest<CreateJobResponse>("/v1/jobs", { method: "POST", body: { text }, sessionId, signal }),

  matchResumeToJob: (documentId: string, jobId: string, sessionId: string, signal?: AbortSignal) =>
    apiRequest<JobMatchResult>("/v1/match", {
      method: "POST",
      body: { document_id: documentId, job_id: jobId },
      sessionId,
      signal,
    }),
};

/**
 * Best-effort signal that this page is going away.
 *
 * `sendBeacon` cannot set headers, and an `application/json` content type would trigger a CORS
 * preflight that an unloading page may never finish - so the id goes in a `text/plain` body,
 * which is CORS-safelisted.
 *
 * This *releases* the session rather than destroying it. `pagehide` fires on a reload and on
 * ordinary navigation too, so destroying here would throw away the user's work whenever they
 * pressed refresh. The server shortens the session to a short grace window instead: a page that
 * comes back resumes it, and a tab that is really gone is cleaned up within minutes.
 *
 * An optimisation only - the server expires the session on its own schedule regardless.
 */
export function beaconReleaseSession(sessionId: string): boolean {
  if (typeof navigator === "undefined" || typeof navigator.sendBeacon !== "function") {
    return false;
  }
  const blob = new Blob([JSON.stringify({ session_id: sessionId })], {
    type: "text/plain;charset=UTF-8",
  });
  return navigator.sendBeacon(`${API_BASE_URL}/v1/session/release`, blob);
}
