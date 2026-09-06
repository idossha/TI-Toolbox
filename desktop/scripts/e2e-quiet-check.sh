#!/usr/bin/env bash
#
# Proves that a test run does not hijack the monitor: no window on screen, no focus stolen.
#
# It runs the command it is given (default `npm run e2e`) while sampling two things every 0.5 s:
#
#   * the frontmost application, from `System Events` — the focus. It must be the same app at the
#     end as at the start, and must never become one of the test binaries in between.
#   * the on-screen window list, from `CGWindowListCopyWindowInfo` — the screen. No window owned by
#     Electron / TI-Toolbox / Chromium may APPEAR at layer 0 while the command runs. Windows of those
#     owners that were already on screen before the command started (the developer's own `npm run
#     dev` window) are listed as a note and ignored — they are not evidence about this run, and
#     failing on them would make the check unusable on the one machine it exists for.
#
# The window list is what makes this a proof rather than a vibe: `getBounds()` is what Electron
# *asked* for, and macOS clamps it (a window asked to sit at x=-10000 was measured coming back on
# screen). `CGWindowListCopyWindowInfo` is what the window server actually shows.
#
# Usage:
#   scripts/e2e-quiet-check.sh                              # runs `npm run e2e`
#   scripts/e2e-quiet-check.sh npx playwright test tests/e2e/smoke.spec.ts
#
# Exit 0 = quiet. Exit 1 = a window appeared or the focus moved; the offending samples are printed.
# Exit 2 = the check itself could not run, so it proves nothing. macOS only — it is the platform
# with the monitor to hijack (Linux CI runs under Xvfb).
#
# `osascript -e 'tell application "System Events" …'` needs Automation permission for the terminal
# the first time. Without it `osascript` prints nothing, and an *empty* frontmost must never be read
# as "the focus did not move": before and after would compare equal and every assertion would pass
# vacuously while the script still printed PASS — a window-only check wearing the badge of a focus
# check, on exactly the machine this script is for. So an unreadable frontmost is a hard error.

set -uo pipefail

if [[ "$(uname)" != "Darwin" ]]; then
  echo "e2e-quiet-check: macOS only; nothing to check on $(uname)." >&2
  exit 0
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Anything whose on-screen presence would mean the run took the screen.
OWNERS='Electron|TI-Toolbox|ti-toolbox-desktop|Chromium|Google Chrome for Testing|Playwright'

# --- the window lister -----------------------------------------------------------------------
# Built here rather than committed as a binary: it is 30 lines of CoreGraphics and clang ships with
# the Xcode command line tools.
cat >"$WORK/onscreen.c" <<'C'
#include <ApplicationServices/ApplicationServices.h>
#include <stdio.h>
static void put(CFStringRef s) {
  char buf[512];
  if (s && CFStringGetCString(s, buf, sizeof buf, kCFStringEncodingUTF8)) printf("%s", buf);
  else printf("?");
}
int main(void) {
  CFArrayRef list = CGWindowListCopyWindowInfo(
      kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements, kCGNullWindowID);
  if (!list) { fprintf(stderr, "no window list\n"); return 2; }
  for (CFIndex i = 0, n = CFArrayGetCount(list); i < n; i++) {
    CFDictionaryRef w = CFArrayGetValueAtIndex(list, i);
    CFNumberRef ln = CFDictionaryGetValue(w, kCGWindowLayer);
    int layer = 0; if (ln) CFNumberGetValue(ln, kCFNumberIntType, &layer);
    CFDictionaryRef b = CFDictionaryGetValue(w, kCGWindowBounds);
    CGRect r = CGRectZero; if (b) CGRectMakeWithDictionaryRepresentation(b, &r);
    CFNumberRef idn = CFDictionaryGetValue(w, kCGWindowNumber);
    long wid = 0; if (idn) CFNumberGetValue(idn, kCFNumberLongType, &wid);
    printf("id=%ld\tlayer=%d\towner=", wid, layer);
    put(CFDictionaryGetValue(w, kCGWindowOwnerName));
    printf("\tbounds=%.0f,%.0f,%.0fx%.0f\ttitle=", r.origin.x, r.origin.y, r.size.width, r.size.height);
    put(CFDictionaryGetValue(w, kCGWindowName));
    printf("\n");
  }
  return 0;
}
C
if ! clang -o "$WORK/onscreen" "$WORK/onscreen.c" -framework ApplicationServices 2>"$WORK/clang.log"; then
  echo "e2e-quiet-check: could not build the window lister (need Xcode command line tools):" >&2
  cat "$WORK/clang.log" >&2
  exit 2
fi

# The focus, or the empty string plus a reason in $WORK/osascript.log. Never silently empty.
frontmost() {
  osascript -e 'tell application "System Events" to get name of first application process whose frontmost is true' 2>"$WORK/osascript.log"
}

UNREADABLE='<unreadable>'

die_unreadable() {
  {
    echo "e2e-quiet-check: could not read the frontmost application — $1."
    echo "  This check cannot tell you whether the focus moved, so it refuses to claim it did not."
    echo "  Grant Automation permission for \"System Events\" to this terminal:"
    echo "  System Settings > Privacy & Security > Automation > <your terminal> > System Events."
    [[ -s "$WORK/osascript.log" ]] && sed 's/^/  osascript: /' "$WORK/osascript.log"
  } >&2
  exit 2
}

