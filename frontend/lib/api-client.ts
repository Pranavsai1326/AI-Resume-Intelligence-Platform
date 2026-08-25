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

// ---------------------------------------------------------------------------
// Resume Builder (Phase 5): versions, AI rewriting, tailoring, export.
// ---------------------------------------------------------------------------

export type ProvenanceKind = "user_provided" | "extracted" | "ai_suggested" | "ai_generated";

export interface Provenance {
  kind: ProvenanceKind;
  confidence: number | null;
  source: { page: number | null; start: number | null; end: number | null } | null;
}

export interface Provenanced<T> {
  value: T;
  provenance: Provenance;
}

export interface DateRange {
  raw: string;
  start: string | null;
  end: string | null;
  is_current: boolean;
}

export interface ContactInfo {
  full_name: Provenanced<string> | null;
  email: Provenanced<string> | null;
  phone: Provenanced<string> | null;
  location: Provenanced<string> | null;
  links: Provenanced<string>[];
}

export interface ExperienceEntry {
  title: string;
  organization: string;
  location: string | null;
  dates: DateRange | null;
  bullets: string[];
}

export interface EducationEntry {
  institution: string;
  degree: string | null;
  field_of_study: string | null;
  location: string | null;
  dates: DateRange | null;
  details: string[];
}

export interface ProjectEntry {
  name: string;
  description: string | null;
  bullets: string[];
  technologies: string[];
  dates: DateRange | null;
}

export interface CertificationEntry {
  name: string;
  issuer: string | null;
  date: string | null;
}

export interface SkillGroup {
  category: string | null;
  skills: string[];
}

export interface CustomSection {
  title: string;
  bullets: string[];
}

export interface Resume {
  contact: ContactInfo;
  summary: Provenanced<string> | null;
  experience: Provenanced<ExperienceEntry>[];
  education: Provenanced<EducationEntry>[];
  skills: Provenanced<SkillGroup>[];
  projects: Provenanced<ProjectEntry>[];
  certifications: Provenanced<CertificationEntry>[];
  custom_sections: Provenanced<CustomSection>[];
}

export type VersionSource = "original" | "manual_edit" | "ai_tailored";

export interface VersionSummary {
  version_id: string;
  label: string;
  source: VersionSource;
  created_at: string;
  based_on_version_id: string | null;
}

export interface ResumeVersion extends VersionSummary {
  document_id: string;
  resume: Resume;
}

export interface RewriteProposal {
  before: string;
  after: string | null;
  fact_guard_findings: string[];
  available: boolean;
  unavailable_reason: string | null;
}

export interface TailorTarget {
  skill_group_index: number | null;
  experience_index: number | null;
  bullet_index: number | null;
}

export type TailorProposalKind = "reorder_skills" | "skill_reminder" | "bullet_rewrite";

export interface TailorProposal {
  proposal_id: string;
  kind: TailorProposalKind;
  rationale: string;
  target: TailorTarget;
  before: string | string[] | null;
  after: string | string[] | null;
  fact_guard_findings: string[];
  requires_ai: boolean;
}

export type ExportFormat = "pdf" | "docx";

export interface ExportResult {
  blob: Blob;
  filename: string;
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

/**
 * Filename from a `Content-Disposition: attachment; filename="..."` header. Falls back to a
 * generic name rather than throwing if the header is missing or unparsable - the download still
 * works, just without a meaningful name.
 */
function filenameFromContentDisposition(header: string | null, format: ExportFormat): string {
  if (!header) return `resume.${format}`;
  const match = /filename="?([^";]+)"?/i.exec(header);
  return match?.[1] ?? `resume.${format}`;
}

async function exportResume(
  documentId: string,
  format: ExportFormat,
  sessionId: string,
  versionId?: string | null,
  signal?: AbortSignal,
): Promise<ExportResult> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/v1/export`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Session-Id": sessionId },
      body: JSON.stringify({ document_id: documentId, version_id: versionId ?? null, format }),
      signal,
      credentials: "omit",
      cache: "no-store",
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw NETWORK_ERROR;
  }

  if (!response.ok) throw await toApiError(response);
  const blob = await response.blob();
  const filename = filenameFromContentDisposition(
    response.headers.get("Content-Disposition"),
    format,
  );
  return { blob, filename };
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

  listResumeVersions: (documentId: string, sessionId: string, signal?: AbortSignal) =>
    apiRequest<VersionSummary[]>(`/v1/resume/versions?document_id=${encodeURIComponent(documentId)}`, {
      sessionId,
      signal,
    }),

  getResumeVersion: (versionId: string, sessionId: string, signal?: AbortSignal) =>
    apiRequest<ResumeVersion>(`/v1/resume/versions/${encodeURIComponent(versionId)}`, {
      sessionId,
      signal,
    }),

  saveResumeVersion: (
    params: {
      documentId: string;
      label: string;
      resume?: Resume;
      basedOnVersionId?: string | null;
      source?: VersionSource;
    },
    sessionId: string,
    signal?: AbortSignal,
  ) =>
    apiRequest<ResumeVersion>("/v1/resume/versions", {
      method: "POST",
      body: {
        document_id: params.documentId,
        label: params.label,
        resume: params.resume ?? null,
        based_on_version_id: params.basedOnVersionId ?? null,
        source: params.source ?? "manual_edit",
      },
      sessionId,
      signal,
    }),

  rewriteText: (
    documentId: string,
    kind: "bullet" | "summary",
    text: string,
    sessionId: string,
    signal?: AbortSignal,
  ) =>
    apiRequest<RewriteProposal>("/v1/ai/rewrite", {
      method: "POST",
      body: { document_id: documentId, kind, text },
      sessionId,
      signal,
    }),

  generateTailorProposals: (
    documentId: string,
    jobId: string,
    sessionId: string,
    versionId?: string | null,
    signal?: AbortSignal,
  ) =>
    apiRequest<TailorProposal[]>("/v1/tailor", {
      method: "POST",
      body: { document_id: documentId, job_id: jobId, version_id: versionId ?? null },
      sessionId,
      signal,
    }),

  applyTailorProposals: (
    params: {
      documentId: string;
      versionId?: string | null;
      label?: string;
      proposals: TailorProposal[];
    },
    sessionId: string,
    signal?: AbortSignal,
  ) =>
    apiRequest<ResumeVersion>("/v1/tailor/apply", {
      method: "POST",
      body: {
        document_id: params.documentId,
        version_id: params.versionId ?? null,
        label: params.label ?? "Tailored",
        proposals: params.proposals,
      },
      sessionId,
      signal,
    }),

  exportResume,
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
