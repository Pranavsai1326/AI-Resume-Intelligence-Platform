"use client";

/*
  Mandatory consent gate (Phase 9B).

  Shown once per browser session, before any resume, job description, or candidate content can
  be entered - not a checkbox buried under the mode-selection buttons, a genuinely separate step
  that has to be explicitly agreed to or declined. Consent lives in plain React state, nothing is
  written to any storage: it is tied to the act of starting a session, not a persisted preference
  (PRIVACY_ARCHITECTURE.md section 4 - nothing here belongs in localStorage, and this isn't
  content that belongs in sessionStorage either). A reload asks again, which is the honest
  behaviour for a tool that promises not to remember you.
*/

import { AlertTriangle, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const CONSENT_POINTS = [
  "No account is created and nothing you upload is written to a permanent database. Your resume, any job description, and anything generated live only in a temporary server session.",
  "That session is deleted automatically after 60 minutes of inactivity, or 8 hours at the outside — whichever comes first. Closing this tab does not delete it immediately; reopening within that window restores it. Use \"End session & delete data\" at any time for immediate, permanent deletion.",
  "By default nothing leaves this application except to that temporary session store. If you use an AI-assisted feature (rewriting, tailoring, cover letters, interview prep, career suggestions), the relevant resume or job text is sent to our AI provider (Google Gemini) to generate that one response — and only then. If no provider is configured, those features report themselves unavailable rather than faking a result.",
];

export function ConsentGate({
  onAgree,
  onDecline,
}: {
  onAgree: () => void;
  onDecline: () => void;
}) {
  return (
    <div className="mx-auto max-w-2xl py-8">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <ShieldCheck aria-hidden className="size-5 text-accent" />
            <CardTitle>Before you continue</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="space-y-5">
          <ul className="space-y-3 text-sm text-ink-muted">
            {CONSENT_POINTS.map((point) => (
              <li key={point} className="flex gap-2.5">
                <span aria-hidden className="mt-2 size-1.5 shrink-0 rounded-full bg-ink-subtle" />
                <span>{point}</span>
              </li>
            ))}
          </ul>

          <div className="flex items-start gap-2.5 rounded-card border border-warning/40 bg-warning-soft p-3 text-sm text-ink">
            <AlertTriangle aria-hidden className="mt-0.5 size-4 shrink-0 text-warning" />
            <p>
              Your data is temporary, not instantly erased on tab close — that&apos;s what lets a
              reload rejoin your work instead of losing it. Deletion happens automatically on the
              schedule above, or immediately if you choose &quot;End session &amp; delete
              data.&quot;
            </p>
          </div>

          <div className="flex flex-wrap gap-3 pt-1">
            <Button onClick={onAgree}>I agree — continue</Button>
            <Button variant="ghost" onClick={onDecline}>
              Decline
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
