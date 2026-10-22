// @vitest-environment jsdom
/**
 * The Explode toggle names the action a click performs: "Explode" collapsed, "Collapse" exploded.
 * One component serves every scene pane that offers Explode (MNI only: `explodeOffered`, tested in
 * scene-explode.test.ts; a subject's own head has no button), so this is the whole contract.
 */
import React, { act, useState } from "react";
import { createRoot } from "react-dom/client";
import { expect, it } from "vitest";
import { ExplodeButton } from "../../src/renderer/pages/_shared/scene/ExplodeButton";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function Harness() {
  const [exploded, setExploded] = useState(false);
  return <ExplodeButton exploded={exploded} onToggle={() => setExploded((value) => !value)} />;
}

it("flips its label and accessible name with the state, and back, without aria-pressed", () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  try {
    act(() => root.render(<Harness />));
    const button = host.querySelector("button")!;
    expect(button.textContent).toBe("Explode");
    expect(button.getAttribute("aria-pressed")).toBeNull(); // the label is the state; "Collapse, pressed" would contradict itself
    expect(button.getAttribute("title")).toMatch(/^Pull the atlas regions apart/);

    act(() => button.click());
    expect(button.textContent).toBe("Collapse");
    expect(button.getAttribute("aria-pressed")).toBeNull();
    expect(button.getAttribute("title")).toMatch(/^Bring the atlas regions back together/);

    act(() => button.click());
    expect(button.textContent).toBe("Explode");
  } finally {
    act(() => root.unmount());
    host.remove();
  }
});
