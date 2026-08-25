/**
 * Typed mirror of the CSS custom properties declared in `app/globals.css`.
 *
 * Components that need a token in a computed/inline context (rather than a Tailwind class) read
 * from here instead of re-declaring the value, so the type scale and spacing rhythm stay defined
 * in exactly one place.
 */

export const textScale = {
  display: "var(--text-display)",
  h1: "var(--text-h1)",
  h2: "var(--text-h2)",
  body: "var(--text-body)",
  small: "var(--text-small)",
  micro: "var(--text-micro)",
} as const;

export const spacing = {
  section: "var(--space-section)",
  card: "var(--space-card)",
  inline: "var(--space-inline)",
} as const;

export type TextScaleToken = keyof typeof textScale;
export type SpacingToken = keyof typeof spacing;

/** Tailwind utility classes for the same rhythm, for the common case of static class names. */
export const spacingClass = {
  section: "space-y-10",
  card: "space-y-4",
  inline: "gap-2",
} as const;
