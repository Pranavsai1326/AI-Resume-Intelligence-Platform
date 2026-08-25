/**
 * Pure helpers for editing a `Resume` immutably in the builder.
 *
 * Every function returns a new array/object rather than mutating its input, matching the
 * backend's own `apply_proposals` convention (app/ai/tailor.py) - the builder always replaces
 * state wholesale via `setResume(next)`, never patches in place.
 */

import type {
  CertificationEntry,
  CustomSection,
  DateRange,
  EducationEntry,
  ExperienceEntry,
  ProjectEntry,
  Provenance,
  Provenanced,
  Resume,
} from "@/lib/api-client";

export function userProvided<T>(value: T): Provenanced<T> {
  return { value, provenance: userProvidedProvenance() };
}

export function userProvidedProvenance(): Provenance {
  return { kind: "user_provided", confidence: null, source: null };
}

export function moveItem<T>(items: T[], index: number, direction: -1 | 1): T[] {
  const target = index + direction;
  if (target < 0 || target >= items.length) return items;
  const next = items.slice();
  const [item] = next.splice(index, 1) as [T];
  next.splice(target, 0, item);
  return next;
}

export function removeItem<T>(items: T[], index: number): T[] {
  return items.filter((_, i) => i !== index);
}

export function updateItem<T>(items: T[], index: number, next: T): T[] {
  return items.map((item, i) => (i === index ? next : item));
}

export function emptyResume(): Resume {
  return {
    contact: { full_name: null, email: null, phone: null, location: null, links: [] },
    summary: null,
    experience: [],
    education: [],
    skills: [],
    projects: [],
    certifications: [],
    custom_sections: [],
  };
}

export function emptyDateRange(): DateRange {
  return { raw: "", start: null, end: null, is_current: false };
}

/** Renders a `DateRange` for display - "start – end", "start – Present", or the raw text as a fallback. */
export function formatDateRange(dates: DateRange | null): string {
  if (!dates) return "";
  if (dates.start || dates.end || dates.is_current) {
    const end = dates.is_current ? "Present" : (dates.end ?? "");
    return [dates.start ?? "", end].filter(Boolean).join(" – ");
  }
  return dates.raw;
}

// ---------------------------------------------------------------------------
// Section movement ("Move to...", Phase 9D spec section 5): entries can be reclassified between
// structurally compatible sections. Two compatibility groups, bridged by custom sections:
//   - "bulleted work item":  experience <-> projects <-> custom_sections
//   - "credential":          education <-> certifications <-> custom_sections
// A conversion never silently drops data it cannot map directly - fields with no equivalent on
// the target shape are folded into the closest textual field (a bullet, a note) instead.
// ---------------------------------------------------------------------------

export type MovableSection = "experience" | "education" | "projects" | "certifications" | "custom_sections";

const SECTION_COMPATIBILITY: Record<MovableSection, MovableSection[]> = {
  experience: ["projects", "custom_sections"],
  projects: ["experience", "custom_sections"],
  custom_sections: ["experience", "projects", "education", "certifications"],
  education: ["certifications", "custom_sections"],
  certifications: ["education", "custom_sections"],
};

export function compatibleSections(from: MovableSection): MovableSection[] {
  return SECTION_COMPATIBILITY[from];
}

export const SECTION_LABEL: Record<MovableSection, string> = {
  experience: "Experience",
  education: "Education",
  projects: "Projects",
  certifications: "Certifications",
  custom_sections: "Custom section",
};

function experienceToProject(entry: ExperienceEntry): ProjectEntry {
  return {
    name: entry.title || entry.organization,
    description: entry.organization ? `${entry.title} at ${entry.organization}`.trim() : null,
    bullets: entry.bullets,
    technologies: [],
    dates: entry.dates,
  };
}

function experienceToCustom(entry: ExperienceEntry): CustomSection {
  const title = [entry.title, entry.organization].filter(Boolean).join(" — ");
  return { title: title || "Untitled entry", bullets: entry.bullets };
}

function projectToExperience(entry: ProjectEntry): ExperienceEntry {
  const bullets = entry.technologies.length
    ? [...entry.bullets, `Technologies: ${entry.technologies.join(", ")}`]
    : entry.bullets;
  return {
    title: entry.name,
    organization: entry.description ?? "",
    location: null,
    dates: entry.dates,
    bullets,
  };
}

