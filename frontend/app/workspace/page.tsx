"use client";

import * as React from "react";
import { AlertCircle, Loader2, Search, Users } from "lucide-react";

import { ResumeAnalyzer } from "@/components/analysis/resume-analyzer";
import { AppShell } from "@/components/layout/app-shell";
import { useSessionActions } from "@/components/session/session-provider";
import { Alert, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type ReadyInfo } from "@/lib/api-client";
import { useSessionStore } from "@/stores/session-store";

/*
  Workspace.

  The module list shows honest availability rather than buttons that lead nowhere - a module
  appears as available only when its backend exists (RULE 8: no fake functionality). Upload and
  analysis (Phases 2-3) are real; they render as the interactive flow above the list rather than
  as another "not built yet" card.
*/

interface ModuleCard {
  key: string;
  title: string;
  description: string;
  icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  phase: string;
  available: boolean;
}

// Job matching, tailoring, the resume builder, and career intelligence (Phase 4-6) are real and
// render inline in the upload -> analyze flow above rather than as another "not built yet" card -
// see ResumeAnalyzer / ResumeBuilder / CareerPanel.
const CANDIDATE_MODULES: ModuleCard[] = [];

const RECRUITER_MODULES: ModuleCard[] = [
  {
    key: "screening",
    title: "Bulk screening",
    description: "Upload a job description and a candidate batch for asynchronous processing.",
    icon: Users,
    phase: "Phase 7",
    available: false,
  },
  {
    key: "ranking",
    title: "Ranking and comparison",
    description: "Evidence-backed ranking with a per-candidate breakdown of every score.",
    icon: Search,
    phase: "Phase 7",
    available: false,
  },
];

export default function WorkspacePage() {
  const status = useSessionStore((s) => s.status);
  const info = useSessionStore((s) => s.info);
  const error = useSessionStore((s) => s.error);
  const { start } = useSessionActions();
  const [ready, setReady] = React.useState<ReadyInfo | null>(null);

  React.useEffect(() => {
    if (status !== "active") return;
    const controller = new AbortController();
    api
      .ready(controller.signal)
      .then(setReady)
      .catch(() => setReady(null));
    return () => controller.abort();
  }, [status]);

  if (status === "starting") {
    return (
      <AppShell>
        <div className="space-y-4" aria-busy="true" aria-live="polite">
          <span className="sr-only">Starting your temporary session</span>
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-4 w-96" />
          <div className="grid gap-5 pt-4 md:grid-cols-3">
            <Skeleton className="h-40" />
            <Skeleton className="h-40" />
            <Skeleton className="h-40" />
          </div>
        </div>
      </AppShell>
    );
  }

  if (status !== "active" || !info) {
    return (
      <AppShell>
        <div className="mx-auto max-w-2xl py-8">
          <h1 className="text-2xl font-semibold tracking-tight text-ink">
            Start a temporary session
          </h1>
          <p className="mt-3 text-ink-muted">
            No account is created. The session holds your work in server memory and expires after
            60 minutes of inactivity, or 8 hours at the outside — whichever comes first.
          </p>

          {status === "error" && error ? (
            <Alert variant="danger" className="mt-6">
              <AlertTitle className="flex items-center gap-2">
                <AlertCircle aria-hidden="true" className="size-4" />
                Could not start a session
              </AlertTitle>
              <p className="text-ink-muted">{error}</p>
            </Alert>
          ) : null}

          <div className="mt-8 grid gap-4 sm:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>I am a candidate</CardTitle>
                <CardDescription>
                  Build, analyse, match and tailor your own resume.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button className="w-full" onClick={() => void start("candidate")}>
                  Start candidate session
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>I am a recruiter</CardTitle>
                <CardDescription>
                  Screen and rank a candidate pool against one role.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button variant="secondary" className="w-full" onClick={() => void start("recruiter")}>
                  Start screening session
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>
      </AppShell>
    );
  }

  const modules = info.mode === "recruiter" ? RECRUITER_MODULES : CANDIDATE_MODULES;

  return (
    <AppShell>
      <div className="space-y-8">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">
            {info.mode === "recruiter" ? "Screening workspace" : "Candidate workspace"}
          </h1>
          <p className="mt-2 text-ink-muted">
            Your session is active. Anything you add stays here until it expires, then it is
            removed from the server.
          </p>
        </div>

        <Alert>
          <AlertTitle>Phase 6 of the build is live</AlertTitle>
          <p className="text-ink-muted">
            Upload, resume analysis, job matching, the resume builder, AI-assisted tailoring,
            export, cover letters, interview prep and learning priorities all work end to end
            below. Anything not built yet is listed honestly with its real status — none of it
            will show you a fabricated result.
          </p>
        </Alert>

        {info.mode === "candidate" ? (
          <section aria-labelledby="analyzer-heading">
            <h2 id="analyzer-heading" className="text-lg font-semibold text-ink">
              Analyze your resume
            </h2>
            <p className="mt-2 text-sm text-ink-muted">
              Upload a resume to see how it reads to an ATS parser and a human reviewer, with
              every score explained.
            </p>
            <div className="mt-4">
              <ResumeAnalyzer sessionId={info.session_id} />
            </div>
          </section>
        ) : null}

        {modules.length > 0 ? (
        <section aria-labelledby="modules-heading">
          <h2 id="modules-heading" className="text-lg font-semibold text-ink">
            {info.mode === "candidate" ? "More modules" : "Modules"}
          </h2>
          <div className="mt-4 grid gap-5 md:grid-cols-3">
            {modules.map((module) => (
              <Card key={module.key} className="flex flex-col">
                <CardHeader>
                  <module.icon aria-hidden className="size-5 text-ink-subtle" />
                  <CardTitle>{module.title}</CardTitle>
                  <CardDescription>{module.description}</CardDescription>
                </CardHeader>
                <CardContent className="mt-auto">
                  {module.available ? (
                    <Badge variant="success">Available</Badge>
                  ) : (
                    <Badge variant="neutral">Not built yet — {module.phase}</Badge>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </section>
        ) : null}

        <section aria-labelledby="capabilities-heading">
          <h2 id="capabilities-heading" className="text-lg font-semibold text-ink">
            Server capabilities
          </h2>
          <p className="mt-2 text-sm text-ink-muted">
            Reported by the backend, so the interface never offers something this deployment
            cannot actually do.
          </p>
          {ready ? (
            <ul className="mt-4 flex flex-wrap gap-2">
              {Object.entries(ready.capabilities).map(([name, enabled]) => (
                <li key={name}>
                  <Badge variant={enabled ? "success" : "neutral"}>
                    {name.replace(/_/g, " ")}: {enabled ? "available" : "not configured"}
                  </Badge>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-4 flex items-center gap-2 text-sm text-ink-subtle">
              <Loader2 aria-hidden="true" className="size-4 animate-spin" />
              Checking capabilities…
            </p>
          )}
        </section>
      </div>
    </AppShell>
  );
}
