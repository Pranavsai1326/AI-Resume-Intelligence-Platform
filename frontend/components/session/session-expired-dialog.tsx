"use client";

/**
 * Shown when the server reports the session is gone.
 *
 * States plainly that the data was removed rather than implying it can be recovered - there is
 * nothing to recover, by design.
 */

import * as Dialog from "@radix-ui/react-dialog";
import { RotateCcw } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { useSessionActions } from "@/components/session/session-provider";
import { useSessionStore } from "@/stores/session-store";

export function SessionExpiredDialog() {
  const status = useSessionStore((s) => s.status);
  const { restart } = useSessionActions();
  const [restarting, setRestarting] = React.useState(false);

  const onRestart = async () => {
    setRestarting(true);
    await restart();
    setRestarting(false);
  };

  return (
    <Dialog.Root open={status === "expired"}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content
          className="fixed left-1/2 top-1/2 w-[min(28rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-card border border-border bg-surface p-6 shadow-lg"
          onEscapeKeyDown={(event) => event.preventDefault()}
          onInteractOutside={(event) => event.preventDefault()}
        >
          <Dialog.Title className="text-lg font-semibold text-ink">
            Your session has ended
          </Dialog.Title>
          <Dialog.Description className="mt-2 text-sm text-ink-muted">
            Temporary sessions expire after a period of inactivity, and everything they held has
            been removed from the server. Nothing was saved to an account, so there is nothing to
            restore.
          </Dialog.Description>
          <div className="mt-6 flex justify-end gap-2">
            <Button variant="secondary" asChild>
              <Link href="/">Back to home</Link>
            </Button>
            <Button onClick={() => void onRestart()} disabled={restarting}>
              <RotateCcw aria-hidden="true" />
              {restarting ? "Starting..." : "Start a new session"}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
