import { Card, CardContent } from "@/components/ui/card";
import type { Resume } from "@/lib/api-client";

/** A live, read-only rendering of the resume as it's edited - mirrors the structure (not the
 * exact typography) of the backend's HTML export template (app/export/html_template.py). */
export function ResumePreview({ resume }: { resume: Resume }) {
  const name = resume.contact.full_name?.value || "Your name";
  const contactBits = [
    resume.contact.email?.value,
    resume.contact.phone?.value,
    resume.contact.location?.value,
    ...resume.contact.links.map((l) => l.value),
  ].filter((bit): bit is string => Boolean(bit));

  return (
    <Card>
      <CardContent className="max-h-[70vh] space-y-4 overflow-y-auto p-6 text-sm">
        <div>
          <h2 className="text-xl font-semibold text-ink">{name}</h2>
          {contactBits.length > 0 ? (
            <p className="text-xs text-ink-subtle">{contactBits.join(" · ")}</p>
          ) : null}
        </div>

        {resume.summary?.value ? <p className="text-ink-muted">{resume.summary.value}</p> : null}

        {resume.experience.length > 0 ? (
          <PreviewSection title="Experience">
            {resume.experience.map((item, index) => (
              <div key={index} className="space-y-1">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-medium text-ink">{item.value.title}</span>
                  <span className="text-xs text-ink-subtle">{item.value.dates?.raw}</span>
                </div>
                <p className="text-xs text-ink-subtle italic">{item.value.organization}</p>
                {item.value.bullets.length > 0 ? (
                  <ul className="ml-4 list-disc space-y-0.5 text-ink-muted">
                    {item.value.bullets.map((bullet, bulletIndex) => (
                      <li key={bulletIndex}>{bullet}</li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ))}
          </PreviewSection>
        ) : null}

        {resume.education.length > 0 ? (
          <PreviewSection title="Education">
            {resume.education.map((item, index) => (
              <div key={index}>
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-medium text-ink">{item.value.institution}</span>
                  <span className="text-xs text-ink-subtle">{item.value.dates?.raw}</span>
                </div>
                {item.value.degree ? (
                  <p className="text-xs text-ink-subtle">{item.value.degree}</p>
                ) : null}
              </div>
            ))}
          </PreviewSection>
        ) : null}

        {resume.skills.length > 0 ? (
          <PreviewSection title="Skills">
            {resume.skills.map((item, index) => (
              <p key={index} className="text-ink-muted">
                {item.value.category ? (
                  <span className="font-medium text-ink">{item.value.category}: </span>
                ) : null}
                {item.value.skills.join(", ")}
              </p>
            ))}
          </PreviewSection>
        ) : null}

        {resume.projects.length > 0 ? (
          <PreviewSection title="Projects">
            {resume.projects.map((item, index) => (
              <div key={index}>
                <p className="font-medium text-ink">
                  {item.value.name}
                  {item.value.technologies.length > 0
                    ? ` (${item.value.technologies.join(", ")})`
                    : ""}
                </p>
                {item.value.bullets.length > 0 ? (
                  <ul className="ml-4 list-disc space-y-0.5 text-ink-muted">
                    {item.value.bullets.map((bullet, bulletIndex) => (
                      <li key={bulletIndex}>{bullet}</li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ))}
          </PreviewSection>
        ) : null}

        {resume.certifications.length > 0 ? (
          <PreviewSection title="Certifications">
            <ul className="ml-4 list-disc space-y-0.5 text-ink-muted">
              {resume.certifications.map((item, index) => (
                <li key={index}>
                  {[item.value.name, item.value.issuer, item.value.date]
                    .filter(Boolean)
                    .join(" — ")}
                </li>
              ))}
            </ul>
          </PreviewSection>
        ) : null}
      </CardContent>
    </Card>
  );
}

function PreviewSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="border-b border-border pb-1 text-xs font-semibold tracking-wide text-ink-subtle uppercase">
        {title}
      </h3>
      <div className="mt-2 space-y-3">{children}</div>
    </section>
  );
}
