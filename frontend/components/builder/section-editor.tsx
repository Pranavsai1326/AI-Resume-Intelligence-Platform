"use client";

import * as React from "react";
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";

import { AiRewriteControl } from "@/components/builder/ai-rewrite-control";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { moveItem, removeItem, updateItem, userProvided } from "@/lib/resume-edit";
import type {
  CertificationEntry,
  EducationEntry,
  ExperienceEntry,
  ProjectEntry,
  Provenanced,
  Resume,
  SkillGroup,
} from "@/lib/api-client";

/*
  Section editor: add/edit/delete plus move-up/move-down for reordering (drag-and-drop was
  deliberately not built - the user chose explicit up/down buttons instead).
*/

const FIELD_CLASS =
  "w-full rounded-card border border-border-strong bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-subtle focus-visible:outline-none";

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
    <div className="space-y-5">
      <ContactAndSummaryEditor
        documentId={documentId}
        sessionId={sessionId}
        resume={resume}
        onChange={onChange}
      />
      <ExperienceEditor
        documentId={documentId}
        sessionId={sessionId}
        entries={resume.experience}
        onChange={(experience) => onChange({ ...resume, experience })}
      />
      <EducationEditor
        entries={resume.education}
        onChange={(education) => onChange({ ...resume, education })}
      />
      <SkillsEditor
        groups={resume.skills}
        onChange={(skills) => onChange({ ...resume, skills })}
      />
      <ProjectsEditor
        entries={resume.projects}
        onChange={(projects) => onChange({ ...resume, projects })}
      />
      <CertificationsEditor
        entries={resume.certifications}
        onChange={(certifications) => onChange({ ...resume, certifications })}
      />
    </div>
  );
}

function ReorderControls({
  index,
  count,
  onMove,
  onRemove,
}: {
  index: number;
  count: number;
  onMove: (direction: -1 | 1) => void;
  onRemove: () => void;
}) {
  return (
    <div className="flex shrink-0 items-center gap-1">
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
      <Button type="button" variant="ghost" size="sm" aria-label="Delete" onClick={onRemove}>
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
    <Card>
      <CardHeader>
        <CardTitle>Contact &amp; summary</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
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
      </CardContent>
    </Card>
  );
}

function newExperience(): Provenanced<ExperienceEntry> {
  return userProvided({ title: "", organization: "", location: null, dates: null, bullets: [] });
}

function ExperienceEditor({
  documentId,
  sessionId,
  entries,
  onChange,
}: {
  documentId: string;
  sessionId: string;
  entries: Provenanced<ExperienceEntry>[];
  onChange: (next: Provenanced<ExperienceEntry>[]) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Experience</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {entries.map((entry, index) => (
          <div key={index} className="rounded-card border border-border p-3">
            <div className="flex items-start gap-2">
              <div className="flex-1 space-y-2">
                <div className="grid gap-2 sm:grid-cols-2">
                  <input
                    className={FIELD_CLASS}
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
                  <input
                    className={FIELD_CLASS}
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
                </div>
                <BulletListEditor
                  documentId={documentId}
                  sessionId={sessionId}
                  bullets={entry.value.bullets}
                  onChange={(bullets) =>
                    onChange(updateItem(entries, index, { ...entry, value: { ...entry.value, bullets } }))
                  }
                />
              </div>
              <ReorderControls
                index={index}
                count={entries.length}
                onMove={(direction) => onChange(moveItem(entries, index, direction))}
                onRemove={() => onChange(removeItem(entries, index))}
              />
            </div>
          </div>
        ))}
        <Button type="button" variant="secondary" size="sm" onClick={() => onChange([...entries, newExperience()])}>
          <Plus aria-hidden />
          Add experience
        </Button>
      </CardContent>
    </Card>
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
  entries,
  onChange,
}: {
  entries: Provenanced<EducationEntry>[];
  onChange: (next: Provenanced<EducationEntry>[]) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Education</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {entries.map((entry, index) => (
          <div key={index} className="flex items-start gap-2 rounded-card border border-border p-3">
            <div className="grid flex-1 gap-2 sm:grid-cols-2">
              <input
                className={FIELD_CLASS}
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
            </div>
            <ReorderControls
              index={index}
              count={entries.length}
              onMove={(direction) => onChange(moveItem(entries, index, direction))}
              onRemove={() => onChange(removeItem(entries, index))}
            />
          </div>
        ))}
        <Button type="button" variant="secondary" size="sm" onClick={() => onChange([...entries, newEducation()])}>
          <Plus aria-hidden />
          Add education
        </Button>
      </CardContent>
    </Card>
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
    <Card>
      <CardHeader>
        <CardTitle>Skills</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {groups.map((group, index) => (
          <div key={index} className="flex items-start gap-2 rounded-card border border-border p-3">
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
            <ReorderControls
              index={index}
              count={groups.length}
              onMove={(direction) => onChange(moveItem(groups, index, direction))}
              onRemove={() => onChange(removeItem(groups, index))}
            />
          </div>
        ))}
        <Button type="button" variant="secondary" size="sm" onClick={() => onChange([...groups, newSkillGroup()])}>
          <Plus aria-hidden />
          Add skill group
        </Button>
      </CardContent>
    </Card>
  );
}

function newProject(): Provenanced<ProjectEntry> {
  return userProvided({ name: "", description: null, bullets: [], technologies: [], dates: null });
}

function ProjectsEditor({
  entries,
  onChange,
}: {
  entries: Provenanced<ProjectEntry>[];
  onChange: (next: Provenanced<ProjectEntry>[]) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Projects</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {entries.map((entry, index) => (
          <div key={index} className="flex items-start gap-2 rounded-card border border-border p-3">
            <div className="flex-1 space-y-2">
              <input
                className={FIELD_CLASS}
                placeholder="Project name"
                value={entry.value.name}
                onChange={(e) =>
                  onChange(
                    updateItem(entries, index, { ...entry, value: { ...entry.value, name: e.target.value } }),
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
            </div>
            <ReorderControls
              index={index}
              count={entries.length}
              onMove={(direction) => onChange(moveItem(entries, index, direction))}
              onRemove={() => onChange(removeItem(entries, index))}
            />
          </div>
        ))}
        <Button type="button" variant="secondary" size="sm" onClick={() => onChange([...entries, newProject()])}>
          <Plus aria-hidden />
          Add project
        </Button>
      </CardContent>
    </Card>
  );
}

function newCertification(): Provenanced<CertificationEntry> {
  return userProvided({ name: "", issuer: null, date: null });
}

function CertificationsEditor({
  entries,
  onChange,
}: {
  entries: Provenanced<CertificationEntry>[];
  onChange: (next: Provenanced<CertificationEntry>[]) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Certifications</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {entries.map((entry, index) => (
          <div key={index} className="flex items-start gap-2 rounded-card border border-border p-3">
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
            <ReorderControls
              index={index}
              count={entries.length}
              onMove={(direction) => onChange(moveItem(entries, index, direction))}
              onRemove={() => onChange(removeItem(entries, index))}
            />
          </div>
        ))}
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={() => onChange([...entries, newCertification()])}
        >
          <Plus aria-hidden />
          Add certification
        </Button>
      </CardContent>
    </Card>
  );
}
