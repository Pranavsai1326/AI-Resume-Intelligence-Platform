"use client";

import * as React from "react";
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";

import { AiRewriteControl } from "@/components/builder/ai-rewrite-control";
import { DateRangeEditor } from "@/components/builder/date-range-editor";
import { Button } from "@/components/ui/button";
import { ConfidenceHint } from "@/components/ui/confidence-hint";
import {
  SECTION_LABEL,
  compatibleSections,
  moveEntryToSection,
  moveItem,
  removeItem,
  updateItem,
  userProvided,
} from "@/lib/resume-edit";
import type { MovableSection as MovableSectionType } from "@/lib/resume-edit";
import type {
  CertificationEntry,
  CustomSection,
  EducationEntry,
  ExperienceEntry,
  ProjectEntry,
  Provenanced,
  Resume,
  SkillGroup,
} from "@/lib/api-client";

/*
  Section editor: the extraction-review and resume-editing surface (Phase 9D). Add/edit/delete,
  move-up/move-down for reordering (drag-and-drop was deliberately not built - explicit up/down
  buttons instead), and "Move to..." for reclassifying an entry into a compatible section. Entry
  headers read like a document (title / organization / dates on one line) with the action
  toolbar revealed on hover or keyboard focus rather than permanently taking up space.
*/

const FIELD_CLASS =
  "w-full rounded-card border border-border-strong bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-subtle focus-visible:outline-none";

const INLINE_FIELD_CLASS =
  "rounded-card border border-transparent bg-transparent px-1 py-0.5 text-sm font-medium text-ink placeholder:text-ink-subtle hover:border-border-strong focus-visible:border-border-strong focus-visible:outline-none";

export function SectionEditor({
  documentId,
  sessionId,
  resume,
  onChange,
}: {
  documentId: string;
  sessionId: string;
  resume: Resume;
  onChange: (next: Resume) => void;
}) {
  return (
    <div className="space-y-8">
      <ContactAndSummaryEditor
        documentId={documentId}
        sessionId={sessionId}
        resume={resume}
        onChange={onChange}
      />
      <ExperienceEditor
        documentId={documentId}
        sessionId={sessionId}
        resume={resume}
        entries={resume.experience}
        onChange={(experience) => onChange({ ...resume, experience })}
        onResumeChange={onChange}
      />
      <EducationEditor
        resume={resume}
        entries={resume.education}
        onChange={(education) => onChange({ ...resume, education })}
        onResumeChange={onChange}
      />
      <SkillsEditor groups={resume.skills} onChange={(skills) => onChange({ ...resume, skills })} />
      <ProjectsEditor
        documentId={documentId}
        sessionId={sessionId}
        resume={resume}
        entries={resume.projects}
        onChange={(projects) => onChange({ ...resume, projects })}
        onResumeChange={onChange}
      />
      <CertificationsEditor
        resume={resume}
        entries={resume.certifications}
        onChange={(certifications) => onChange({ ...resume, certifications })}
        onResumeChange={onChange}
      />
      <CustomSectionsEditor
        documentId={documentId}
        sessionId={sessionId}
        resume={resume}
        entries={resume.custom_sections}
        onChange={(custom_sections) => onChange({ ...resume, custom_sections })}
        onResumeChange={onChange}
      />
    </div>
  );
}

function MoveToMenu({
  from,
  onMove,
}: {
  from: MovableSectionType;
  onMove: (to: MovableSectionType) => void;
}) {
  const targets = compatibleSections(from);
  if (targets.length === 0) return null;
  return (
    <select
      aria-label="Move to a different section"
      value=""
      onChange={(e) => {
        const value = e.target.value as MovableSectionType;
        if (value) onMove(value);
      }}
      className="h-8 rounded-card border border-border-strong bg-surface px-1.5 text-xs text-ink-muted focus-visible:outline-none"
    >
      <option value="" disabled>
        Move to…
      </option>
      {targets.map((target) => (
        <option key={target} value={target}>
          {SECTION_LABEL[target]}
        </option>
      ))}
    </select>
  );
}

