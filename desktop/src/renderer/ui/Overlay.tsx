import * as DialogPrimitive from "@radix-ui/react-dialog";
import * as AlertDialogPrimitive from "@radix-ui/react-alert-dialog";
import * as PopoverPrimitive from "@radix-ui/react-popover";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { X } from "lucide-react";
import { useState, type ReactNode } from "react";
import { usePageActive } from "../app/pageActivity";
import { Button, IconButton, type ButtonVariant } from "./Button";

/** Body portals must follow the page that owns them, without clearing that page's dialog draft. */
function usePageOverlay(open?: boolean, onOpenChange?: (open: boolean) => void) {
  const active = usePageActive();
  const [localOpen, setLocalOpen] = useState(false);
  return {
    open: active && (open ?? localOpen),
    onOpenChange(next: boolean) {
      if (!active) return;
      if (open === undefined) setLocalOpen(next);
      onOpenChange?.(next);
    },
    onCloseAutoFocus(event: Event) {
      if (!active) event.preventDefault();
    },
  };
}

export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  trigger,
}: {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  title: string;
  description?: string;
  children?: ReactNode;
  footer?: ReactNode;
  trigger?: ReactNode;
}) {
  const overlay = usePageOverlay(open, onOpenChange);
  return (
    <DialogPrimitive.Root open={overlay.open} onOpenChange={overlay.onOpenChange}>
      {trigger && <DialogPrimitive.Trigger asChild>{trigger}</DialogPrimitive.Trigger>}
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="overlay" />
        <DialogPrimitive.Content className="dialog-content" onCloseAutoFocus={overlay.onCloseAutoFocus}>
          <DialogPrimitive.Title className="dialog-title">{title}</DialogPrimitive.Title>
          {description && <DialogPrimitive.Description className="dialog-description">{description}</DialogPrimitive.Description>}
          {children}
          {footer && <div className="dialog-footer">{footer}</div>}
          <DialogPrimitive.Close asChild>
            <IconButton aria-label="Close dialog" icon={<X size={16} />} className="dialog-close" />
          </DialogPrimitive.Close>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

/**
 * Confirmations only (overwrite, stop, terminate, delete) — the confirm button repeats the
 * destructive verb ("Overwrite", "Stop job", "Delete montage"), never a bare "OK".
 */
export function AlertDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  onConfirm,
  confirmVariant = "destructive",
  cancelLabel = "Cancel",
  trigger,
}: {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  title: string;
  description: string;
  confirmLabel: string;
  onConfirm: () => void;
  confirmVariant?: ButtonVariant;
  cancelLabel?: string;
  trigger?: ReactNode;
}) {
  const overlay = usePageOverlay(open, onOpenChange);
  return (
    <AlertDialogPrimitive.Root open={overlay.open} onOpenChange={overlay.onOpenChange}>
      {trigger && <AlertDialogPrimitive.Trigger asChild>{trigger}</AlertDialogPrimitive.Trigger>}
      <AlertDialogPrimitive.Portal>
        <AlertDialogPrimitive.Overlay className="overlay" />
        <AlertDialogPrimitive.Content className="alert-dialog-content" onCloseAutoFocus={overlay.onCloseAutoFocus}>
          <AlertDialogPrimitive.Title className="dialog-title">{title}</AlertDialogPrimitive.Title>
          <AlertDialogPrimitive.Description className="dialog-description">{description}</AlertDialogPrimitive.Description>
          <div className="dialog-footer">
            <AlertDialogPrimitive.Cancel asChild>
              <Button variant="secondary">{cancelLabel}</Button>
            </AlertDialogPrimitive.Cancel>
            <AlertDialogPrimitive.Action asChild>
              <Button variant={confirmVariant} onClick={onConfirm}>
                {confirmLabel}
              </Button>
            </AlertDialogPrimitive.Action>
          </div>
        </AlertDialogPrimitive.Content>
      </AlertDialogPrimitive.Portal>
    </AlertDialogPrimitive.Root>
  );
}

/** Jobs rail expansion or a right-side detail panel. */
export function Drawer({
  open,
  onOpenChange,
  title,
  children,
  side = "right",
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  children: ReactNode;
  side?: "right";
}) {
  void side;
  const overlay = usePageOverlay(open, onOpenChange);
  return (
    <DialogPrimitive.Root open={overlay.open} onOpenChange={overlay.onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="overlay" />
        <DialogPrimitive.Content className="drawer-content" onCloseAutoFocus={overlay.onCloseAutoFocus}>
          <div className="drawer-header">
            <DialogPrimitive.Title className="card-title">{title}</DialogPrimitive.Title>
            <DialogPrimitive.Close asChild>
              <IconButton aria-label="Close" icon={<X size={16} />} />
            </DialogPrimitive.Close>
          </div>
          <div className="drawer-body">{children}</div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

export function Popover({
  trigger,
  children,
  open,
  onOpenChange,
}: {
  trigger: ReactNode;
  children: ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}) {
  const overlay = usePageOverlay(open, onOpenChange);
  return (
    <PopoverPrimitive.Root open={overlay.open} onOpenChange={overlay.onOpenChange}>
      <PopoverPrimitive.Trigger asChild>{trigger}</PopoverPrimitive.Trigger>
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content className="popover-content" sideOffset={4} onCloseAutoFocus={overlay.onCloseAutoFocus}>
          {children}
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  );
}

/** 400 ms delay, per DESIGN.md. */
export function Tooltip({ label, children }: { label: string; children: ReactNode }) {
  const overlay = usePageOverlay();
  return (
    <TooltipPrimitive.Provider delayDuration={400}>
      <TooltipPrimitive.Root open={overlay.open} onOpenChange={overlay.onOpenChange}>
        <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content className="tooltip-content" sideOffset={4}>
            {label}
            <TooltipPrimitive.Arrow className="tooltip-arrow" />
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  );
}
