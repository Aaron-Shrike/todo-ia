// phrase-ui spec, "Duplicate alert": the similarity score MUST be shown as a
// whole percentage FLOORED from the 4-decimal score, "computed on integer
// basis points to avoid float error" — never rounded, so the percentage can
// never overstate similarity.
//
// The score arriving here is already rounded to 4 decimals by the domain's
// `SimilarityPolicy` (`ROUNDING_DECIMALS`), so `score * 10000` SHOULD be an
// exact integer, but IEEE 754 float multiplication can still land a hair off
// (e.g. `0.995 * 100` is `99.49999999999999`, not `99.5`) — flooring that
// directly would UNDERSTATE the percentage by one point on exact boundaries.
// `Math.round(score * 10000)` recovers the true basis-point integer first;
// dividing by 100 and flooring THAT is what actually floors the percentage,
// never rounds it up.
export function floorPercent(score: number): number {
  const basisPoints = Math.round(score * 10000);
  return Math.floor(basisPoints / 100);
}
