/**
 * Pure helpers for editing a `Resume` immutably in the builder.
 *
 * Every function returns a new array/object rather than mutating its input, matching the
 * backend's own `apply_proposals` convention (app/ai/tailor.py) - the builder always replaces
 * state wholesale via `setResume(next)`, never patches in place.
 */

import type { Provenance, Provenanced, Resume } from "@/lib/api-client";

export function userProvided<T>(value: T): Provenanced<T> {
  return { value, provenance: userProvidedProvenance() };
}

export function userProvidedProvenance(): Provenance {
  return { kind: "user_provided", confidence: null, source: null };
}

export function moveItem<T>(items: T[], index: number, direction: -1 | 1): T[] {
  const target = index + direction;
  if (target < 0 || target >= items.length) return items;
  const next = items.slice();
  const [item] = next.splice(index, 1) as [T];
  next.splice(target, 0, item);
  return next;
}

export function removeItem<T>(items: T[], index: number): T[] {
  return items.filter((_, i) => i !== index);
}

export function updateItem<T>(items: T[], index: number, next: T): T[] {
  return items.map((item, i) => (i === index ? next : item));
}

export function emptyResume(): Resume {
  return {
    contact: { full_name: null, email: null, phone: null, location: null, links: [] },
    summary: null,
    experience: [],
    education: [],
    skills: [],
    projects: [],
    certifications: [],
    custom_sections: [],
  };
}
