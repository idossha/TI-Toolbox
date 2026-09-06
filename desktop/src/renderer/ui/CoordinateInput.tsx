import { NumberInput } from "./NumberInput";
import { SegmentedControl } from "./SegmentedControl";

export interface Coordinate {
  x: number | undefined;
  y: number | undefined;
  z: number | undefined;
  radius?: number | undefined;
}

export function CoordinateInput({
  value,
  onValueChange,
  space,
  onSpaceChange,
  withRadius = false,
  disabled,
}: {
  value: Coordinate;
  onValueChange: (value: Coordinate) => void;
  space?: "subject" | "mni";
  onSpaceChange?: (space: "subject" | "mni") => void;
  withRadius?: boolean;
  disabled?: boolean;
}) {
  const axis = (key: "x" | "y" | "z" | "radius", label: string) => (
    <div className="coordinate-axis">
      <span className="coordinate-axis-label">{label}</span>
      <NumberInput
        value={value[key]}
        onValueChange={(v) => onValueChange({ ...value, [key]: v })}
        unit="mm"
        step={0.1}
        disabled={disabled}
        aria-label={`${label} coordinate`}
      />
    </div>
  );
  return (
    <div className="coordinate-input">
      {axis("x", "X")}
      {axis("y", "Y")}
      {axis("z", "Z")}
      {withRadius && axis("radius", "Radius")}
      {space && onSpaceChange && (
        /* DESIGN.md §4.2 rule 9: a small exclusive choice is a `SegmentedControl`. This is the
           same subject/MNI choice `pages/_shared/roi/RoiPicker.tsx` renders as a segment, and
           this control is reachable from that picker's own "Add ROI" dialog — as a radio pair it
           was two idioms for one idea meeting inside a single flow. Radix renders the identical
           `radiogroup`/`radio` roles, so every existing spec and every screen reader sees what it
           saw before. */
        <SegmentedControl
          value={space}
          onValueChange={(v) => onSpaceChange(v as "subject" | "mni")}
          options={[
            { value: "subject", label: "Subject" },
            { value: "mni", label: "MNI" },
          ]}
          size="sm"
          disabled={disabled}
          aria-label="Coordinate space"
        />
      )}
    </div>
  );
}
