// Placeholder Server Component (Unit 10 scaffold).
//
// The real first paint — `export const dynamic = "force-dynamic"` plus a
// `fetch(..., { cache: "no-store" })` call against `GET /phrases`, feeding
// the client `PhraseList` its `initialItems` — is wired in Unit 13 (design.md
// "First paint and list refresh"). This unit only proves the App Router
// renders through the Docker build and `next build`.
export default function HomePage() {
  return (
    <main>
      <h1>Lista de frases</h1>
      <p>La interfaz de validación de frases se implementa en unidades posteriores.</p>
    </main>
  );
}
