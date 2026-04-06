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
tit/paths.py                   ← PathManager.user_config_dir() (static method)

User config dir (host-side, mounted into Docker):
  macOS:   ~/.config/ti-toolbox/
  Linux:   ~/.config/ti-toolbox/           (XDG)
  Windows: %APPDATA%/ti-toolbox/
  Docker:  /root/.config/ti-toolbox/       (mounted from host)
    └── telemetry.json           ← User-level config (consent, client_id)
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
| Host OS name | `darwin`, `win32`, `linux` | `os_name` |
| Host OS version | `24.6.0`, `10.0.22631` | `os_version` |
| Host CPU architecture | `x86_64`, `arm64` | `platform` |
| Operation type | `sim_ti`, `flex_search` | Event name |
| Operation status | `start`, `success`, `error` | `status` |
| Error class (on failure) | `ValueError` | `error_type` |
| Country (approximate) | Derived from IP by GA4 | Automatic |

> **Note:** OS info comes from the **host machine** (via `TIT_HOST_*`
> environment variables set by the Electron launcher), not the Docker
> container's Linux kernel. Python version is not collected — it is
> fixed by the Docker image.

### What We Do NOT Collect

- File paths, project names, directory structures
- Subject IDs, patient data, scientific results
- Electrode positions, montage names, ROI definitions
- Parameter values (intensities, coordinates, thresholds)
- Hostnames, usernames, IP addresses (GA4 anonymizes IP)
- Tracebacks or error messages
- Python version (fixed by Docker image)

---

## Tracked Events

### Operations with start + success/error (via `track_operation`)

These send exactly **2 events**: `{name}` with `status: start`,
then `{name}` with `status: success` or `status: error`.

| Event Name | Trigger | File |
|---|---|---|
| `sim_ti` | `run_simulation()` with TI montages | `tit/sim/utils.py` |
| `sim_mti` | `run_simulation()` with mTI montages | `tit/sim/utils.py` |
| `flex_search` | `run_flex_search()` | `tit/opt/flex/flex.py` |
| `ex_search` | `run_ex_search()` | `tit/opt/ex/ex.py` |
| `analysis` | `Analyzer.analyze_sphere()` / `.analyze_cortex()` | `tit/analyzer/analyzer.py` |
| `pre_pipeline` | `run_pipeline()` (full preprocessing) | `tit/pre/structural.py` |
| `stats_comparison` | `run_group_comparison()` | `tit/stats/permutation.py` |

### Feature usage events (start only, via `track_event`)

These fire once when the feature is invoked. Success/failure is captured
by the parent `track_operation` wrapper (e.g. `pre_pipeline`).

| Event Name | Trigger | File |
|---|---|---|
| `gui_launch` | GUI `MainWindow.__init__` | `tit/gui/main.py` |
| `group_analysis` | `run_group_analysis()` | `tit/analyzer/group.py` |
| `pre_charm` | `run_charm()` | `tit/pre/charm.py` |
| `pre_recon_all` | `run_recon_all()` | `tit/pre/recon_all.py` |
| `pre_dicom` | `run_dicom_to_nifti()` | `tit/pre/dicom2nifti.py` |
| `pre_qsiprep` | `run_qsiprep()` | `tit/pre/qsi/qsiprep.py` |
| `pre_qsirecon` | `run_qsirecon()` | `tit/pre/qsi/qsirecon.py` |
| `report_generate` | `BaseReportGenerator.generate()` | `tit/reporting/generators/base_generator.py` |
| `blender_montage` | `run_montage()` | `tit/blender/montage_publication.py` |
| `blender_regions` | `run_regions()` | `tit/blender/region_exporter.py` |
| `blender_vectors` | `run_vectors()` | `tit/blender/vector_field_exporter.py` |

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
| **Config file** | Edit `telemetry.json` in user config dir → `"enabled": false` | Next operation |
| **GUI toggle** | Settings (gear icon) → "Usage Statistics" | Immediately |
| **Re-prompt** | Delete `~/.config/ti-toolbox/telemetry.json` | Next interactive session |

