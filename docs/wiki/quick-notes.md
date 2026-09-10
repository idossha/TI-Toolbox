---
layout: wiki
title: Quick Notes
permalink: /wiki/quick-notes/
---

Quick notes is a project notepad that opens beside your work. Use **⌘⇧N** on macOS
(**Ctrl⇧N** on Windows/Linux), or find **Quick notes** in the command palette. It opens a
right-hand drawer, so you can keep the current workflow visible while writing.

## Write and save

Type directly in the notepad. Edits save automatically after a short pause; the status changes
from **Unsaved changes** to **Saving…** and then **Saved** with the time. Wait for the saved
status before closing the app or switching projects. If saving fails, the drawer keeps the
edits visible and reports the error.

- **Insert timestamp** appends the current date and time in your browser or desktop locale.
  Timestamps are optional; typing does not add one automatically.
- **Copy** copies all notes to the clipboard.
- **Clear** asks for confirmation before removing all notes in the project notepad.

## Storage

The server saves plain text in your active project:

```text
<project>/derivatives/ti-toolbox/notes.txt
```

Notes remain with the dataset across restarts and are included when you back up that file.
Switching projects opens the next project's own notes. This is a shared plain-text notepad,
not a revision history; clearing notes removes its contents.

## Troubleshooting

If notes cannot load or save, confirm that the project's server is connected and the project
directory is writable. Copy any unsaved text before closing or switching projects. For a
clipboard error, select the text and use your system's normal copy command.

> **V2 difference:** Quick Notes used to be a separate extension with an **Add Note** button
> and automatic timestamps. In v3 it is an autosaving drawer with optional timestamp insertion.
