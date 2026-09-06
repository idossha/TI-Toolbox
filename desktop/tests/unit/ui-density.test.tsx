// @vitest-environment jsdom
/**
 * The v2 density primitives that carry logic rather than only CSS: `Field`'s row shapes and
 * changed-marking, `FormSection`'s collapse / summary / force-open safety rule, `PageLayout`'s
 * variants and header suppression, `SegmentedControl`'s never-empty guarantee, and the
 * empty/loading/failed trio.
 *
 * jsdom computes no layout, so the 28px numbers are asserted as CSS in `cssRules.test.ts` and
 * measured for real by the Gallery's density ruler. What is asserted here is behaviour and the
 * class contract a page actually gets.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ActionBar, StatusBar, StatusCell, RefetchBar } from "../../src/renderer/ui/Chrome";
import { changedFields, Field, TextInput, useChangedFields } from "../../src/renderer/ui/Field";
import { EmptyState, InlineError, Skeleton } from "../../src/renderer/ui/Feedback";
import { FormSection, PageLayout } from "../../src/renderer/ui/Layout";
import { SegmentedControl } from "../../src/renderer/ui/SegmentedControl";

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});
function render(el: React.ReactElement) {
  act(() => root.render(el));
}
function click(el: Element) {
  act(() => {
    (el as HTMLElement).click();
  });
}

describe("Field — row shapes", () => {
  it("defaults to the label-left row: no layout class, control wrapped in .field-control", () => {
    render(
      <Field label="Goal">
        <TextInput readOnly value="mean" />
      </Field>,
    );
    const field = container.querySelector(".field")!;
    expect(field.className).not.toContain("field-stacked");
    expect(field.className).not.toContain("field-full-bleed");
    expect(field.querySelector(".field-control > input")).not.toBeNull();
  });

  it('layout="stacked" and fullBleed are the two escapes, and they are independent', () => {
    render(
      <Field label="Notes" layout="stacked">
        <TextInput readOnly value="" />
      </Field>,
    );
    expect(container.querySelector(".field")!.className).toContain("field-stacked");

    render(
      <Field label="Pairs" fullBleed>
        <TextInput readOnly value="" />
      </Field>,
    );
    expect(container.querySelector(".field")!.className).toContain("field-full-bleed");
  });

  it("help is an (i) popover trigger, not a third line", () => {
    render(
      <Field label="Goal" help="What the optimizer maximises inside the ROI.">
        <TextInput readOnly value="mean" />
      </Field>,
    );
    // The help string is not printed under the control...
    expect(container.textContent).not.toContain("What the optimizer maximises");
    // ...it is behind a labelled trigger next to the label.
    const trigger = container.querySelector(".field-help-trigger")!;
    expect(trigger).not.toBeNull();
    expect(trigger.getAttribute("aria-label")).toBe("Help");
  });

  it("errors render in the control column with role=alert; help is suppressed by nothing else", () => {
    render(
      <Field label="Subject" error="Subject sub-999 does not exist.">
        <TextInput readOnly value="sub-999" />
      </Field>,
    );
    const err = container.querySelector(".field-error")!;
    expect(err.getAttribute("role")).toBe("alert");
    expect(err.textContent).toContain("sub-999");
  });

  it("changed marking is opt-in in three states: unset, default, changed", () => {
    render(
      <Field label="A">
        <TextInput readOnly value="" />
      </Field>,
    );
    let cls = container.querySelector(".field")!.className;
    expect(cls).not.toContain("field-default");
    expect(cls).not.toContain("field-changed");

    render(
      <Field label="A" changed={false}>
        <TextInput readOnly value="" />
      </Field>,
    );
    cls = container.querySelector(".field")!.className;
    expect(cls).toContain("field-default");

    render(
      <Field label="A" changed>
        <TextInput readOnly value="" />
      </Field>,
    );
    cls = container.querySelector(".field")!.className;
    expect(cls).toContain("field-changed");
  });
});

describe("changedFields / useChangedFields", () => {
  it("compares structurally, so an ROI or a coordinate is not 'changed' by identity", () => {
    const defaults = { goal: "mean", roi: { x: 1, y: 2, z: 3 }, nets: ["A"] };
    expect([...changedFields({ goal: "mean", roi: { x: 1, y: 2, z: 3 }, nets: ["A"] }, defaults)]).toEqual([]);
    expect([...changedFields({ goal: "max", roi: { x: 1, y: 2, z: 3 }, nets: ["A"] }, defaults)]).toEqual(["goal"]);
    expect([...changedFields({ goal: "mean", roi: { x: 9, y: 2, z: 3 }, nets: ["A"] }, defaults)]).toEqual(["roi"]);
    expect([...changedFields({ goal: "mean", roi: { x: 1, y: 2, z: 3 }, nets: ["A", "B"] }, defaults)]).toEqual(["nets"]);
  });

  it("counts a key the defaults do not declare, but only when it has a value", () => {
    expect(changedFields({ extra: 1 } as Record<string, number>, {}).size).toBe(1);
    expect(changedFields({ extra: undefined } as Record<string, number | undefined>, {}).size).toBe(0);
  });

  it("useChangedFields returns a predicate that also carries the count", () => {
    function Probe() {
      const isChanged = useChangedFields({ goal: "max", intensity: 2 }, { goal: "mean", intensity: 2 });
      return (
        <span>
          {String(isChanged("goal"))}/{String(isChanged("intensity"))}/{isChanged.count}
        </span>
      );
    }
    render(<Probe />);
    expect(container.textContent).toBe("true/false/1");
  });
});

describe("FormSection v2", () => {
  it("is a flush <section>, not a Card", () => {
    render(
      <FormSection title="Electrodes">
        <span>body</span>
      </FormSection>,
    );
    expect(container.querySelector("section.form-section")).not.toBeNull();
    expect(container.querySelector(".card")).toBeNull();
  });

  it("collapsing hides the body and reveals the value summary in the header", () => {
    render(
      <FormSection title="Electrodes" collapsible summary="ellipse · 8×8 mm · gel 4 mm">
        <span>body</span>
      </FormSection>,
    );
    expect(container.textContent).toContain("body");
    expect(container.querySelector(".form-section-summary")).toBeNull();

    click(container.querySelector("button.form-section-header-trigger")!);
    expect(container.textContent).not.toContain("body");
    expect(container.querySelector(".form-section-summary")!.textContent).toContain("gel 4 mm");
    expect(container.querySelector("button.form-section-header-trigger")!.getAttribute("aria-expanded")).toBe("false");
  });

  it("marks a non-default child with an accent dot and an errored one with a danger dot", () => {
    render(
      <FormSection title="Electrodes" changed error>
        <span>body</span>
      </FormSection>,
    );
    expect(container.querySelector(".form-section-mark-changed")).not.toBeNull();
    expect(container.querySelector(".form-section-mark-error")).not.toBeNull();
  });

  it("an advanced group with no changes starts closed", () => {
    render(
      <FormSection title="Search" advanced={<span>advanced body</span>}>
        <span>body</span>
      </FormSection>,
    );
    expect(container.textContent).not.toContain("advanced body");
    expect(container.querySelector(".form-section-advanced-toggle")!.getAttribute("aria-expanded")).toBe("false");
  });

  it("SAFETY RULE: an advanced group holding non-default values force-opens and says how many", () => {
    // A parameter must never sit out of sight doing something to the science. This is the rule
    // that buys the right to collapse Tier-2 groups by default.
    render(
      <FormSection title="Search" advanced={<span>advanced body</span>} advancedChangedCount={2}>
        <span>body</span>
      </FormSection>,
    );
    expect(container.textContent).toContain("advanced body");
    expect(container.querySelector(".form-section-advanced-badge")!.textContent).toContain("2 changed");
  });

  it("force-open is a starting state, not a cage: the user can still collapse it", () => {
    render(
      <FormSection title="Search" advanced={<span>advanced body</span>} advancedChangedCount={2}>
        <span>body</span>
      </FormSection>,
    );
    click(container.querySelector(".form-section-advanced-toggle")!);
    expect(container.textContent).not.toContain("advanced body");
    // ...and the badge stays, so the count is never lost.
    expect(container.querySelector(".form-section-advanced-badge")!.textContent).toContain("2 changed");
  });

  it("the ⋯ menu appears only when there is something in it", () => {
    render(
      <FormSection title="Electrodes">
        <span>body</span>
      </FormSection>,
    );
    expect(container.querySelector(".form-section-menu")).toBeNull();
    render(
      <FormSection title="Electrodes" onReset={() => {}}>
        <span>body</span>
      </FormSection>,
    );
    expect(container.querySelector(".form-section-menu")).not.toBeNull();
  });
});

describe("PageLayout v2", () => {
  it("renders no header by default", () => {
    render(<PageLayout>content</PageLayout>);
    expect(container.querySelector(".page-header")).toBeNull();
    expect(container.querySelector(".page-layout-main")!.textContent).toContain("content");
  });

  it("title/purpose appear only when showHeader is set", () => {
    render(<PageLayout title="Settings" purpose="Server, appearance, tools.">content</PageLayout>);
    expect(container.querySelector(".page-header")).toBeNull();
    render(
      <PageLayout showHeader title="Settings" purpose="Server, appearance, tools.">
        content
      </PageLayout>,
    );
    expect(container.querySelector(".page-header")).not.toBeNull();
    expect(container.querySelector("h1")!.textContent).toBe("Settings");
  });

  it("COMPATIBILITY: a v1 page passing a built header node still renders it", () => {
    render(<PageLayout header={<h1>Results</h1>}>content</PageLayout>);
    expect(container.querySelector("h1")!.textContent).toBe("Results");
  });

  it("COMPATIBILITY: contextPanel is an alias for inspector", () => {
    render(<PageLayout contextPanel={<span>plan</span>}>content</PageLayout>);
    expect(container.querySelector(".page-layout-panel")!.textContent).toBe("plan");
    render(<PageLayout inspector={<span>plan2</span>}>content</PageLayout>);
    expect(container.querySelector(".page-layout-panel")!.textContent).toBe("plan2");
  });

  it("full-bleed adds the variant class; standard does not", () => {
    render(<PageLayout variant="full-bleed">canvas</PageLayout>);
    expect(container.querySelector(".page-layout")!.className).toContain("page-layout-full-bleed");
    render(<PageLayout>form</PageLayout>);
    expect(container.querySelector(".page-layout")!.className).not.toContain("page-layout-full-bleed");
  });

  it("the action bar renders inside the work pane, so it sticks to the pane and not the window", () => {
    render(<PageLayout actionBar={<ActionBar primary={<button type="button">Run</button>} />}>form</PageLayout>);
    expect(container.querySelector(".page-layout-main > .action-bar")).not.toBeNull();
  });
});

describe("SegmentedControl", () => {
  it("reports the picked value", () => {
    const onValueChange = vi.fn();
    render(
      <SegmentedControl
        aria-label="Method"
        value="flex"
        onValueChange={onValueChange}
        options={[
          { value: "flex", label: "Flex" },
          { value: "ex", label: "Ex" },
        ]}
      />,
    );
    click(container.querySelectorAll(".segmented-item")[1]!);
    expect(onValueChange).toHaveBeenCalledWith("ex");
  });

  it("is never empty: clicking the active segment does not deselect it", () => {
    // Radix's single-select ToggleGroup deselects on a second click, which would leave a page with
    // no method at all. That is corrected here, not at every call site.
    const onValueChange = vi.fn();
    render(
      <SegmentedControl
        aria-label="Method"
        value="flex"
        onValueChange={onValueChange}
        options={[
          { value: "flex", label: "Flex" },
          { value: "ex", label: "Ex" },
        ]}
      />,
    );
    click(container.querySelectorAll(".segmented-item")[0]!);
    expect(onValueChange).not.toHaveBeenCalled();
  });
});

describe("ActionBar / StatusBar / RefetchBar", () => {
  it("carries the digest, a problem count and one primary with the ⌘⏎ hint", () => {
    const onWarningsClick = vi.fn();
    render(
      <ActionBar
        digest="2 jobs · 8 CPU · 16 GB"
        warningCount={2}
        onWarningsClick={onWarningsClick}
        primary={<button type="button">Run 2 simulations</button>}
      />,
    );
    expect(container.querySelector(".action-bar-digest")!.textContent).toContain("8 CPU");
    expect(container.querySelector(".action-bar-hint")!.textContent).toContain("⌘⏎");
    click(container.querySelector(".action-bar-warnings button")!);
    expect(onWarningsClick).toHaveBeenCalled();
  });

  it("a blocked plan prints no digest — the disabled primary is the only signal", () => {
    render(<ActionBar digest="Pick a subject and an ROI" blocked primary={<button type="button">Run</button>} />);
    expect(container.querySelector(".action-bar-digest")).toBeNull();
  });

  it("the problem chip is hidden at zero, and singular/plural is correct", () => {
    render(<ActionBar digest="ok" warningCount={0} />);
    expect(container.querySelector(".action-bar-warnings")).toBeNull();
    render(<ActionBar digest="ok" warningCount={1} onWarningsClick={() => {}} />);
    expect(container.querySelector(".action-bar-warnings")!.textContent).toBe("1 problem");
  });

  it("StatusCell renders label + value; `end` pushes the cell right", () => {
    render(
      <StatusBar>
        <StatusCell label="RAS">-28.4 12.1 54.0</StatusCell>
        <StatusCell end label="tit">
          3.0.0-dev
        </StatusCell>
      </StatusBar>,
    );
    const cells = container.querySelectorAll(".status-bar-cell");
    expect(cells).toHaveLength(2);
    expect(cells[0]!.textContent).toBe("RAS-28.4 12.1 54.0");
    expect(cells[1]!.className).toContain("status-bar-cell-end");
  });

  it("RefetchBar reserves no space when inactive", () => {
    render(<RefetchBar active={false} />);
    expect(container.querySelector(".refetch-bar")).toBeNull();
    render(<RefetchBar active />);
    expect(container.querySelector(".refetch-bar")!.getAttribute("role")).toBe("progressbar");
  });
});

describe("Empty / loading / failed", () => {
  it("an inline empty drops the icon and takes a quiet action", () => {
    render(<EmptyState variant="inline" icon={<span>icon</span>} message="No simulations for ernie yet." actionLabel="Run one" onAction={() => {}} />);
    const el = container.querySelector(".empty-state")!;
    expect(el.className).toContain("empty-state-inline");
    expect(container.querySelector(".empty-state-icon")).toBeNull();
    expect(container.querySelector("button")!.className).toContain("btn-ghost");
  });

  it("a whole-page empty stays centred, with its icon and a primary", () => {
    render(<EmptyState icon={<span>icon</span>} message="No subjects in this project." actionLabel="Add subject" onAction={() => {}} />);
    expect(container.querySelector(".empty-state")!.className).not.toContain("empty-state-inline");
    expect(container.querySelector(".empty-state-icon")).not.toBeNull();
    expect(container.querySelector("button")!.className).toContain("btn-primary");
  });

  it("Skeleton rows produce one --row-h bar per real row, not a slab", () => {
    render(<Skeleton rows={3} />);
    const bars = container.querySelectorAll(".skeleton-rows > .skeleton");
    expect(bars).toHaveLength(3);
    expect((bars[0] as HTMLElement).style.height).toBe("var(--row-h)");
    render(<Skeleton height={240} />);
    expect(container.querySelector(".skeleton-rows")).toBeNull();
  });

  it("a failed load is an inline error with the server's own message and a retry", () => {
    const onAction = vi.fn();
    render(<InlineError message="Could not load the subject list." detail="GET /api/subjects — 503" onAction={onAction} />);
    const el = container.querySelector(".inline-error")!;
    expect(el.getAttribute("role")).toBe("alert");
    expect(el.textContent).toContain("503");
    click(container.querySelector(".inline-error-action button")!);
    expect(onAction).toHaveBeenCalled();
  });
});