---

## User-Level Config Mount (Docker Persistence)

Telemetry config must persist across **projects** (one consent for all)
and **container restarts** (Docker is ephemeral).  This is achieved by
mounting a host directory into the container.

### How It Works

```
Host (Electron launcher)                    Docker Container
───────────────────────────────────────────────────────────
~/Library/Application Support/ti-toolbox/   ──mount──►  /root/.config/ti-toolbox/
  └── telemetry.json                                      └── telemetry.json
```

### docker-compose.yml Mount

```yaml
volumes:
  - ${TIT_USER_CONFIG}:/root/.config/ti-toolbox
```

`TIT_USER_CONFIG` is set by the Electron launcher (`env.js`) to the
platform-appropriate directory:

| Platform | Host Path | Set By |
|---|---|---|
| macOS | `~/.config/ti-toolbox/` | `getUserConfigDir()` in `env.js` |
| Linux | `~/.config/ti-toolbox/` (XDG) | `getUserConfigDir()` in `env.js` |
| Windows | `%APPDATA%\ti-toolbox\` | `getUserConfigDir()` in `env.js` |

### Python Resolution

`PathManager.user_config_dir()` (static method) resolves the same
directory from the Python side:

1. Checks if `/root/.config/ti-toolbox/` exists (Docker)
2. Falls back to platform-native path (dev/testing outside Docker)

### Future Use

Any user-level preference that should persist across projects can use
this directory.  Candidates:
- GUI window position / theme preferences
- Default electrode net selection
- Custom keyboard shortcuts

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

### 4. Register Custom Dimensions

GA4 event parameters must be registered as **custom dimensions** before
they appear in reports and Looker Studio.  Without this step, the data
is collected but invisible in the UI.

In GA4: **Admin → Custom definitions → Create custom dimension**

| Dimension name | Event parameter | Scope |
|---|---|---|
| TIT Version | `tit_version` | Event |
| Host OS | `os_name` | Event |
| Host OS Version | `os_version` | Event |
| Host Architecture | `platform` | Event |
| Status | `status` | Event |
| Error Type | `error_type` | Event |
| Report Type | `report_type` | Event |
| N Subjects | `n_subjects` | Event |

**Important:** After creating dimensions, existing data takes ~24h to
backfill. New events are available immediately.

### 5. Measurement Protocol API Secret

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

## BigQuery Export (Long-Term Retention)

GA4 retains processed data for a maximum of 14 months. For indefinite
retention, all events are exported to BigQuery via the built-in GA4
BigQuery Link.

### Architecture

```
tit/telemetry.py  ──POST──►  GA4 Measurement Protocol
                                │
                                ├──► GA4 Realtime (seconds)
                                ├──► GA4 Reports (24h processing, 14-month window)
                                └──► BigQuery Export (daily batch, unlimited retention)
                                       │
                                       ▼
                              Looker Studio
                                ├── GA4 connector (last 14 months, fast)
                                └── BigQuery connector (full history, SQL)
```

### Setup

1. **GA4 Admin → BigQuery Links → Link**
2. Select or create a GCP project (free tier is sufficient)
3. Choose **Daily export** (batched — sufficient for our volume)
4. Pick dataset location (US)
5. Events start flowing automatically — no code changes required

### Cost

BigQuery free tier: 10 GB storage + 1 TB queries/month. At our volume
(academic tool, dozens to low hundreds of users), this costs nothing
and will not be exceeded for years.

### Usage

- **Day-to-day monitoring**: Looker Studio → GA4 data source (fast, pre-aggregated)
- **Historical analysis / annual reports**: Looker Studio → BigQuery data source
- **Custom queries**: BigQuery console with SQL (e.g., error rate trends over
  multiple years, version adoption curves)

---

## Looker Studio Dashboard

A free Looker Studio dashboard provides near-real-time visualization
of telemetry data. Two data sources are used: the **GA4 connector** for
recent data (fast, pre-aggregated) and the **BigQuery connector** for
full historical queries.

### Setup

1. Go to [lookerstudio.google.com](https://lookerstudio.google.com)
2. **Create → Report → Blank Report**
3. Add data source: **Google Analytics** → select `tit-telemetry` property
4. (Optional) Add second data source: **BigQuery** → select the exported dataset

### Dashboard Layout

```
Row 1 — Scorecards
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ Active Users │ │  Total Ops   │ │ Success Rate │ │  Error Rate  │
│    (7d)      │ │   (30d)      │ │              │ │              │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘

