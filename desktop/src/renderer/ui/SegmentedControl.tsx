import * as ToggleGroupPrimitive from "@radix-ui/react-toggle-group";
import type { ReactNode } from "react";
import { cn } from "./utils";

export interface SegmentedOption<T extends string = string> {
  value: T;
  label: ReactNode;
  disabled?: boolean;
  /** Tooltip / title text — a segment label is short, the reason it exists sometimes is not. */
  title?: string;
}

export interface SegmentedControlProps<T extends string = string> {
  value: T;
  onValueChange: (value: T) => void;
  options: SegmentedOption<T>[];
  size?: "sm" | "md";
  disabled?: boolean;
  "aria-label": string;
  className?: string;
}

/**
 * One-of-N in one 28px row: Method ⟨Flex │ Ex │ mEx⟩, Scope ⟨Subject │ Group │ Figures⟩. Use it
 * wherever a `RadioGroup` would spend a whole block on three mutually exclusive words.
 *
 * Radix `ToggleGroup` in single mode, with one deliberate correction: Radix lets a single-select
 * group be deselected by clicking the active item, which would leave a page with no method at all.
 * An empty value is ignored here, so the control is never empty.
 */
export function SegmentedControl<T extends string = string>({
  value,
  onValueChange,
  options,
  size = "md",
  disabled,
  "aria-label": ariaLabel,
  className,
}: SegmentedControlProps<T>) {
  return (
    <ToggleGroupPrimitive.Root
      type="single"
      value={value}
      onValueChange={(next) => {
        if (next) onValueChange(next as T);
      }}
      disabled={disabled}
      aria-label={ariaLabel}
      className={cn("segmented", size === "sm" && "segmented-sm", className)}
    >
      {options.map((option) => (
        <ToggleGroupPrimitive.Item
          key={option.value}
          value={option.value}
          disabled={option.disabled}
          title={option.title}
          className="segmented-item"
        >
          {option.label}
        </ToggleGroupPrimitive.Item>
      ))}
    </ToggleGroupPrimitive.Root>
  );
}
