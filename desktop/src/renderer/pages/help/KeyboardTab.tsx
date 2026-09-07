/**
 * The Help page's own keyboard reference (Q5, `docs/dev/design-notes.md` §4;
 * confirmed by the orchestrator: "Cmd+<n> = the workflow pages in nav order, then Settings,
 * '?' = Help"). This is a page you can browse to, unlike the `?` overlay
 * (`app/KeyboardSheet.tsx`) which needs you to already know the gesture — the two are deliberately
 * separate surfaces for the same facts, not a duplicate implementation. Both now derive the list
 * from `app/registry.ts`'s `NAV_ORDER`: this tab used to hardcode nine rows ending "⌘9 Settings",
 * and every later rail change — the Pipeline row, then the ⌘0-based numbering that gave all ten
 * digits to workflow rows and left Settings with only ⌘, — would have made that copy wrong again. A rail row must not need an edit here.
 *
 * There is no Freeview, no Gmsh and no X11 in this list, and there should never be again — v3
 * removed the external-viewer flow entirely (D3), and the old PyQt help tab's per-viewer shortcut
 * cheat sheets (mouse wheel, right-click-drag, `Ctrl+Wheel`, …) went with it.
 */
import { Kbd } from "../../ui/Feedback";
import { Card, CardBody, CardHeader } from "../../ui/Layout";
import { modKey, modShiftKey } from "../../app/keyboard";
import { enabledPages } from "../../app/registry";

/**
 * Built lazily (called from inside the component, not at module scope): `app/registry.ts` discovers
 * every page directory's `index.tsx` through an eager `import.meta.glob`, and `app/keyboard.ts` itself
 * imports `enabledPages` from that same registry — so a module-scope call into `keyboard.ts` from
 * here re-enters that cycle while `keyboard.ts`'s own `isMac` constant is still mid-initialization
 * ("Cannot access 'isMac' before initialization", caught by `npx vitest run`). `KeyboardSheet.tsx`
 * (`app/`) sidesteps the same cycle the same way — building its rows inside its render, not at the
 * top of the file.
 */
function pageKeys(): [string, string][] {
  return [
    ...enabledPages
      .filter((p) => p.shortcut && p.shortcut !== ",")
      .sort((a, b) => (a.shortcut ?? "").localeCompare(b.shortcut ?? ""))
      .map((p): [string, string] => [modKey(p.shortcut as string), p.title]),
    // Settings is not a rail row, so it has no digit — all ten belong to the workflow rows since
    // the rail started counting at ⌘0. It is listed here by its only chord rather than dropping
    // off a sheet that is supposed to be the complete list.
    [modKey(","), "Settings"],
    ["?", "Help — this sheet"],
  ];
}

function appKeys(): [string, string][] {
  return [
    [modKey("K"), "Command palette"],
    [modKey("J"), "Jobs panel"],
    [modShiftKey("I"), "Collapse or expand the right pane"],
    [modShiftKey("V"), "Focus the viewer canvas"],
  ];
}

function ShortcutList({ rows }: { rows: [string, string][] }) {
  return (
    <dl style={{ margin: 0, display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
      {rows.map(([key, what]) => (
        <div key={what} style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
          <dt style={{ flex: "0 0 88px" }}>
            <Kbd>{key}</Kbd>
          </dt>
          <dd className="text-body" style={{ margin: 0 }}>
            {what}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function KeyboardTab() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
      <p className="text-body" style={{ color: "var(--ink-2)" }}>
        Unmodified keys belong to whatever has focus, the viewer canvas included. Every app shortcut carries the modifier key shown below, with{" "}
        <Kbd>?</Kbd> as the one exception.
      </p>

      <Card>
        <CardHeader title="Pages" />
        <CardBody>
          <ShortcutList rows={pageKeys()} />
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="App" />
        <CardBody>
          <ShortcutList rows={appKeys()} />
        </CardBody>
      </Card>
    </div>
  );
}
