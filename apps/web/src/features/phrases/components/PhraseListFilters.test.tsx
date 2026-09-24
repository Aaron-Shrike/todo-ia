// phrase-ui spec, "Filter controls over the saved list" — presentational
// component, same "MSW rejected"/hand-rolled-fake convention as the rest of
// this feature: no live state here, just callbacks asserted against.
import type { ComponentProps } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { copy } from "@/i18n/copy.es";

import { PhraseListFilters } from "./PhraseListFilters";

function renderFilters(overrides: Partial<ComponentProps<typeof PhraseListFilters>> = {}) {
  const onStatusChange = vi.fn();
  const onTextChange = vi.fn();
  const onMinScoreChange = vi.fn();
  const utils = render(
    <PhraseListFilters
      status=""
      onStatusChange={onStatusChange}
      text=""
      onTextChange={onTextChange}
      minScore={null}
      onMinScoreChange={onMinScoreChange}
      {...overrides}
    />,
  );
  return { ...utils, onStatusChange, onTextChange, onMinScoreChange };
}

describe("PhraseListFilters", () => {
  it("renders the status select first, before the text and min-score controls (most prominent control)", () => {
    const { container } = renderFilters();
    const controls = container.querySelectorAll("select, input");
    expect(controls[0].tagName).toBe("SELECT");
  });

  it("status select offers Todas / Única / Duplicado confirmado, defaulting to Todas", () => {
    renderFilters();
    const select = screen.getByLabelText(copy.filters.statusLabel) as HTMLSelectElement;
    const optionLabels = Array.from(select.options).map((option) => option.textContent);
    expect(optionLabels).toEqual([
      copy.filters.statusAll,
      copy.badge.unique,
      copy.badge.duplicate_confirmed,
    ]);
    expect(select).toHaveValue("");
  });

  it("calls onStatusChange with the selected value", () => {
    const { onStatusChange } = renderFilters();
    fireEvent.change(screen.getByLabelText(copy.filters.statusLabel), {
      target: { value: "duplicate_confirmed" },
    });
    expect(onStatusChange).toHaveBeenCalledWith("duplicate_confirmed");
  });

  it("calls onTextChange with the raw typed value and caps the text input at maxLength", () => {
    const { onTextChange } = renderFilters({ maxLength: 42 });
    const input = screen.getByLabelText(copy.filters.textLabel);
    expect(input).toHaveAttribute("maxLength", "42");

    fireEvent.change(input, { target: { value: "leche" } });

    expect(onTextChange).toHaveBeenCalledWith("leche");
  });

  it("shows the placeholder from the copy module", () => {
    renderFilters();
    expect(screen.getByPlaceholderText(copy.filters.textPlaceholder)).toBeInTheDocument();
  });

  it("min-score input sends percent/100 as a fraction", () => {
    const { onMinScoreChange } = renderFilters();
    fireEvent.change(screen.getByLabelText(copy.filters.minScoreLabel), {
      target: { value: "85" },
    });
    expect(onMinScoreChange).toHaveBeenCalledWith(0.85);
  });

  it("clearing the min-score input calls onMinScoreChange with null", () => {
    const { onMinScoreChange } = renderFilters({ minScore: 0.5 });
    fireEvent.change(screen.getByLabelText(copy.filters.minScoreLabel), {
      target: { value: "" },
    });
    expect(onMinScoreChange).toHaveBeenCalledWith(null);
  });

  it("displays an active minScore as a rounded percent", () => {
    renderFilters({ minScore: 0.853 });
    const input = screen.getByLabelText(copy.filters.minScoreLabel) as HTMLInputElement;
    expect(input.value).toBe("85");
  });

  it("min-score input has percent bounds [0, 100] with step 1", () => {
    renderFilters();
    const input = screen.getByLabelText(copy.filters.minScoreLabel);
    expect(input).toHaveAttribute("type", "number");
    expect(input).toHaveAttribute("min", "0");
    expect(input).toHaveAttribute("max", "100");
    expect(input).toHaveAttribute("step", "1");
  });
});
