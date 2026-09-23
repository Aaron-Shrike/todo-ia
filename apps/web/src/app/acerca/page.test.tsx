import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import AcercaPage from "./page";

describe("AcercaPage", () => {
  it("renders the hero heading, a link back to the app and the feature grid", () => {
    render(<AcercaPage />);

    expect(
      screen.getByRole("heading", { level: 1, name: /lista de frases que sabe/i }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /abrir la app/i }).length).toBeGreaterThan(0);
    expect(
      screen.getByRole("heading", { level: 2, name: /qué hace/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 3, name: /detecta duplicados por significado/i }),
    ).toBeInTheDocument();
  });
});
