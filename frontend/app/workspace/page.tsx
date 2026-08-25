"use client";

import * as React from "react";
import { AlertCircle } from "lucide-react";
import { useRouter } from "next/navigation";

import { AppShell } from "@/components/layout/app-shell";
import { CandidateWorkspace } from "@/components/workspace/candidate-workspace";
import { ScreeningWorkspace } from "@/components/screening/screening-workspace";
import { ConsentGate } from "@/components/session/consent-gate";
import { useSessionActions } from "@/components/session/session-provider";
import { Alert, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useSessionStore } from "@/stores/session-store";

export default function WorkspacePage() {
  const status = useSessionStore((s) => s.status);
  const info = useSessionStore((s) => s.info);
  const error = useSessionStore((s) => s.error);
  const { start } = useSessionActions();
  const router = useRouter();
  // Plain component state, nothing persisted (Phase 9B) - consent is tied to the act of
  // starting a session in this page load, not a saved preference. A reload asks again.
  const [consented, setConsented] = React.useState(false);

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
    if (!consented) {
      return (
        <AppShell>
          <ConsentGate onAgree={() => setConsented(true)} onDecline={() => router.push("/")} />
        </AppShell>
      );
    }

    return (
      <AppShell>
        <div className="mx-auto max-w-2xl py-8">
          <h1 className="text-[length:var(--text-h1)] font-semibold tracking-tight text-ink">
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

  return (
    <AppShell>
      <div className="space-y-8">
        {info.mode === "candidate" ? <CandidateWorkspace sessionId={info.session_id} /> : null}
        {info.mode === "recruiter" ? <ScreeningWorkspace sessionId={info.session_id} /> : null}
      </div>
    </AppShell>
  );
}
