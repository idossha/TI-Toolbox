/**
 * Quick notes — a global drawer, not a nav destination (plan §2: "panel-quick-notes → global
 * drawer ⌘⇧N"). A running notepad is something you reach for *while* looking at something else;
 * a whole page for one textarea cost a nav row and a navigation away from your work.
 *
 * The panel's behaviour is unchanged: the same `GET/PUT /api/catalog/notes`, the same 800 ms
 * debounced autosave, the same Insert timestamp / Copy / Clear actions, the same monospace field.
 * `ui/Overlay.tsx`'s `Drawer` is the Radix Dialog the shell hosts; it is 420px on the right.
 *
 * The shell (`app/Shell.tsx`, another lane) owns the open state and the ⌘⇧N binding — this file
 * takes `{ open, onOpenChange }` and knows nothing about how it was opened.
 */
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock, Copy, Trash2 } from "lucide-react";
import { Button } from "../../ui/Button";
import { Textarea } from "../../ui/Field";
import { InlineError, Kbd, Skeleton } from "../../ui/Feedback";
import { AlertDialog, Drawer } from "../../ui/Overlay";
import { notify } from "../../ui/Toast";
import { getNotes, putNotes } from "./api";
import "./quick-notes.css";

const AUTOSAVE_DELAY_MS = 800;

function formatSavedAt(iso: string | null | undefined): string {
  if (!iso) return "Not saved yet";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "Not saved yet";
  return `Saved ${d.toLocaleTimeString()}`;
}

export interface QuickNotesDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function QuickNotesDrawer({ open, onOpenChange }: QuickNotesDrawerProps) {
  const queryClient = useQueryClient();
  // Only fetch once the drawer has been opened: a notepad nobody opened should not cost a request
  // on every app start.
  const notesQuery = useQuery({ queryKey: ["notes"], queryFn: getNotes, enabled: open });
  const [text, setText] = useState("");
  const [dirty, setDirty] = useState(false);
  const [savedAt, setSavedAt] = useState<string | null | undefined>(undefined);
  const [confirmClear, setConfirmClear] = useState(false);
  const loaded = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (loaded.current || !notesQuery.data) return;
    setText(notesQuery.data.text);
    setSavedAt(notesQuery.data.updated_at);
    loaded.current = true;
  }, [notesQuery.data]);

  const saveMutation = useMutation({
    mutationFn: (value: string) => putNotes(value),
    onSuccess: (saved) => {
      // Write the fresh value straight into the query cache — without this, a remount within the
      // global `staleTime` window (main.tsx, 60s) reads the pre-edit cached GET and the just-saved
      // text visibly reverts.
      queryClient.setQueryData(["notes"], saved);
      setSavedAt(saved.updated_at);
      setDirty(false);
    },
    onError: () => notify.error("Could not save notes. Your edits are still here — try again."),
  });

  function scheduleSave(next: string) {
    setText(next);
    setDirty(true);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => saveMutation.mutate(next), AUTOSAVE_DELAY_MS);
  }

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  /** `ui/Field`'s `Textarea` is not ref-forwarding, so this appends rather than inserting at the
   * cursor — simpler, and matches the Qt version's behaviour of always adding new content at one
   * end of the notes. */
  function insertTimestamp() {
    const stamp = `[${new Date().toLocaleString()}]\n`;
    const next = text.length > 0 && !text.endsWith("\n") ? `${text}\n${stamp}` : `${text}${stamp}`;
    scheduleSave(next);
  }

  async function copyAll() {
    if (!text) {
      notify.error("There are no notes to copy.");
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      notify.success("Copied notes to the clipboard");
    } catch {
      notify.error("Could not access the clipboard.");
    }
  }

  function clearAll() {
    scheduleSave("");
    setConfirmClear(false);
  }

  const status = saveMutation.isPending ? "Saving…" : dirty ? "Unsaved changes" : formatSavedAt(savedAt);

  return (
    <Drawer open={open} onOpenChange={onOpenChange} title="Quick notes">
      <div className="quick-notes" data-testid="quick-notes">
        <div className="quick-notes-head">
          <span className="text-caption quick-notes-hint">
            Saves automatically · <Kbd>⌘⇧N</Kbd>
          </span>
          <Button variant="ghost" size="sm" icon={<Clock size={14} />} onClick={insertTimestamp}>
            Insert timestamp
          </Button>
          <Button variant="ghost" size="sm" icon={<Copy size={14} />} onClick={() => void copyAll()}>
            Copy
          </Button>
          <Button variant="ghost" size="sm" icon={<Trash2 size={14} />} onClick={() => setConfirmClear(true)}>
            Clear
          </Button>
        </div>

        {notesQuery.isError && (
          <InlineError message="Could not load notes." onAction={() => void notesQuery.refetch()} />
        )}
        {notesQuery.isPending ? (
          <Skeleton rows={10} />
        ) : (
          <Textarea
            className="mono quick-notes-field"
            value={text}
            onChange={(e) => scheduleSave(e.target.value)}
            placeholder="Type your notes here — they save automatically."
            rows={16}
            data-testid="quick-notes-textarea"
          />
        )}
        <p className="text-caption quick-notes-status" data-testid="quick-notes-status">
          {status}
        </p>
      </div>

      <AlertDialog
        open={confirmClear}
        onOpenChange={setConfirmClear}
        title="Clear all notes?"
        description="This removes everything in the notepad. This cannot be undone."
        confirmLabel="Clear notes"
        onConfirm={clearAll}
      />
    </Drawer>
  );
}

export default QuickNotesDrawer;
