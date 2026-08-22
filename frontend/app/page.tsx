import Link from "next/link";
import { ArrowRight, FileSearch, ShieldCheck, Users } from "lucide-react";

import { SiteHeader } from "@/components/layout/site-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

/*
  Landing page.

  No invented statistics, no testimonials, no logo wall, no "trusted by" claims. The product is
  in early development and the page says what is actually built. Marketing copy that outruns the
  implementation would be the first fake thing in the codebase.
*/

const PRIVACY_POINTS = [
  {
    title: "No account, ever",
    body: "No signup, no password, no email. Open the site and start working immediately.",
  },
  {
    title: "Processed in a temporary session",
    body: "Your resume lives in a short-lived server session. There is no user table and no resume database to store it in.",
  },
  {
    title: "Removed automatically",
    body: "Sessions expire after 60 minutes of inactivity, and 8 hours at the outside. Expiry is enforced by the server, not by your browser.",
  },
];

const CANDIDATE_STEPS = [
  "Upload or build a resume",
  "Analyse structure, ATS compatibility and content quality",
  "Add a job description and see an explained match score",
  "Tailor, prepare for interviews, and export",
];

const RECRUITER_STEPS = [
  "Start a screening session with a job description",
  "Upload a batch of candidate resumes",
  "Rank candidates against the actual requirements",
  "Compare, shortlist and export a report",
];

export default function LandingPage() {
  return (
    <div className="flex min-h-dvh flex-col">
      <SiteHeader />

      <main id="main" className="flex-1">
        <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-24">
          <p className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1 text-xs font-medium text-ink-muted">
            <ShieldCheck aria-hidden="true" className="size-3.5" />
            Accountless and zero-persistence by design
          </p>

          <h1 className="mt-6 max-w-3xl text-4xl font-semibold tracking-tight text-ink sm:text-5xl">
            Resume intelligence that forgets you on purpose.
          </h1>

          <p className="mt-5 max-w-2xl text-lg text-ink-muted">
            Analyse a resume, match it against a job description, and screen a candidate pool —
            without creating an account and without leaving your data behind. Everything runs in a
            temporary session that the server deletes on its own schedule.
          </p>

          <div className="mt-8 flex flex-wrap gap-3">
            <Button size="lg" asChild>
              <Link href="/workspace">
                Open the workspace
                <ArrowRight aria-hidden="true" />
              </Link>
            </Button>
          </div>

          <p className="mt-4 text-sm text-ink-subtle">
            No signup. No credit card. Nothing to delete afterwards.
          </p>
        </section>

        <section
          aria-labelledby="privacy-heading"
          className="border-y border-border bg-surface"
        >
          <div className="mx-auto max-w-6xl px-4 py-14 sm:px-6">
            <h2 id="privacy-heading" className="text-2xl font-semibold tracking-tight text-ink">
              How the privacy model actually works
            </h2>
            <p className="mt-3 max-w-3xl text-ink-muted">
              Most tools promise privacy in a policy document. Here it is a property of the
              architecture: there is no database of users, resumes or candidates for your data to
              be written into.
            </p>

            <dl className="mt-8 grid gap-6 sm:grid-cols-3">
              {PRIVACY_POINTS.map((point) => (
                <div key={point.title}>
                  <dt className="font-medium text-ink">{point.title}</dt>
                  <dd className="mt-2 text-sm leading-relaxed text-ink-muted">{point.body}</dd>
                </div>
              ))}
            </dl>

            <div className="mt-10 rounded-card border border-border bg-canvas p-5">
              <h3 className="text-sm font-semibold text-ink">
                What we do not claim
              </h3>
              <p className="mt-2 max-w-3xl text-sm leading-relaxed text-ink-muted">
                We do not claim your data is deleted the instant you close the tab. Browsers do not
                guarantee that any code runs on a crash, a forced quit or a lost connection. When
                you close a tab we make a best-effort request to end the session, but deletion is
                guaranteed by three server-side mechanisms instead: session expiry, a periodic
                cleanup sweep, and a purge on server start.
              </p>
            </div>
          </div>
        </section>

        <section aria-labelledby="flows-heading" className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
          <h2 id="flows-heading" className="text-2xl font-semibold tracking-tight text-ink">
            One system, two workflows
          </h2>
          <p className="mt-3 max-w-3xl text-ink-muted">
            Not a collection of separate tools — each step reuses what the previous one produced,
            inside the same temporary session.
          </p>

          <div className="mt-8 grid gap-5 md:grid-cols-2">
            <Card>
              <CardHeader>
                <FileSearch aria-hidden="true" className="size-5 text-accent" />
                <CardTitle>For candidates</CardTitle>
                <CardDescription>
                  Understand how a resume reads to software and to a human, then improve it.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ol className="space-y-2 text-sm text-ink-muted">
                  {CANDIDATE_STEPS.map((step, index) => (
                    <li key={step} className="flex gap-3">
                      <span
                        aria-hidden="true"
                        className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full bg-surface-muted text-xs font-medium text-ink"
                      >
                        {index + 1}
                      </span>
                      {step}
                    </li>
                  ))}
                </ol>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <Users aria-hidden="true" className="size-5 text-accent" />
                <CardTitle>For recruiters</CardTitle>
                <CardDescription>
                  Screen a candidate pool with evidence for every ranking decision.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ol className="space-y-2 text-sm text-ink-muted">
                  {RECRUITER_STEPS.map((step, index) => (
                    <li key={step} className="flex gap-3">
                      <span
                        aria-hidden="true"
                        className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full bg-surface-muted text-xs font-medium text-ink"
                      >
                        {index + 1}
                      </span>
                      {step}
                    </li>
                  ))}
                </ol>
              </CardContent>
            </Card>
          </div>

          <p className="mt-8 text-sm text-ink-subtle">
            Candidate ranking uses job-relevant evidence only — skills, experience, education,
            certifications and projects. Protected attributes are removed before scoring. This
            reduces bias; it does not eliminate it, and we will not claim otherwise.
          </p>
        </section>
      </main>

      <footer className="border-t border-border bg-surface">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-6 text-xs text-ink-subtle sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <span>Resume Intelligence — accountless, zero-persistence resume tooling.</span>
          <span>In active development. Features appear here only once they genuinely work.</span>
        </div>
      </footer>
    </div>
  );
}