function EntryToolbar({
  index,
  count,
  onMove,
  onRemove,
  moveTo,
}: {
  index: number;
  count: number;
  onMove: (direction: -1 | 1) => void;
  onRemove: () => void;
  moveTo?: React.ReactNode;
}) {
  return (
    <div className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
      {moveTo}
      <Button
        type="button"
        variant="ghost"
        size="sm"
        aria-label="Move up"
        disabled={index === 0}
        onClick={() => onMove(-1)}
      >
        <ArrowUp aria-hidden />
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        aria-label="Move down"
        disabled={index === count - 1}
        onClick={() => onMove(1)}
      >
        <ArrowDown aria-hidden />
      </Button>
      <Button type="button" variant="ghost" size="sm" aria-label="Delete entry" onClick={onRemove}>
        <Trash2 aria-hidden className="text-danger" />
      </Button>
    </div>
  );
}

function ContactAndSummaryEditor({
  documentId,
  sessionId,
  resume,
  onChange,
}: {
  documentId: string;
  sessionId: string;
  resume: Resume;
  onChange: (next: Resume) => void;
}) {
  const summaryText = resume.summary?.value ?? "";

  return (
    <section aria-labelledby="contact-heading" className="space-y-3">
      <h2 id="contact-heading" className="text-[length:var(--text-h2)] font-semibold text-ink">
        Contact &amp; summary
      </h2>
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <input
            className={FIELD_CLASS}
            placeholder="Full name"
            value={resume.contact.full_name?.value ?? ""}
            onChange={(e) =>
              onChange({
                ...resume,
                contact: { ...resume.contact, full_name: userProvided(e.target.value) },
              })
            }
          />
          <ConfidenceHint provenance={resume.contact.full_name?.provenance} className="mt-1" />
        </div>
        <input
          className={FIELD_CLASS}
          placeholder="Email"
          value={resume.contact.email?.value ?? ""}
          onChange={(e) =>
            onChange({
              ...resume,
              contact: { ...resume.contact, email: userProvided(e.target.value) },
            })
          }
        />
        <input
          className={FIELD_CLASS}
          placeholder="Phone"
          value={resume.contact.phone?.value ?? ""}
          onChange={(e) =>
            onChange({
              ...resume,
              contact: { ...resume.contact, phone: userProvided(e.target.value) },
            })
          }
        />
        <input
          className={FIELD_CLASS}
          placeholder="Location"
          value={resume.contact.location?.value ?? ""}
          onChange={(e) =>
            onChange({
              ...resume,
              contact: { ...resume.contact, location: userProvided(e.target.value) },
            })
          }
        />
      </div>

      <div className="space-y-2">
        <textarea
          className={FIELD_CLASS}
          rows={3}
          placeholder="Professional summary"
          value={summaryText}
          onChange={(e) =>
            onChange({
              ...resume,
              summary: e.target.value ? userProvided(e.target.value) : null,
            })
          }
        />
        <AiRewriteControl
          documentId={documentId}
          sessionId={sessionId}
          kind="summary"
          text={summaryText}
          onAccept={(next) => onChange({ ...resume, summary: userProvided(next) })}
        />
      </div>
    </section>
  );
}

function newExperience(): Provenanced<ExperienceEntry> {
  return userProvided({ title: "", organization: "", location: null, dates: null, bullets: [] });
}

