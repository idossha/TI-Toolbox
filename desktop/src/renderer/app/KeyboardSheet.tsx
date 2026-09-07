import { Dialog } from "../ui/Overlay";
import { Kbd } from "../ui/Feedback";
import { enabledPages } from "./registry";
import { modKey, modShiftKey } from "./keyboard";

/**
 * One sheet, both key sets (DESIGN.md §6.5). App keys are derived from the registry so the sheet
 * cannot drift from what the shell actually binds; the viewer's own keys are listed as a static
 * block because they belong to the engine, not to this app — the canvas owns unmodified keys
 * whenever it has focus, which is the rule the top of the sheet states.
 */

const APP_KEYS: [string, string][] = [
  [modKey("K"), "Command palette"],
  [modKey("P"), "Switch subject"],
  [modKey("J"), "Jobs panel"],
  [modShiftKey("N"), "Quick notes"],
  [modShiftKey("V"), "Focus the viewer canvas"],
  [modShiftKey("I"), "Collapse or restore the right pane"],
  [modKey("⏎"), "Run the action bar's primary"],
  [modKey(","), "Settings (same as ⌘0)"],
  ["?", "This sheet"],
  ["Esc", "Close the innermost overlay"],
];

const VIEWER_KEYS: [string, string][] = [
  ["Arrows", "Move the cursor one slice"],
  ["Scroll", "Slice through the stack"],
  ["Drag", "Rotate (3D) or pan (2D)"],
  ["Shift + drag", "Window and level"],
];

function KeyTable({ title, rows }: { title: string; rows: [string, string][] }) {
  return (
    <section className="keyboard-sheet-block">
      <h3 className="text-eyebrow">{title}</h3>
      <dl className="keyboard-sheet-list">
        {rows.map(([key, what]) => (
          <div key={key} className="keyboard-sheet-row">
            <dt>
              <Kbd>{key}</Kbd>
            </dt>
            <dd>{what}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

export function KeyboardSheet({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const pageKeys: [string, string][] = enabledPages
    .filter((p) => p.shortcut && p.shortcut !== ",")
    .sort((a, b) => (a.shortcut ?? "").localeCompare(b.shortcut ?? ""))
    .map((p) => [modKey(p.shortcut as string), p.title]);

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Keyboard"
      description="Unmodified keys belong to whatever has focus, the viewer canvas included. Every app shortcut carries the modifier key."
    >
      <div className="keyboard-sheet" data-testid="keyboard-sheet">
        <KeyTable title="App" rows={APP_KEYS} />
        <KeyTable title="Screens" rows={pageKeys} />
        <KeyTable title="Viewer canvas" rows={VIEWER_KEYS} />
      </div>
    </Dialog>
  );
}
