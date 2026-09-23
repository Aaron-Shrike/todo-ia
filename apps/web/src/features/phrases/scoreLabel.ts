import { copy } from "@/i18n/copy.es";

import { floorPercent } from "./percent";

/**
 * `copy.duplicate.score`'s `{percent}` template, filled in — the one
 * interpolated copy string in the phrase feature. Shared by `DuplicateAlert`
 * (match list) and `PhraseList` (saved-item similarity), both of which need
 * "Similitud: NN%".
 */
export function scoreLabel(score: number): string {
  return copy.duplicate.score.replace("{percent}", String(floorPercent(score)));
}
