import { lazy, Suspense, type ComponentType } from "react";

/**
 * Hosts the quick-notes drawer (⌘⇧N, plan §2: the panel becomes a global drawer).
 *
 * Lane S2 turns `pages/panel-quick-notes/` into an exported `QuickNotesDrawer`. Until that lands,
 * this file must still typecheck and build — so the module is looked up through `import.meta.glob`
 * (a build-time directory scan that yields an empty record when the file is absent) rather than a
 * static import that would fail resolution. When the drawer is not there yet, ⌘⇧N does nothing
 * visible and nothing breaks.
 */
export interface QuickNotesDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const modules = import.meta.glob("../pages/panel-quick-notes/QuickNotesDrawer.tsx") as Record<
  string,
  () => Promise<unknown>
>;
const load = Object.values(modules)[0];

/** The drawer is absent until lane S2 writes it; a module that exists but exports neither name is
 *  a programming error the shell must not crash on, so it renders nothing and says why once. */
const Missing: ComponentType<QuickNotesDrawerProps> = () => null;

const QuickNotesDrawer = load
  ? lazy(async () => {
      const mod = (await load()) as Partial<Record<"QuickNotesDrawer" | "default", ComponentType<QuickNotesDrawerProps>>>;
      const Component = mod.QuickNotesDrawer ?? mod.default;
      if (!Component) console.warn("panel-quick-notes/QuickNotesDrawer.tsx exports no QuickNotesDrawer");
      return { default: Component ?? Missing };
    })
  : null;

export function QuickNotesHost({ open, onOpenChange }: QuickNotesDrawerProps) {
  if (!QuickNotesDrawer || !open) return null;
  return (
    <Suspense fallback={null}>
      <QuickNotesDrawer open={open} onOpenChange={onOpenChange} />
    </Suspense>
  );
}
