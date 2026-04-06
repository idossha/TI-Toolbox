# Telemetry — Developer Reference

**Added:** 2026-04-06
**GA4 Property:** `tit-telemetry` (separate from docs analytics)
**Measurement ID:** `G-2GGJF2D8C7`
**Stream:** `CLI/GUI Events`

---

## Overview

TI-Toolbox collects anonymous, opt-in usage telemetry via the
[Google Analytics 4 Measurement Protocol](https://developers.google.com/analytics/devguides/collection/protocol/ga4).
The goal is to understand feature adoption, platform distribution, and
error rates — without collecting any personal or scientific data.

---

## Architecture

```
tit/telemetry.py              ← All telemetry logic (single module)
tit/constants.py               ← GA4 credentials + event name constants
~/.config/ti-toolbox/
  └── telemetry.json           ← Per-install config (enabled, client_id, consent_shown)
```

### Data Flow

```
User runs operation (e.g. run_simulation)
  │
  ├─ is_enabled()? ──► No ──► return (no network call)
  │
  ▼ Yes
  track_event("sim_ti", {"status": "start"})
  │
  ├─ Build GA4 payload (event name + system params + client_id)
  ├─ Spawn daemon thread
  └─ POST to https://www.google-analytics.com/mp/collect
       ?measurement_id=G-2GGJF2D8C7
       &api_secret=<embedded>
     │
     ├─ Success: GA4 returns 204 No Content
     └─ Failure: silently dropped (timeout, DNS, firewall)
```

### Key Design Decisions

| Decision | Rationale |
|---|---|
| **Stdlib only** (`urllib`, `json`, `uuid`, `threading`) | No new deps; works in Docker/SimNIBS env |
| **Daemon threads** | Never block user workflow; process can exit freely |
| **5-second timeout** | Fast failure on bad networks |
| **Silent failure** | Telemetry must never crash or delay operations |
| **Per-install UUID** (not per-user) | Counts installs, not people |
| **No tracebacks** | Only exception class name on error |

---

## What We Collect

| Data Point | Example | GA4 Parameter |
|---|---|---|
| TI-Toolbox version | `2.3.0` | `tit_version` |
| Python version | `3.11.5` | `python_version` |
| OS name | `Linux`, `Darwin` | `os_name` |
| OS release | `5.15.0` | `os_version` |
| CPU architecture | `x86_64`, `arm64` | `platform` |
| Operation type | `sim_ti`, `flex_search` | Event name |
| Operation status | `start`, `success`, `error` | `status` |
| Error class (on failure) | `ValueError` | `error_type` |
| Country (approximate) | Derived from IP by GA4 | Automatic |

### What We Do NOT Collect

- File paths, project names, directory structures
- Subject IDs, patient data, scientific results
- Electrode positions, montage names, ROI definitions
- Parameter values (intensities, coordinates, thresholds)
- Hostnames, usernames, IP addresses (GA4 anonymizes IP)
- Tracebacks or error messages

---

## Tracked Events

| Event Name | Trigger | File |
|---|---|---|
| `sim_ti` | `run_simulation()` with TI montages | `tit/sim/utils.py` |
| `sim_mti` | `run_simulation()` with mTI montages | `tit/sim/utils.py` |
| `flex_search` | `run_flex_search()` | `tit/opt/flex/flex.py` |
| `ex_search` | `run_ex_search()` | `tit/opt/ex/ex.py` |
| `analysis` | `Analyzer.analyze_sphere()` / `.analyze_cortex()` | `tit/analyzer/analyzer.py` |
| `gui_launch` | GUI `MainWindow.__init__` | `tit/gui/main.py` |

Each operation sends exactly **2 events**: `{name}` with `status: start`,
then `{name}` with `status: success` or `status: error`.

---

## Consent Flow

### First Run — CLI

When `tit` is imported in an interactive terminal and `consent_shown` is
`False`, a banner is printed asking Y/n. Default is Yes (press Enter).
Non-interactive environments (Docker builds, CI, piped stdin) skip the
prompt entirely — telemetry stays disabled.

### First Run — GUI

A `QMessageBox` dialog appears on first `MainWindow` launch with
Enable / No Thanks buttons.

### Subsequent Runs

The user's choice is persisted in `~/.config/ti-toolbox/telemetry.json`.
The prompt never appears again unless the config file is deleted.

---

## Opt-Out Mechanisms

| Method | How | Takes Effect |
|---|---|---|
| **Environment variable** | `export TIT_NO_TELEMETRY=1` | Immediately (overrides config) |
| **Config file** | Edit `~/.config/ti-toolbox/telemetry.json` → `"enabled": false` | Next operation |
| **GUI toggle** | Settings (gear icon) → "Usage Statistics" | Immediately |
| **Re-prompt** | Delete `~/.config/ti-toolbox/telemetry.json` | Next interactive session |

---

## GA4 Property Setup

This section documents how the GA4 property was created (for future
reference or if the property needs to be recreated).

### 1. Account

Used the existing Google Analytics account that hosts the TI-Toolbox
documentation analytics. Both properties live under one account.

### 2. Property

- **Property name:** `tit-telemetry`
- **Timezone/currency:** default
- **Separate from docs property** — CLI/GUI events don't mix with
  web page views.

### 3. Data Stream

- **Type:** Web (required by GA4, even for non-web use)
- **Website URL:** `https://github.com/idossha/TI-toolbox` (label only)
- **Stream name:** `CLI/GUI Events`
- **Enhanced Measurement:** OFF (not applicable to MP events)

### 4. Measurement Protocol API Secret

- **Nickname:** `tit-usage`
- **Value:** Embedded in `tit/constants.py`
- Created via: Admin → Data Streams → stream → Measurement Protocol API secrets

### 5. Why the API Secret Is Safe to Embed

The GA4 MP "API secret" is **not a sensitive credential**. It is
functionally identical to the classic `UA-XXXXX` tracking IDs that have
always been public in website HTML source:

- **EEGLAB** embeds their GA tracking ID in shipped MATLAB source (`eeg_update.m`)
- **Nipype/migas** embeds credentials in open-source Python packages
- Google's own docs describe MP secrets as client-side identifiers, not auth tokens
- The secret only permits **sending** events — it grants **zero** read access
  to analytics data (reading requires authenticated Google account access)
- Worst case scenario: someone sends fake events, which can be filtered in GA4

This is standard practice across neuroscience open-source tools.

---

## Adding a New Tracked Event

To instrument a new operation:

```python
# In your module:
from tit.telemetry import track_operation

def my_new_function(config):
    with track_operation("my_event_name"):
        # ... existing logic ...
```

Or for a one-shot event (no start/success/error):

```python
from tit.telemetry import track_event
track_event("my_event", {"custom_param": "value"})
```

Then add the event name constant to `tit/constants.py`:

```python
TELEMETRY_OP_MY_EVENT = "my_event"
```

---

## Viewing Data in GA4

1. **Realtime** → live event stream (events appear within seconds)
2. **Reports → Events** → `sim_ti`, `flex_search`, etc. with counts
3. **Reports → Tech Details** → OS/platform breakdown
4. **Reports → Demographics → Location** → country-level geo
5. **Explore** → custom funnels (e.g., start → success rate per operation)
6. **Admin → DebugView** → debug individual events during development

---

## Testing

```bash
# Run telemetry tests (all HTTP is mocked — no real network calls)
python -m pytest tests/test_telemetry.py -v

# Disable telemetry in test/CI environments
export TIT_NO_TELEMETRY=1
python -m pytest tests/

# Send a manual test ping (will appear in GA4 Realtime)
python -c "
from tit.telemetry import set_enabled, track_event
import time
set_enabled(True)
track_event('test_ping', {'status': 'manual_test'})
time.sleep(3)
"
```

---

## File Reference

| File | Role |
|---|---|
| `tit/telemetry.py` | Core module — config, consent, GA4 sender, context manager |
| `tit/constants.py` | `GA4_*` credentials, `ENV_NO_TELEMETRY`, `TELEMETRY_OP_*` names |
| `tit/sim/utils.py` | `run_simulation()` instrumentation |
| `tit/opt/flex/flex.py` | `run_flex_search()` instrumentation |
| `tit/opt/ex/ex.py` | `run_ex_search()` instrumentation |
| `tit/analyzer/analyzer.py` | `analyze_sphere()` / `analyze_cortex()` instrumentation |
| `tit/gui/main.py` | GUI consent dialog + `gui_launch` event |
| `tit/gui/settings_menu.py` | Privacy toggle in gear menu |
| `tests/test_telemetry.py` | 24 unit tests |
| `~/.config/ti-toolbox/telemetry.json` | Per-install config (not in repo) |
