import * as SelectPrimitive from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";
import { useState } from "react";
import { usePageActive } from "../app/pageActivity";
import { cn } from "./utils";

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export function Select({
  value,
  onValueChange,
  options,
  placeholder = "Select…",
  disabled,
  invalid,
  id,
  "aria-label": ariaLabel,
  "aria-describedby": describedBy,
}: {
  value: string | undefined;
  onValueChange: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  disabled?: boolean;
  invalid?: boolean;
  id?: string;
  "aria-label"?: string;
  "aria-describedby"?: string;
}) {
  const active = usePageActive();
  const [open, setOpen] = useState(false);
  const selected = options.find((option) => option.value === value);
  return (
    <SelectPrimitive.Root value={value} onValueChange={onValueChange} disabled={disabled} open={active && open} onOpenChange={setOpen}>
      <SelectPrimitive.Trigger
        id={id}
        className={cn("select-trigger", invalid && "control-error")}
        aria-label={ariaLabel}
        aria-describedby={describedBy}
        aria-invalid={invalid || undefined}
        title={selected?.label}
      >
        <span className="picker-value">
          <SelectPrimitive.Value placeholder={placeholder} />
        </span>
        <SelectPrimitive.Icon className="picker-chevron">
          <ChevronDown size={14} aria-hidden />
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content
          className="select-content"
          position="popper"
          sideOffset={4}
          collisionPadding={8}
          onCloseAutoFocus={(event) => { if (!active) event.preventDefault(); }}
        >
          <SelectPrimitive.Viewport>
            {options.map((opt) => (
              <SelectPrimitive.Item key={opt.value} value={opt.value} disabled={opt.disabled} className="select-item">
                <span className="picker-option-mark" aria-hidden>
                  <SelectPrimitive.ItemIndicator>
                    <Check size={14} />
                  </SelectPrimitive.ItemIndicator>
                </span>
                <span className="picker-option-label">
                  <SelectPrimitive.ItemText>{opt.label}</SelectPrimitive.ItemText>
                </span>
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
}
