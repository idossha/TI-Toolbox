// @vitest-environment jsdom
/**
 * `<Subscripted>` draws a field label `X_{sub}` as ONE inline element (2026-10-30): inside a flex
 * label with a gap (the Output fields checkboxes) a bare fragment's text and `<sub>` became two
 * flex items, rendered "TI  max". Expected values are the registry labels written here.
 */
import { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it } from "vitest";
import { plainLabel, Subscripted } from "../../src/renderer/ui/Subscripted";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function render(text: string): HTMLElement {
  const host = document.createElement("label");
  host.style.display = "flex";
  act(() => createRoot(host).render(<Subscripted text={text} />));
  return host;
}

describe("Subscripted", () => {
  it.each([["TI_{max}", "TI", "max"], ["HF_{peak}", "HF", "peak"], ["p_{HF}", "p", "HF"]])(
    "renders %s as a single child element",
    (text, base, sub) => {
      const host = render(text);
      expect(host.childNodes).toHaveLength(1);
      const only = host.firstChild as HTMLElement;
      expect(only.tagName).toBe("SPAN");
      expect(only.textContent).toBe(base + sub);
      expect(only.querySelector("sub")?.textContent).toBe(sub);
    },
  );

  it("leaves text without a subscript as plain text, and plainLabel drops the braces", () => {
    expect(render("Auto").innerHTML).toBe("Auto");
    expect(plainLabel("Auto (HF_{peak})")).toBe("Auto (HF_peak)");
  });
});
