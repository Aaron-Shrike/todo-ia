import { fileURLToPath } from "node:url";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Standalone output keeps the runtime Docker stage to a `node_modules`-free
  // `server.js` plus only the traced dependencies (see apps/web/Dockerfile).
  output: "standalone",
  // Pins Turbopack's workspace root to this package explicitly. Without it,
  // Turbopack walks up from `apps/web` looking for a lockfile and — on a
  // reviewer machine with an unrelated `~/package-lock.json` — can pick that
  // one up instead, which only produces a (harmless but noisy) warning here
  // since this repo has no other lockfile above `apps/web`, but is worth
  // pinning rather than relying on that.
  turbopack: {
    root: fileURLToPath(new URL(".", import.meta.url)),
  },
  // Next.js 16 dropped the built-in `eslint` build-step config key (linting
  // during `next build` is gone; `next lint` is deprecated in favor of
  // running ESLint directly) — confirmed by `npm run build` warning of an
  // "Unrecognized key(s)" when this key was present. No ESLint ruleset is
  // wired yet (openspec/config.yaml: "no ruleset configured yet" — Unit 0),
  // so there is nothing to configure here for this unit.
};

export default nextConfig;
