import { Button } from "../../../ui/Button";

/**
 * The atlas Explode toggle. It names the action a click performs, so the label flips to "Collapse"
 * while exploded — and carries no `aria-pressed`, which would make a screen reader say "Collapse,
 * pressed" (a stable label is what `aria-pressed` is for). The primary variant is the visual state.
 */
export function ExplodeButton({ exploded, onToggle }: { exploded: boolean; onToggle: () => void }) {
  return (
    <Button
      variant={exploded ? "primary" : "secondary"}
      data-testid="scene-pane-explode"
      title={
        exploded
          ? "Bring the atlas regions back together — the selection is unchanged"
          : "Pull the atlas regions apart to reach deep structures — the selection is unchanged"
      }
      onClick={onToggle}
    >
      {exploded ? "Collapse" : "Explode"}
    </Button>
  );
}
