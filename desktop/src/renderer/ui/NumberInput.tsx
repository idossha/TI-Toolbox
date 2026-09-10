import { forwardRef, type InputHTMLAttributes } from "react";
import { cn } from "./utils";

export interface NumberInputProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "value" | "onChange"> {
  value: number | undefined;
  onValueChange: (value: number | undefined) => void;
  unit?: string;
  step?: number;
  min?: number;
  max?: number;
  invalid?: boolean;
}

/** Numeric field with an optional unit suffix; tabular, right-aligned, mono. */
export const NumberInput = forwardRef<HTMLInputElement, NumberInputProps>(function NumberInput(
  { value, onValueChange, unit, invalid, className, disabled, ...rest },
  ref,
) {
  return (
    <div className={cn("number-input", !unit && "number-input-no-unit", className)}>
      <input
        ref={ref}
        type="number"
        inputMode="decimal"
        className={cn("control", invalid && "control-error")}
        value={value ?? ""}
        disabled={disabled}
        onChange={(e) => {
          const raw = e.target.value;
          onValueChange(raw === "" ? undefined : Number(raw));
        }}
        {...rest}
      />
      {unit && <span className="number-input-unit">{unit}</span>}
    </div>
  );
});
