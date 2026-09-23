/** Small inline SVG icon set for this page only — no icon-library dependency
 * (same "extra dep for no gain at this size" precedent as `lib/api/client.ts`'s
 * "MSW rejected" comment). Outline style, 24x24 viewBox, stroke-based so a
 * single `currentColor` controls fill. Every usage in `page.tsx` pairs an
 * icon with adjacent visible text, so each one is `aria-hidden` here rather
 * than carrying its own accessible name. */

import type { SVGProps } from "react";

function Base(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    />
  );
}

export function SparkleIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Base {...props}>
      <path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18" />
      <circle cx="12" cy="12" r="3" />
    </Base>
  );
}

export function LayersIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Base {...props}>
      <path d="m12 3 9 5-9 5-9-5 9-5Z" />
      <path d="m3 13 9 5 9-5" />
    </Base>
  );
}

export function ShieldCheckIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Base {...props}>
      <path d="M12 3 4 6v6c0 4.5 3.4 7.7 8 9 4.6-1.3 8-4.5 8-9V6l-8-3Z" />
      <path d="m9 12 2 2 4-4" />
    </Base>
  );
}

export function CpuIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Base {...props}>
      <rect x="6" y="6" width="12" height="12" rx="1.5" />
      <path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3" />
    </Base>
  );
}

export function DatabaseIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Base {...props}>
      <ellipse cx="12" cy="5.5" rx="7.5" ry="2.5" />
      <path d="M4.5 5.5V18c0 1.4 3.4 2.5 7.5 2.5s7.5-1.1 7.5-2.5V5.5" />
      <path d="M4.5 12c0 1.4 3.4 2.5 7.5 2.5s7.5-1.1 7.5-2.5" />
    </Base>
  );
}

export function HexagonIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Base {...props}>
      <path d="m12 2 8 4.5v11L12 22l-8-4.5v-11L12 2Z" />
      <path d="M12 8v8M8.5 6l3.5 2 3.5-2M8.5 18l3.5-2 3.5 2" />
    </Base>
  );
}

export function GithubIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Base {...props} strokeWidth={1.5}>
      <path d="M9 19c-4.3 1.4-4.3-2.5-6-3m12 5v-3.5c0-1 .1-1.4-.5-2 2.8-.3 5.5-1.4 5.5-6a4.6 4.6 0 0 0-1.3-3.2 4.2 4.2 0 0 0-.1-3.2s-1.1-.3-3.5 1.3a12.3 12.3 0 0 0-6.2 0C6.6 2.8 5.5 3.1 5.5 3.1a4.2 4.2 0 0 0-.1 3.2A4.6 4.6 0 0 0 4.1 9.5c0 4.6 2.7 5.7 5.5 6-.6.6-.6 1.2-.5 2V21" />
    </Base>
  );
}

export function ArrowRightIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Base {...props}>
      <path d="M5 12h14M13 6l6 6-6 6" />
    </Base>
  );
}
