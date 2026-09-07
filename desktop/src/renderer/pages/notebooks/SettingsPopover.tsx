/**
 * Notebook editor settings — the sliders button in the toolbar.
 *
 * Same gesture as the per-job settings dialogs (DESIGN §5): a sliders icon
 * opening a popover of the things that change how the editor behaves, not what
 * it runs. Nothing here touches the notebook or the kernel, which is why it is
 * a popover rather than a form with a Save: every control writes straight
 * through to `localStorage` and every open cell reconfigures in place.
 */
import type { JSX } from "react";
import * as Popover from "@radix-ui/react-popover";
import { SlidersHorizontal } from "lucide-react";
import { Button, SegmentedControl, Switch } from "../../ui";
import {
  FONT_SIZES,
  INDENT_SIZES,
  useNotebookPrefs,
  type NotebookPrefs,
} from "./settings";

interface Row {
  key: keyof NotebookPrefs;
  label: string;
  hint: string;
}

const SWITCHES: Row[] = [
  {
    key: "autocomplete",
    label: "Autocompletion",
    hint: "Suggestions from the running kernel on ⇥ and ⌃Space — it knows what your objects actually hold.",
  },
  {
    key: "signatureHelp",
    label: "Signature help",
    hint: "The signature and docstring of the name under the cursor.",
  },
  { key: "closeBrackets", label: "Auto-close brackets", hint: "Typing ( gives you ()." },
  { key: "lineNumbers", label: "Line numbers", hint: "In the cell gutter." },
  { key: "wordWrap", label: "Word wrap", hint: "Wrap long lines instead of scrolling sideways." },
];

export function NotebookSettings(): JSX.Element {
  const prefs = useNotebookPrefs((state) => state.prefs);
  const set = useNotebookPrefs((state) => state.set);
  const reset = useNotebookPrefs((state) => state.reset);

  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <Button
          size="sm"
          variant="ghost"
          title="Editor settings"
          aria-label="Editor settings"
          data-testid="nb-settings-open"
        >
          <SlidersHorizontal size={13} />
        </Button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          className="nb-settings"
          data-testid="nb-settings"
          align="end"
          sideOffset={6}
        >
          <p className="nb-settings__title">Editor</p>
          {SWITCHES.map((row) => (
            <label className="nb-settings__row" key={row.key}>
              <span className="nb-settings__label">
                {row.label}
                <span className="nb-settings__hint">{row.hint}</span>
              </span>
              <span data-testid={`nb-pref-${row.key}`} data-checked={prefs[row.key] ? "1" : "0"}>
                <Switch
                  checked={prefs[row.key] as boolean}
                  onCheckedChange={(next) => set(row.key, next as never)}
                  aria-label={row.label}
                />
              </span>
            </label>
          ))}

          <div className="nb-settings__row nb-settings__row--stacked">
            <span className="nb-settings__label">
              Indent
              <span className="nb-settings__hint">Spaces per level. Python&rsquo;s answer is 4.</span>
            </span>
            <span data-testid="nb-pref-indentSize" data-value={prefs.indentSize}>
              <SegmentedControl
                size="sm"
                aria-label="Indent size"
                value={String(prefs.indentSize)}
                onValueChange={(next) => set("indentSize", Number(next))}
                options={INDENT_SIZES.map((size) => ({ value: String(size), label: String(size) }))}
              />
            </span>
          </div>

          <div className="nb-settings__row nb-settings__row--stacked">
            <span className="nb-settings__label">
              Font size
              <span className="nb-settings__hint">Cells and their text output.</span>
            </span>
            <span data-testid="nb-pref-fontSize" data-value={prefs.fontSize}>
              <SegmentedControl
                size="sm"
                aria-label="Font size"
                value={String(prefs.fontSize)}
                onValueChange={(next) => set("fontSize", Number(next))}
                options={FONT_SIZES.map((size) => ({ value: String(size), label: String(size) }))}
              />
            </span>
          </div>

          <div className="nb-settings__footer">
            <span className="nb-settings__hint">Saved on this machine, for every notebook.</span>
            <Button size="sm" variant="ghost" onClick={reset} data-testid="nb-pref-reset">
              Reset
            </Button>
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
