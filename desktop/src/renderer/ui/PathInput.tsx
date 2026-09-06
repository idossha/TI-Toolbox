import { FolderOpen } from "lucide-react";
import { Button } from "./Button";
import { TextInput } from "./Field";

export interface PathInputProps {
  value: string;
  onValueChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  invalid?: boolean;
  id?: string;
  /**
   * Opens a host file/folder picker and resolves to a container-mapped path. Pass this only where
   * the Electron shell provides one (see app/electron.ts) — in browser mode, or when omitted, the
   * field is plain text (a container path the user types or pastes).
   */
  onBrowse?: () => Promise<string | undefined>;
}

/** Container path field. In Electron with `onBrowse` wired, a host picker maps the chosen path
 * through the server; without it (browser mode, or before the shell wires it up) it is plain text. */
export function PathInput({ value, onValueChange, placeholder, disabled, invalid, id, onBrowse }: PathInputProps) {
  return (
    <div className="path-input">
      <TextInput
        id={id}
        value={value}
        onChange={(e) => onValueChange(e.target.value)}
        placeholder={placeholder ?? "/path/inside/the/container"}
        disabled={disabled}
        invalid={invalid}
        style={{ flex: 1 }}
      />
      {onBrowse && (
        <Button
          variant="secondary"
          size="md"
          disabled={disabled}
          icon={<FolderOpen size={14} />}
          onClick={() => {
            void onBrowse().then((picked) => picked !== undefined && onValueChange(picked));
          }}
        >
          Browse…
        </Button>
      )}
    </div>
  );
}
