import { lazy, Suspense } from "react";
import type { QuickNotesDrawerProps } from "../pages/panel-quick-notes/QuickNotesDrawer";

/**
 * Hosts the ⌘⇧N quick-notes drawer. Closed, it renders nothing: the drawer unmounts, and its own
 * unmount sends any text still waiting on the autosave delay.
 */
export type { QuickNotesDrawerProps };

const QuickNotesDrawer = lazy(() => import("../pages/panel-quick-notes/QuickNotesDrawer"));

export function QuickNotesHost({ open, onOpenChange }: QuickNotesDrawerProps) {
  if (!open) return null;
  return (
    <Suspense fallback={null}>
      <QuickNotesDrawer open={open} onOpenChange={onOpenChange} />
    </Suspense>
  );
}
