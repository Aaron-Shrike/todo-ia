import { copy } from "@/i18n/copy.es";

function fillTemplate(template: string, loaded: number, total: number): string {
  return template.replace("{loaded}", String(loaded)).replace("{total}", String(total));
}

/** `copy.list.counter`'s `{loaded}/{total}` template, filled in — the saved-list counter. */
export function counterLabel(loaded: number, total: number): string {
  return fillTemplate(copy.list.counter, loaded, total);
}

/** `copy.duplicate.matchesCounter`'s `{loaded}/{total}` template, filled in — the duplicate alert's match-list counter. */
export function matchesCounterLabel(loaded: number, total: number): string {
  return fillTemplate(copy.duplicate.matchesCounter, loaded, total);
}