function projectToCustom(entry: ProjectEntry): CustomSection {
  const bullets = [
    ...(entry.description ? [entry.description] : []),
    ...entry.bullets,
    ...(entry.technologies.length ? [`Technologies: ${entry.technologies.join(", ")}`] : []),
  ];
  return { title: entry.name || "Untitled project", bullets };
}

function customToExperience(entry: CustomSection): ExperienceEntry {
  return { title: entry.title, organization: "", location: null, dates: null, bullets: entry.bullets };
}

function customToProject(entry: CustomSection): ProjectEntry {
  return { name: entry.title, description: null, bullets: entry.bullets, technologies: [], dates: null };
}

function educationToCertification(entry: EducationEntry): CertificationEntry {
  const name = [entry.degree, entry.field_of_study].filter(Boolean).join(", ") || entry.institution;
  return { name, issuer: entry.institution || null, date: entry.dates?.raw ?? null };
}

function educationToCustom(entry: EducationEntry): CustomSection {
  const bullets = [
    ...(entry.degree ? [entry.degree] : []),
    ...(entry.field_of_study ? [entry.field_of_study] : []),
    ...entry.details,
  ];
  return { title: entry.institution || "Untitled entry", bullets };
}

function certificationToEducation(entry: CertificationEntry): EducationEntry {
  return {
    institution: entry.issuer ?? entry.name,
    degree: entry.issuer ? entry.name : null,
    field_of_study: null,
    location: null,
    dates: entry.date ? { raw: entry.date, start: null, end: entry.date, is_current: false } : null,
    details: [],
  };
}

function certificationToCustom(entry: CertificationEntry): CustomSection {
  const bullets = [...(entry.issuer ? [entry.issuer] : []), ...(entry.date ? [entry.date] : [])];
  return { title: entry.name || "Untitled certification", bullets };
}

function customToEducation(entry: CustomSection): EducationEntry {
  return {
    institution: entry.title,
    degree: null,
    field_of_study: null,
    location: null,
    dates: null,
    details: entry.bullets,
  };
}

function customToCertification(entry: CustomSection): CertificationEntry {
  return { name: entry.title, issuer: entry.bullets[0] ?? null, date: null };
}

type ConversionKey = `${MovableSection}->${MovableSection}`;
type Converter = (value: unknown) => unknown;

const CONVERTERS: Partial<Record<ConversionKey, Converter>> = {
  "experience->projects": (v) => experienceToProject(v as ExperienceEntry),
  "experience->custom_sections": (v) => experienceToCustom(v as ExperienceEntry),
  "projects->experience": (v) => projectToExperience(v as ProjectEntry),
  "projects->custom_sections": (v) => projectToCustom(v as ProjectEntry),
  "custom_sections->experience": (v) => customToExperience(v as CustomSection),
  "custom_sections->projects": (v) => customToProject(v as CustomSection),
  "education->certifications": (v) => educationToCertification(v as EducationEntry),
  "education->custom_sections": (v) => educationToCustom(v as EducationEntry),
  "certifications->education": (v) => certificationToEducation(v as CertificationEntry),
  "certifications->custom_sections": (v) => certificationToCustom(v as CertificationEntry),
  "custom_sections->education": (v) => customToEducation(v as CustomSection),
  "custom_sections->certifications": (v) => customToCertification(v as CustomSection),
};

/**
 * Reclassifies one entry from `from[index]` into the `to` section, converting its shape via the
 * mapping above. Provenance becomes `user_provided` - moving an entry to correct its
 * classification is itself a correction, the same as any other edit.
 */
export function moveEntryToSection(
  resume: Resume,
  from: MovableSection,
  index: number,
  to: MovableSection,
): Resume {
  if (from === to) return resume;
  if (!SECTION_COMPATIBILITY[from].includes(to)) return resume;

  const fromArr = resume[from] as Provenanced<unknown>[];
  const entry = fromArr[index];
  if (!entry) return resume;

  const convert = CONVERTERS[`${from}->${to}`];
  if (!convert) return resume;

  const converted: Provenanced<unknown> = {
    value: convert(entry.value),
    provenance: userProvidedProvenance(),
  };

  const nextFrom = removeItem(fromArr, index);
  const toArr = resume[to] as Provenanced<unknown>[];
  const nextTo = [...toArr, converted];

  return { ...resume, [from]: nextFrom, [to]: nextTo } as Resume;
}