# --- run, and watch --------------------------------------------------------------------------
CMD=("$@")
[[ ${#CMD[@]} -eq 0 ]] && CMD=(npm run e2e)

BEFORE="$(frontmost)"
[[ -z "$BEFORE" ]] && die_unreadable "the first sample, before the command started, came back empty"
echo "e2e-quiet-check: frontmost before = $BEFORE"
echo "e2e-quiet-check: running ${CMD[*]}"

# Windows already on screen before the command starts are the developer's own (the app they are
# tinkering with, a dev window from another lane) and are not evidence about this run; only a window
# that APPEARS during the run is. Identity is the window-server id, so a pre-existing window that
# moves or is retitled is still the same window.
"$WORK/onscreen" | grep -E "^id=[0-9]+	layer=0	owner=($OWNERS)	" >"$WORK/preexisting.txt" || true
if [[ -s "$WORK/preexisting.txt" ]]; then
  echo "e2e-quiet-check: note — these windows were already on screen before the run (ignored):"
  sed 's/^/  /' "$WORK/preexisting.txt"
fi
PRE_IDS="$(sed -E 's/^id=([0-9]+)	.*/\1/' "$WORK/preexisting.txt" | sort -u)"

( cd "$ROOT" && "${CMD[@]}" ) &
CMD_PID=$!

: >"$WORK/focus.txt"
: >"$WORK/windows.txt"
while kill -0 "$CMD_PID" 2>/dev/null; do
  SAMPLE="$(frontmost)"
  echo "${SAMPLE:-$UNREADABLE}" >>"$WORK/focus.txt"
  "$WORK/onscreen" | grep -E "^id=[0-9]+	layer=0	owner=($OWNERS)	" | while IFS= read -r line; do
    wid="${line#id=}"; wid="${wid%%	*}"
    grep -qx "$wid" <<<"$PRE_IDS" || echo "$line" >>"$WORK/windows.txt"
  done
  sleep 0.5
done
wait "$CMD_PID"
CMD_STATUS=$?

SAMPLES=$(wc -l <"$WORK/focus.txt" | tr -d ' ')

# Judged before the "after" reading, so permission lost mid-run reports as what it is.
if [[ $SAMPLES -eq 0 ]]; then
  echo "e2e-quiet-check: the command exited before the first 0.5 s sample — nothing was observed." >&2
  exit 2
fi
BLIND=$(grep -c "^$UNREADABLE$" "$WORK/focus.txt" || true)
[[ $BLIND -gt 0 ]] && die_unreadable "$BLIND of $SAMPLES samples during the run came back empty"

AFTER="$(frontmost)"
[[ -z "$AFTER" ]] && die_unreadable "the last sample, after the command finished, came back empty"
echo "e2e-quiet-check: frontmost after  = $AFTER   (${SAMPLES} samples)"
echo "e2e-quiet-check: command exited ${CMD_STATUS}"

STATUS=0

# A changed frontmost app is a failure only when a test binary is involved. On a developer's
# machine the person keeps working while the suite runs — mail, browser, terminal — and that
# movement is theirs, not the suite's. The STOLEN check below is what catches the suite taking
# the focus; this one only reports.
if [[ "$BEFORE" != "$AFTER" ]]; then
  if [[ "$AFTER" =~ ^($OWNERS)$ || "$BEFORE" =~ ^($OWNERS)$ ]]; then
    echo "e2e-quiet-check: FAIL — the frontmost app changed to/from a test binary: '$BEFORE' -> '$AFTER'" >&2
    STATUS=1
  else
    echo "e2e-quiet-check: note — the frontmost app changed while you worked: '$BEFORE' -> '$AFTER' (neither is a test binary)"
  fi
fi

STOLEN="$(grep -E "^($OWNERS)$" "$WORK/focus.txt" | sort -u)"
if [[ -n "$STOLEN" ]]; then
  echo "e2e-quiet-check: FAIL — a test binary held the focus during the run:" >&2
  echo "$STOLEN" | sed 's/^/  /' >&2
  STATUS=1
fi

MOVED="$(sort -u "$WORK/focus.txt" | grep -v "^$BEFORE$" || true)"
if [[ -n "$MOVED" ]]; then
  echo "e2e-quiet-check: note — the focus was elsewhere during some samples (not a test binary):" >&2
  echo "$MOVED" | sed 's/^/  /' >&2
fi

if [[ -s "$WORK/windows.txt" ]]; then
  echo "e2e-quiet-check: FAIL — these windows APPEARED on screen during the run:" >&2
  sort -u "$WORK/windows.txt" | sed 's/^/  /' >&2
  STATUS=1
else
  echo "e2e-quiet-check: no new Electron/Chromium window reached the screen."
fi

[[ $STATUS -eq 0 && $CMD_STATUS -eq 0 ]] && echo "e2e-quiet-check: PASS"
[[ $CMD_STATUS -ne 0 ]] && STATUS=$CMD_STATUS
exit $STATUS
