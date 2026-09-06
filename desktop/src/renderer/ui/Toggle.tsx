import * as SwitchPrimitive from "@radix-ui/react-switch";
import * as CheckboxPrimitive from "@radix-ui/react-checkbox";
import * as RadioGroupPrimitive from "@radix-ui/react-radio-group";
import * as SliderPrimitive from "@radix-ui/react-slider";
import { Check, Minus } from "lucide-react";
import { type ReactNode } from "react";
import { NumberInput } from "./NumberInput";

export function Switch({
  checked,
  onCheckedChange,
  disabled,
  id,
  "aria-label": ariaLabel,
}: {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
  id?: string;
  "aria-label"?: string;
}) {
  return (
    <SwitchPrimitive.Root
      id={id}
      className="switch-root"
      checked={checked}
      onCheckedChange={onCheckedChange}
      disabled={disabled}
      aria-label={ariaLabel}
    >
      <SwitchPrimitive.Thumb className="switch-thumb" />
    </SwitchPrimitive.Root>
  );
}

export function Checkbox({
  checked,
  onCheckedChange,
  disabled,
  id,
  label,
  "aria-label": ariaLabel,
  "aria-describedby": describedBy,
}: {
  checked: boolean | "indeterminate";
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
  id?: string;
  label?: ReactNode;
  "aria-label"?: string;
  "aria-describedby"?: string;
}) {
  const box = (
    <CheckboxPrimitive.Root
      id={id}
      className="checkbox-root"
      checked={checked}
      onCheckedChange={(v) => onCheckedChange(v === true)}
      disabled={disabled}
      aria-label={ariaLabel}
      aria-describedby={describedBy}
    >
      <CheckboxPrimitive.Indicator>{checked === "indeterminate" ? <Minus size={12} /> : <Check size={12} />}</CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
  if (!label) return box;
  return (
    <label className="checkbox-label-row">
      {box}
      {/* The text gets its own element rather than sitting as a bare text node beside the box.
          It reads the same, and it stops the row's text being invisible to anything that walks
          the DOM by element — `tests/e2e/_metrics.ts`'s dead-space probe resolves a point to the
          innermost ELEMENT, so a text node inside a <label> that also contains the box scored as
          empty ground. Pre-processing's Structural section measured 92 % dead with three ticked
          checkboxes in it. */}
      <span className="checkbox-label-text">{label}</span>
    </label>
  );
}

export interface RadioOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export function RadioGroup({
  value,
  onValueChange,
  options,
  layout = "horizontal",
  name,
}: {
  value: string;
  onValueChange: (value: string) => void;
  options: RadioOption[];
  layout?: "horizontal" | "cards";
  name?: string;
}) {
  return (
    <RadioGroupPrimitive.Root
      className={layout === "cards" ? "radio-group-cards" : "radio-group"}
      value={value}
      onValueChange={onValueChange}
      name={name}
    >
      {options.map((opt) =>
        layout === "cards" ? (
          <RadioGroupPrimitive.Item key={opt.value} value={opt.value} disabled={opt.disabled} className="radio-card" asChild>
            <label>
              <RadioGroupPrimitive.Indicator />
              <span className="radio-label-text">{opt.label}</span>
            </label>
          </RadioGroupPrimitive.Item>
        ) : (
          <label key={opt.value} className="radio-item-row">
            <RadioGroupPrimitive.Item value={opt.value} disabled={opt.disabled} className="radio-root">
              <RadioGroupPrimitive.Indicator className="radio-indicator" />
            </RadioGroupPrimitive.Item>
            <span className="radio-label-text">{opt.label}</span>
          </label>
        ),
      )}
    </RadioGroupPrimitive.Root>
  );
}

export function Slider({
  value,
  onValueChange,
  min = 0,
  max = 100,
  step = 1,
  unit,
  showNumberInput = true,
  disabled,
  "aria-label": ariaLabel,
  "data-testid": testId,
}: {
  value: number;
  onValueChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  unit?: string;
  showNumberInput?: boolean;
  disabled?: boolean;
  "aria-label"?: string;
  "data-testid"?: string;
}) {
  return (
    <div className="slider-row" data-testid={testId}>
      <SliderPrimitive.Root
        className="slider-root"
        value={[value]}
        onValueChange={([v]) => v !== undefined && onValueChange(v)}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
      >
        <SliderPrimitive.Track className="slider-track">
          <SliderPrimitive.Range className="slider-range" />
        </SliderPrimitive.Track>
        <SliderPrimitive.Thumb className="slider-thumb" aria-label={ariaLabel} aria-valuetext={unit ? `${value} ${unit}` : undefined} />
      </SliderPrimitive.Root>
      {showNumberInput && (
        <NumberInput
          value={value}
          onValueChange={(v) => v !== undefined && onValueChange(Math.min(max, Math.max(min, v)))}
          unit={unit}
          min={min}
          max={max}
          step={step}
          disabled={disabled}
          aria-label={ariaLabel ? `${ariaLabel} value` : undefined}
        />
      )}
    </div>
  );
}
