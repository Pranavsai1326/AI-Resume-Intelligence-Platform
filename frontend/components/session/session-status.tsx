"use client";

/** Live session indicator: mode, remaining time, and an explicit way to end it now. */

import { Clock, ShieldCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useSessionActions } from "@/components/session/session-provider";
import { formatDuration } from "@/lib/utils";
import { useSessionStore } from "@/stores/session-store";

const WARNING_THRESHOLD_SECONDS = 5 * 60;

export function SessionStatus() {
  const status = useSessionStore((s) => s.status);
  const info = useSessionStore((s) => s.info);
  const secondsRemaining = useSessionStore((s) => s.secondsRemaining);
  const { end } = useSessionActions();

  if (status !== "active" || !info) return null;

  const expiringSoon = secondsRemaining <= WARNING_THRESHOLD_SECONDS;

  return (
    <div className="flex items-center gap-3">
      <Badge variant={expiringSoon ? "warning" : "success"}>
        <ShieldCheck aria-hidden="true" className="size-3.5" />
        <span className="capitalize">{info.mode} session</span>
      </Badge>
      <span
        className="hidden items-center gap-1.5 text-sm text-ink-muted sm:inline-flex"
        aria-live="polite"
      >
        <Clock aria-hidden="true" className="size-3.5" />
        <span>
          <span className="sr-only">Time remaining before this session expires: </span>
          {formatDuration(secondsRemaining)}
        </span>
      </span>
      <Button variant="ghost" size="sm" onClick={() => void end()}>
        End session &amp; delete data
      </Button>
    </div>
  );
}
