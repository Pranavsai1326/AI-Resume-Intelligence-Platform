"use client";

import * as React from "react";

import { emptyDateRange } from "@/lib/resume-edit";
import type { DateRange } from "@/lib/api-client";

/*
  Start/end month-year + "Present" toggle (Phase 9D spec section 4). `DateRange.start`/`end` are
  free-text on the backend (extraction can't always normalise a date to a strict month/year), so
  this editor writes plain text into them via `type="month"` inputs for the common case while
  still round-tripping whatever text extraction produced if the user never touches the field.
*/

const FIELD_CLASS =
  "rounded-card border border-border-strong bg-surface px-2 py-1.5 text-sm text-ink focus-visible:outline-none";

function toMonthInput(value: string | null): string {
  if (!value) return "";
  const match = /^(\d{4})-(\d{2})/.exec(value);
  return match ? `${match[1]}-${match[2]}` : "";
}

export function DateRangeEditor({
  dates,
  onChange,
}: {
  dates: DateRange | null;
  onChange: (next: DateRange | null) => void;
}) {
  const value = dates ?? emptyDateRange();

  const update = (patch: Partial<DateRange>) => {
    const next = { ...value, ...patch };
    next.raw = [next.start ?? "", next.is_current ? "Present" : (next.end ?? "")]
      .filter(Boolean)
      .join(" – ");
    onChange(next);
  };

  return (
    <div className="flex flex-wrap items-center gap-2 text-sm text-ink-muted">
      <input
        type="month"
        aria-label="Start date"
        className={FIELD_CLASS}
        value={toMonthInput(value.start)}
        onChange={(e) => update({ start: e.target.value || null })}
      />
      <span aria-hidden>→</span>
      <input
        type="month"
        aria-label="End date"
        className={FIELD_CLASS}
        value={toMonthInput(value.end)}
        disabled={value.is_current}
        onChange={(e) => update({ end: e.target.value || null })}
      />
      <label className="flex items-center gap-1.5 text-xs">
        <input
          type="checkbox"
          checked={value.is_current}
          onChange={(e) => update({ is_current: e.target.checked, end: e.target.checked ? null : value.end })}
        />
        Present
      </label>
    </div>
  );
}