function ExperienceEditor({
  documentId,
  sessionId,
  resume,
  entries,
  onChange,
  onResumeChange,
}: {
  documentId: string;
  sessionId: string;
  resume: Resume;
  entries: Provenanced<ExperienceEntry>[];
  onChange: (next: Provenanced<ExperienceEntry>[]) => void;
  onResumeChange: (next: Resume) => void;
}) {
  return (
    <section aria-labelledby="experience-heading" className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 id="experience-heading" className="text-[length:var(--text-h2)] font-semibold text-ink">
          Experience
        </h2>
        <Button type="button" variant="ghost" size="sm" onClick={() => onChange([...entries, newExperience()])}>
          <Plus aria-hidden />
          Add entry
        </Button>
      </div>
      <div className="space-y-3">
        {entries.map((entry, index) => (
          <div key={index} className="group rounded-card border border-border p-3">
            <div className="flex items-start gap-2">
              <div className="flex-1 space-y-2">
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                  <input
                    className={INLINE_FIELD_CLASS}
                    placeholder="Job title"
                    value={entry.value.title}
                    onChange={(e) =>
                      onChange(
                        updateItem(entries, index, {
                          ...entry,
                          value: { ...entry.value, title: e.target.value },
                        }),
                      )
                    }
                  />
                  <span aria-hidden className="text-ink-subtle">
                    at
                  </span>
                  <input
                    className={INLINE_FIELD_CLASS}
                    placeholder="Organization"
                    value={entry.value.organization}
                    onChange={(e) =>
                      onChange(
                        updateItem(entries, index, {
                          ...entry,
                          value: { ...entry.value, organization: e.target.value },
                        }),
                      )
                    }
                  />
                  <ConfidenceHint provenance={entry.provenance} />
                </div>
                <DateRangeEditor
                  dates={entry.value.dates}
                  onChange={(dates) =>
                    onChange(updateItem(entries, index, { ...entry, value: { ...entry.value, dates } }))
                  }
                />
                <BulletListEditor
                  documentId={documentId}
                  sessionId={sessionId}
                  bullets={entry.value.bullets}
                  onChange={(bullets) =>
                    onChange(updateItem(entries, index, { ...entry, value: { ...entry.value, bullets } }))
                  }
                />
              </div>
              <EntryToolbar
                index={index}
                count={entries.length}
                onMove={(direction) => onChange(moveItem(entries, index, direction))}
                onRemove={() => onChange(removeItem(entries, index))}
                moveTo={
                  <MoveToMenu
                    from="experience"
                    onMove={(to) => onResumeChange(moveEntryToSection(resume, "experience", index, to))}
                  />
                }
              />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function BulletListEditor({
  documentId,
  sessionId,
  bullets,
  onChange,
}: {
  documentId: string;
  sessionId: string;
  bullets: string[];
  onChange: (next: string[]) => void;
}) {
  return (
    <div className="space-y-2">
      {bullets.map((bullet, index) => (
        <div key={index} className="space-y-1.5">
          <div className="flex items-start gap-2">
            <span aria-hidden className="mt-2.5 text-ink-subtle">
              •
            </span>
            <textarea
              className={FIELD_CLASS}
              rows={2}
              placeholder="Bullet point"
              value={bullet}
              onChange={(e) => onChange(updateItem(bullets, index, e.target.value))}
            />
            <Button
              type="button"
              variant="ghost"
              size="sm"
              aria-label="Delete bullet"
              onClick={() => onChange(removeItem(bullets, index))}
            >
              <Trash2 aria-hidden className="text-danger" />
            </Button>
          </div>
          <AiRewriteControl
            documentId={documentId}
            sessionId={sessionId}
            kind="bullet"
            text={bullet}
            onAccept={(next) => onChange(updateItem(bullets, index, next))}
          />
        </div>
      ))}
      <Button type="button" variant="ghost" size="sm" onClick={() => onChange([...bullets, ""])}>
        <Plus aria-hidden />
        Add bullet
      </Button>
    </div>
  );
}

function newEducation(): Provenanced<EducationEntry> {
  return userProvided({
    institution: "",
    degree: null,
    field_of_study: null,
    location: null,
    dates: null,
    details: [],
  });
}

function EducationEditor({
  resume,
  entries,
  onChange,
  onResumeChange,
}: {
  resume: Resume;
  entries: Provenanced<EducationEntry>[];
  onChange: (next: Provenanced<EducationEntry>[]) => void;
  onResumeChange: (next: Resume) => void;
}) {
  return (
    <section aria-labelledby="education-heading" className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 id="education-heading" className="text-[length:var(--text-h2)] font-semibold text-ink">
          Education
        </h2>
        <Button type="button" variant="ghost" size="sm" onClick={() => onChange([...entries, newEducation()])}>
          <Plus aria-hidden />
          Add entry
        </Button>
      </div>
      <div className="space-y-3">
        {entries.map((entry, index) => (
          <div key={index} className="group rounded-card border border-border p-3">
            <div className="flex items-start gap-2">
              <div className="flex-1 space-y-2">
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                  <input
                    className={INLINE_FIELD_CLASS}
                    placeholder="Institution"
                    value={entry.value.institution}
                    onChange={(e) =>
                      onChange(
                        updateItem(entries, index, {
                          ...entry,
                          value: { ...entry.value, institution: e.target.value },
                        }),
                      )
                    }
                  />
                  <ConfidenceHint provenance={entry.provenance} />
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  <input
                    className={FIELD_CLASS}
                    placeholder="Degree"
                    value={entry.value.degree ?? ""}
                    onChange={(e) =>
                      onChange(
                        updateItem(entries, index, {
                          ...entry,
                          value: { ...entry.value, degree: e.target.value || null },
                        }),
                      )
                    }
                  />
                  <input
                    className={FIELD_CLASS}
                    placeholder="Field of study"
                    value={entry.value.field_of_study ?? ""}
                    onChange={(e) =>
                      onChange(
                        updateItem(entries, index, {
                          ...entry,
                          value: { ...entry.value, field_of_study: e.target.value || null },
                        }),
                      )
                    }
                  />
                  <input
                    className={FIELD_CLASS}
                    placeholder="Location"
                    value={entry.value.location ?? ""}
                    onChange={(e) =>
                      onChange(
                        updateItem(entries, index, {
                          ...entry,
                          value: { ...entry.value, location: e.target.value || null },
                        }),
                      )
                    }
                  />
                </div>
                <DateRangeEditor
                  dates={entry.value.dates}
                  onChange={(dates) =>
                    onChange(updateItem(entries, index, { ...entry, value: { ...entry.value, dates } }))
                  }
                />
              </div>
              <EntryToolbar
                index={index}
                count={entries.length}
                onMove={(direction) => onChange(moveItem(entries, index, direction))}
                onRemove={() => onChange(removeItem(entries, index))}
                moveTo={
                  <MoveToMenu
                    from="education"
                    onMove={(to) => onResumeChange(moveEntryToSection(resume, "education", index, to))}
                  />
                }
              />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function newSkillGroup(): Provenanced<SkillGroup> {
  return userProvided({ category: "", skills: [] });
}

function SkillsEditor({
  groups,
  onChange,
}: {
  groups: Provenanced<SkillGroup>[];
  onChange: (next: Provenanced<SkillGroup>[]) => void;
}) {
  return (
    <section aria-labelledby="skills-heading" className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 id="skills-heading" className="text-[length:var(--text-h2)] font-semibold text-ink">
          Skills
        </h2>
        <Button type="button" variant="ghost" size="sm" onClick={() => onChange([...groups, newSkillGroup()])}>
          <Plus aria-hidden />
          Add group
        </Button>
      </div>
      <div className="space-y-3">
        {groups.map((group, index) => (
          <div key={index} className="group flex items-start gap-2 rounded-card border border-border p-3">
            <div className="flex-1 space-y-2">
              <input
                className={FIELD_CLASS}
                placeholder="Category (optional)"
                value={group.value.category ?? ""}
                onChange={(e) =>
                  onChange(
                    updateItem(groups, index, {
                      ...group,
                      value: { ...group.value, category: e.target.value || null },
                    }),
                  )
                }
              />
              <input
                className={FIELD_CLASS}
                placeholder="Skills, comma separated"
                value={group.value.skills.join(", ")}
                onChange={(e) =>
                  onChange(
                    updateItem(groups, index, {
                      ...group,
                      value: {
                        ...group.value,
                        skills: e.target.value
                          .split(",")
                          .map((s) => s.trim())
                          .filter(Boolean),
                      },
                    }),
                  )
                }
              />
            </div>
            <EntryToolbar
              index={index}
              count={groups.length}
              onMove={(direction) => onChange(moveItem(groups, index, direction))}
              onRemove={() => onChange(removeItem(groups, index))}
            />
          </div>
        ))}
      </div>
    </section>
  );
}

function newProject(): Provenanced<ProjectEntry> {
  return userProvided({ name: "", description: null, bullets: [], technologies: [], dates: null });
}

function ProjectsEditor({
  documentId,
  sessionId,
  resume,
  entries,
  onChange,
  onResumeChange,
}: {
  documentId: string;
  sessionId: string;
  resume: Resume;
  entries: Provenanced<ProjectEntry>[];
  onChange: (next: Provenanced<ProjectEntry>[]) => void;
  onResumeChange: (next: Resume) => void;
}) {
  return (
    <section aria-labelledby="projects-heading" className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 id="projects-heading" className="text-[length:var(--text-h2)] font-semibold text-ink">
          Projects
        </h2>
        <Button type="button" variant="ghost" size="sm" onClick={() => onChange([...entries, newProject()])}>
          <Plus aria-hidden />
          Add project
        </Button>
      </div>
      <div className="space-y-3">
        {entries.map((entry, index) => (
          <div key={index} className="group rounded-card border border-border p-3">
            <div className="flex items-start gap-2">
              <div className="flex-1 space-y-2">
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                  <input
                    className={INLINE_FIELD_CLASS}
                    placeholder="Project name"
                    value={entry.value.name}
                    onChange={(e) =>
                      onChange(
                        updateItem(entries, index, { ...entry, value: { ...entry.value, name: e.target.value } }),
                      )
                    }
                  />
                  <ConfidenceHint provenance={entry.provenance} />
                </div>
                <textarea
                  className={FIELD_CLASS}
                  rows={2}
                  placeholder="Description"
                  value={entry.value.description ?? ""}
                  onChange={(e) =>
                    onChange(
                      updateItem(entries, index, {
                        ...entry,
                        value: { ...entry.value, description: e.target.value || null },
                      }),
                    )
                  }
                />
                <input
                  className={FIELD_CLASS}
                  placeholder="Technologies, comma separated"
                  value={entry.value.technologies.join(", ")}
                  onChange={(e) =>
                    onChange(
                      updateItem(entries, index, {
                        ...entry,
                        value: {
                          ...entry.value,
                          technologies: e.target.value
                            .split(",")
                            .map((s) => s.trim())
                            .filter(Boolean),
                        },
                      }),
                    )
                  }
                />
                <DateRangeEditor
                  dates={entry.value.dates}
                  onChange={(dates) =>
                    onChange(updateItem(entries, index, { ...entry, value: { ...entry.value, dates } }))
                  }
                />
                <BulletListEditor
                  documentId={documentId}
                  sessionId={sessionId}
                  bullets={entry.value.bullets}
                  onChange={(bullets) =>
                    onChange(updateItem(entries, index, { ...entry, value: { ...entry.value, bullets } }))
                  }
                />
              </div>
              <EntryToolbar
                index={index}
                count={entries.length}
                onMove={(direction) => onChange(moveItem(entries, index, direction))}
                onRemove={() => onChange(removeItem(entries, index))}
                moveTo={
                  <MoveToMenu
                    from="projects"
                    onMove={(to) => onResumeChange(moveEntryToSection(resume, "projects", index, to))}
                  />
                }
              />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function newCertification(): Provenanced<CertificationEntry> {
  return userProvided({ name: "", issuer: null, date: null });
}

function CertificationsEditor({
  resume,
  entries,
  onChange,
  onResumeChange,
}: {
  resume: Resume;
  entries: Provenanced<CertificationEntry>[];
  onChange: (next: Provenanced<CertificationEntry>[]) => void;
  onResumeChange: (next: Resume) => void;
}) {
  return (
    <section aria-labelledby="certifications-heading" className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 id="certifications-heading" className="text-[length:var(--text-h2)] font-semibold text-ink">
          Certifications
        </h2>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => onChange([...entries, newCertification()])}
        >
          <Plus aria-hidden />
          Add certification
        </Button>
      </div>
      <div className="space-y-3">
        {entries.map((entry, index) => (
          <div key={index} className="group flex items-start gap-2 rounded-card border border-border p-3">
            <div className="grid flex-1 gap-2 sm:grid-cols-2">
              <input
                className={FIELD_CLASS}
                placeholder="Certification name"
                value={entry.value.name}
                onChange={(e) =>
                  onChange(
                    updateItem(entries, index, { ...entry, value: { ...entry.value, name: e.target.value } }),
                  )
                }
              />
              <input
                className={FIELD_CLASS}
                placeholder="Issuer"
                value={entry.value.issuer ?? ""}
                onChange={(e) =>
                  onChange(
                    updateItem(entries, index, {
                      ...entry,
                      value: { ...entry.value, issuer: e.target.value || null },
                    }),
                  )
                }
              />
            </div>
            <EntryToolbar
              index={index}
              count={entries.length}
              onMove={(direction) => onChange(moveItem(entries, index, direction))}
              onRemove={() => onChange(removeItem(entries, index))}
              moveTo={
                <MoveToMenu
                  from="certifications"
                  onMove={(to) => onResumeChange(moveEntryToSection(resume, "certifications", index, to))}
                />
              }
            />
          </div>
        ))}
      </div>
    </section>
  );
}

function newCustomSection(): Provenanced<CustomSection> {
  return userProvided({ title: "", bullets: [] });
}

function CustomSectionsEditor({
  documentId,
  sessionId,
  resume,
  entries,
  onChange,
  onResumeChange,
}: {
  documentId: string;
  sessionId: string;
  resume: Resume;
  entries: Provenanced<CustomSection>[];
  onChange: (next: Provenanced<CustomSection>[]) => void;
  onResumeChange: (next: Resume) => void;
}) {
  return (
    <section aria-labelledby="custom-sections-heading" className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 id="custom-sections-heading" className="text-[length:var(--text-h2)] font-semibold text-ink">
          Custom sections
        </h2>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => onChange([...entries, newCustomSection()])}
        >
          <Plus aria-hidden />
          Add section
        </Button>
      </div>
      {entries.length === 0 ? (
        <p className="text-sm text-ink-subtle">
          Anything that doesn&apos;t fit the sections above — awards, publications, volunteering —
          can go here.
        </p>
      ) : null}
      <div className="space-y-3">
        {entries.map((entry, index) => (
          <div key={index} className="group rounded-card border border-border p-3">
            <div className="flex items-start gap-2">
              <div className="flex-1 space-y-2">
                <input
                  className={INLINE_FIELD_CLASS}
                  placeholder="Section title"
                  value={entry.value.title}
                  onChange={(e) =>
                    onChange(
                      updateItem(entries, index, { ...entry, value: { ...entry.value, title: e.target.value } }),
                    )
                  }
                />
                <BulletListEditor
                  documentId={documentId}
                  sessionId={sessionId}
                  bullets={entry.value.bullets}
                  onChange={(bullets) =>
                    onChange(updateItem(entries, index, { ...entry, value: { ...entry.value, bullets } }))
                  }
                />
              </div>
              <EntryToolbar
                index={index}
                count={entries.length}
                onMove={(direction) => onChange(moveItem(entries, index, direction))}
                onRemove={() => onChange(removeItem(entries, index))}
                moveTo={
                  <MoveToMenu
                    from="custom_sections"
                    onMove={(to) => onResumeChange(moveEntryToSection(resume, "custom_sections", index, to))}
                  />
                }
              />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
