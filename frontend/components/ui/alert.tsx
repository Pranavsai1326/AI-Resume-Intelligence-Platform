import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const alertVariants = cva("rounded-card border p-4 text-sm", {
  variants: {
    variant: {
      info: "border-border bg-surface-muted text-ink",
      warning: "border-warning/40 bg-warning-soft text-ink",
      danger: "border-danger/40 bg-danger-soft text-ink",
    },
  },
  defaultVariants: { variant: "info" },
});

export function Alert({
  className,
  variant,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & VariantProps<typeof alertVariants>) {
  return <div role="alert" className={cn(alertVariants({ variant }), className)} {...props} />;
}

export function AlertTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h4 className={cn("mb-1 font-semibold", className)} {...props} />;
}
