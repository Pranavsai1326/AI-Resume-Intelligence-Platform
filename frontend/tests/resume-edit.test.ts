import { describe, expect, it } from "vitest";

import {
  compatibleSections,
  emptyResume,
  formatDateRange,
  moveEntryToSection,
  userProvided,
} from "@/lib/resume-edit";
import type { ExperienceEntry, ProjectEntry, Resume } from "@/lib/api-client";

function resumeWithExperience(entry: Partial<ExperienceEntry> = {}): Resume {
  const resume = emptyResume();
  resume.experience = [
    userProvided({
      title: "Senior Backend Engineer",
      organization: "Cascade Systems",
      location: null,
      dates: { raw: "Jan 2021 – Present", start: "2021-01", end: null, is_current: true },
      bullets: ["Migrated the billing pipeline"],
      ...entry,
    }),
  ];
  return resume;
}

describe("moveEntryToSection", () => {
  it("moves an experience entry into projects, preserving bullets and dates", () => {
    const resume = resumeWithExperience();
    const next = moveEntryToSection(resume, "experience", 0, "projects");

    expect(next.experience).toHaveLength(0);
    expect(next.projects).toHaveLength(1);
    const project = next.projects[0]!.value as ProjectEntry;
    expect(project.name).toBe("Senior Backend Engineer");
    expect(project.bullets).toEqual(["Migrated the billing pipeline"]);
    expect(project.dates?.is_current).toBe(true);
    expect(next.projects[0]!.provenance.kind).toBe("user_provided");
  });

  it("moves an experience entry into a custom section, folding title and organization", () => {
    const resume = resumeWithExperience();
    const next = moveEntryToSection(resume, "experience", 0, "custom_sections");

    expect(next.custom_sections).toHaveLength(1);
    expect(next.custom_sections[0]!.value.title).toBe("Senior Backend Engineer — Cascade Systems");
    expect(next.custom_sections[0]!.value.bullets).toEqual(["Migrated the billing pipeline"]);
  });

  it("round-trips a project back into experience without losing technologies", () => {
    const resume = emptyResume();
    resume.projects = [
      userProvided({
        name: "Trailmark",
        description: null,
        bullets: ["Open source resume parser"],
        technologies: ["Python", "FastAPI"],
        dates: null,
      }),
    ];

    const next = moveEntryToSection(resume, "projects", 0, "experience");
    const experience = next.experience[0]!.value as ExperienceEntry;
    expect(experience.title).toBe("Trailmark");
    expect(experience.bullets).toContain("Technologies: Python, FastAPI");
  });

  it("refuses an incompatible move and returns the resume unchanged", () => {
    const resume = resumeWithExperience();
    // "experience" and "education" are not in the same compatibility group - the guard is a
    // runtime check (compatibleSections), since MovableSection itself doesn't encode which
    // pairs are actually convertible.
    const next = moveEntryToSection(resume, "experience", 0, "education");
    expect(next).toBe(resume);
  });

  it("is a no-op when moving to the same section", () => {
    const resume = resumeWithExperience();
    const next = moveEntryToSection(resume, "experience", 0, "experience");
    expect(next).toBe(resume);
  });

  it("does nothing when the index is out of range", () => {
    const resume = resumeWithExperience();
    const next = moveEntryToSection(resume, "experience", 5, "projects");
    expect(next).toBe(resume);
  });
});

describe("compatibleSections", () => {
  it("bridges experience/projects and education/certifications through custom sections", () => {
    expect(compatibleSections("experience")).toEqual(["projects", "custom_sections"]);
    expect(compatibleSections("custom_sections")).toEqual([
      "experience",
      "projects",
      "education",
      "certifications",
    ]);
  });
});

describe("formatDateRange", () => {
  it("renders a current role as '<start> – Present'", () => {
    expect(formatDateRange({ raw: "", start: "2021-01", end: null, is_current: true })).toBe(
      "2021-01 – Present",
    );
  });

  it("falls back to the raw text when no structured fields are set", () => {
    expect(formatDateRange({ raw: "Summer 2019", start: null, end: null, is_current: false })).toBe(
      "Summer 2019",
    );
  });

  it("returns an empty string for a null date range", () => {
    expect(formatDateRange(null)).toBe("");
  });
});