Row 2 — Trends + Distribution
┌──────────────────────────────┐ ┌───────────────────┐
│  Events Over Time (line)     │ │ Operations (donut) │
└──────────────────────────────┘ └───────────────────┘

Row 3 — Reliability + Platform
┌──────────────────────────────┐ ┌───────────────────┐
│  Success vs Error (stacked)  │ │ Platform Mix (pie) │
└──────────────────────────────┘ └───────────────────┘

Row 4 — Adoption + Errors
┌──────────────────────────────┐ ┌───────────────────┐
│  Version Adoption (bar)      │ │ Error Types (table)│
└──────────────────────────────┘ └───────────────────┘

Row 5 — Geography (full width)
┌────────────────────────────────────────────────────┐
│  Country Map (geo)                                  │
└────────────────────────────────────────────────────┘

Row 6 — Feature Drill-Down (full width)
┌────────────────────────────────────────────────────┐
│  Preprocessing & Feature Usage (horizontal bar)     │
└────────────────────────────────────────────────────┘
```

### Panel Specifications

| Panel | Chart Type | Dimension | Metric |
|---|---|---|---|
| Active Users (7d) | Scorecard | — | Active users |
| Total Ops (30d) | Scorecard | — | Event count (filtered to operations) |
| Success Rate | Scorecard | — | Calculated field (see below) |
| Error Rate | Scorecard | — | Calculated field (see below) |
| Events Over Time | Time series | Date | Event count |
| Operations Breakdown | Donut chart | Event name | Event count |
| Success vs Error | Stacked bar | Event name + Status | Event count |
| Platform Mix | Pie chart | OS Name | Event count |
| Version Adoption | Bar chart | TIT Version | Event count |
| Error Types | Table | Error Type (filter: status=error) | Event count |
| Country Map | Geo map | Country | Active users |
| Feature Usage | Horizontal bar | Event name (filter: pre_*, blender_*, gui_*) | Event count |

### Calculated Fields

Success and error rate scorecards require calculated fields in Looker
Studio (Resource → Manage added data sources → Edit → Add a field):

```
Name:    Success Rate
Formula: SUM(CASE WHEN Status = "success" THEN 1 ELSE 0 END)
         / SUM(CASE WHEN Status = "success" OR Status = "error" THEN 1 ELSE 0 END)
Type:    Percent
```

```
Name:    Error Rate
Formula: SUM(CASE WHEN Status = "error" THEN 1 ELSE 0 END)
         / SUM(CASE WHEN Status = "success" OR Status = "error" THEN 1 ELSE 0 END)
Type:    Percent
```

> **Note:** The `Status` dimension comes from the custom dimension registered
> in GA4 (parameter: `status`). It takes 24–48 hours after registration
> before it appears in Looker Studio's field list.

### Filters

Useful filters for the dashboard:
- **Exclude test events**: Event name ≠ `container_test_ping`, `test_ping`
- **Operations only**: Event name matches `sim_|flex_|ex_|analysis|pre_|stats_|blender_|gui_`
- **Errors only**: Status = `error`
- **Date range**: Last 30 days (default)

### Auto-Refresh

**View → Auto-refresh → 15 minutes** (minimum interval).
GA4 data has ~5-minute latency for realtime, ~24h for full processing.
BigQuery daily export processes once per day.

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
| User config dir `/telemetry.json` | User-level config (persists across projects + containers) |
