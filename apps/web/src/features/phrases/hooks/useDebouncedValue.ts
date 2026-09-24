"use client";

import { useEffect, useState } from "react";

/**
 * Returns `value`, updated only after it has stayed unchanged for `delayMs`
 * (phrase-ui spec, "Filter controls over the saved list": "the list
 * refetches only after the user stops typing for a few hundred
 * milliseconds, not on every keystroke"). Debounces, not throttles: every
 * change resets the pending timer, so only the value that survives
 * unchanged for the full delay is ever committed.
 */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}
