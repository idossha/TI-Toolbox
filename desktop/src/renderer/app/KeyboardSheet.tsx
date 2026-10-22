import { Dialog } from "../ui/Overlay";
import { Kbd } from "../ui/Feedback";
import { enabledPages } from "./registry";
import { modKey, modShiftKey } from "./keyboard";

/**
 * One sheet (DESIGN.md §6.5). Screen keys are derived from the registry so the sheet cannot drift
 * from what the shell actually binds. The viewer is the separate TetraVox app, whose own keys are
 * its own; a focused control here owns unmodified keys, which is the rule the top of the sheet
 * states.
 */

const APP_KEYS: [string, string][] = [
  [modKey("K"), "Command palette"],
  [modKey("P"), "Switch subject"],
  [modKey("J"), "Jobs panel"],
  [modShiftKey("N"), "Quick notes"],
  [modShiftKey("V"), "Open or bring forward TetraVox"],
  [modShiftKey("I"), "Collapse or restore the right pane"],
  [modKey("⏎"), "Run the action bar's primary"],
  [modKey(","), "Settings"],
  ["?", "This sheet"],
  ["Esc", "Close the innermost overlay"],
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
      description="Unmodified keys belong to whatever has focus. Every app shortcut carries the modifier key."
    >
      <div className="keyboard-sheet" data-testid="keyboard-sheet">
        <KeyTable title="App" rows={APP_KEYS} />
        <KeyTable title="Screens" rows={pageKeys} />
      </div>
    </Dialog>
  );
}
